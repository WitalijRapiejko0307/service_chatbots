"""Channel bindings API endpoints."""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator

from app.api.auth import require_admin
from app.api.exceptions import AgentNotFoundError
from app.dependencies import CommonDependencies
from app.models.channel_binding import ChannelBinding, ChannelType
from app.services.channel_binding_service import ChannelBindingService
from app.storage.resolver import get_secrets_manager
from app.utils.datetime_utils import to_utc_iso_string
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)
router = APIRouter()


class CreateChannelBindingRequest(BaseModel):
    """Request to create a channel binding."""

    channel_type: str = Field(..., description="Channel type (telegram, viber, instagram, tiktok, web_chat)")
    channel_account_id: str = Field(..., description="Channel account ID")
    access_token: str = Field(..., description="Access token for the channel")
    channel_username: Optional[str] = Field(None, description="Channel username (optional, for display)")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("channel_type")
    @classmethod
    def validate_channel_type(cls, v: str) -> str:
        try:
            ChannelType(v)
        except ValueError:
            allowed = ", ".join(c.value for c in ChannelType)
            raise ValueError(f"Invalid channel type: {v}. Allowed: {allowed}")
        return v


class UpdateChannelBindingRequest(BaseModel):
    is_active: Optional[bool] = Field(None)
    access_token: Optional[str] = Field(None)
    metadata: Optional[dict[str, Any]] = Field(None)


class UpdateCommandsRequest(BaseModel):
    commands: dict[str, bool] = Field(
        ...,
        description="Map of command key to enabled flag, e.g. {\"restart\": true}",
    )

    @field_validator("commands")
    @classmethod
    def validate_command_keys(cls, v: dict[str, bool]) -> dict[str, bool]:
        from app.services.bot_commands_service import TELEGRAM_BOT_COMMANDS

        known = {cmd["key"] for cmd in TELEGRAM_BOT_COMMANDS}
        unknown = set(v.keys()) - known
        if unknown:
            raise ValueError(f"Unknown command key(s): {unknown}")
        return v


class ChannelBindingResponse(BaseModel):
    binding_id: str
    agent_id: str
    channel_type: str
    channel_account_id: str
    channel_username: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: str
    updated_at: str
    created_by: Optional[str]
    metadata: dict[str, Any]

    @classmethod
    def from_binding(cls, binding: ChannelBinding) -> "ChannelBindingResponse":
        return cls(
            binding_id=binding.binding_id,
            agent_id=binding.agent_id,
            channel_type=get_enum_value(binding.channel_type),
            channel_account_id=binding.channel_account_id,
            channel_username=binding.channel_username,
            is_active=binding.is_active,
            is_verified=binding.is_verified,
            created_at=to_utc_iso_string(binding.created_at),
            updated_at=to_utc_iso_string(binding.updated_at),
            created_by=binding.created_by,
            metadata=binding.metadata,
        )


def get_channel_binding_service(
    deps: CommonDependencies = Depends(),
) -> ChannelBindingService:
    secrets_manager = get_secrets_manager()
    return ChannelBindingService(deps.db, secrets_manager)


@router.post(
    "/agents/{agent_id}/channel-bindings",
    response_model=ChannelBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel_binding(
    agent_id: str,
    request: CreateChannelBindingRequest,
    deps: CommonDependencies = Depends(),
    binding_service: ChannelBindingService = Depends(get_channel_binding_service),
    _admin: str = require_admin(),
):
    """Create a new channel binding for an agent."""
    agent_data = await deps.db.get_agent(agent_id)
    if not agent_data:
        raise AgentNotFoundError(agent_id)

    try:
        binding = await binding_service.create_binding(
            agent_id=agent_id,
            channel_type=request.channel_type,
            channel_account_id=request.channel_account_id,
            access_token=request.access_token,
            metadata=request.metadata,
            created_by=_admin,
            channel_username=request.channel_username,
        )
        return ChannelBindingResponse.from_binding(binding)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create channel binding: {str(e)}",
        )


@router.get(
    "/agents/{agent_id}/channel-bindings",
    response_model=list[ChannelBindingResponse],
)
async def list_channel_bindings(
    agent_id: str,
    channel_type: Optional[str] = Query(None, description="Filter by channel type"),
    active_only: bool = Query(default=True, description="Filter only active bindings"),
    deps: CommonDependencies = Depends(),
    binding_service: ChannelBindingService = Depends(get_channel_binding_service),
    _admin: str = require_admin(),
):
    agent_data = await deps.db.get_agent(agent_id)
    if not agent_data:
        raise AgentNotFoundError(agent_id)

    if channel_type:
        try:
            ChannelType(channel_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid channel type: {channel_type}",
            )

    try:
        bindings = await binding_service.get_bindings_by_agent(
            agent_id=agent_id,
            channel_type=channel_type,
            active_only=active_only,
        )
        return [ChannelBindingResponse.from_binding(binding) for binding in bindings]
    except Exception as e:
        logger.error(
            "Failed to get channel bindings for agent %s: %s",
            agent_id,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve channel bindings: {str(e)}",
        )


@router.get(
    "/channel-bindings/{binding_id}",
    response_model=ChannelBindingResponse,
)
async def get_channel_binding(
    binding_id: str,
    binding_service: ChannelBindingService = Depends(get_channel_binding_service),
    _admin: str = require_admin(),
):
    binding = await binding_service.get_binding(binding_id)
    if not binding:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel binding {binding_id} not found",
        )
    return ChannelBindingResponse.from_binding(binding)


@router.put(
    "/channel-bindings/{binding_id}",
    response_model=ChannelBindingResponse,
)
async def update_channel_binding(
    binding_id: str,
    request: UpdateChannelBindingRequest,
    binding_service: ChannelBindingService = Depends(get_channel_binding_service),
    _admin: str = require_admin(),
):
    try:
        binding = await binding_service.update_binding(
            binding_id=binding_id,
            is_active=request.is_active,
            access_token=request.access_token,
            metadata=request.metadata,
        )
        return ChannelBindingResponse.from_binding(binding)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update channel binding: {str(e)}",
        )


@router.delete(
    "/channel-bindings/{binding_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_channel_binding(
    binding_id: str,
    binding_service: ChannelBindingService = Depends(get_channel_binding_service),
    _admin: str = require_admin(),
):
    try:
        await binding_service.delete_binding(binding_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete channel binding: {str(e)}",
        )


@router.post(
    "/channel-bindings/{binding_id}/verify",
    response_model=dict[str, Any],
)
async def verify_channel_binding(
    binding_id: str,
    binding_service: ChannelBindingService = Depends(get_channel_binding_service),
    _admin: str = require_admin(),
):
    try:
        is_verified = await binding_service.verify_binding(binding_id)
        binding = await binding_service.get_binding(binding_id)
        if not binding:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Channel binding {binding_id} not found",
            )
        return {
            "binding_id": binding_id,
            "is_verified": is_verified,
            "status": "verified" if is_verified else "verification_failed",
            "metadata": binding.metadata,
        }
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify channel binding: {str(e)}",
        )


@router.get(
    "/channel-bindings/{binding_id}/commands",
    response_model=list[dict[str, Any]],
)
async def get_binding_commands(
    binding_id: str,
    binding_service: ChannelBindingService = Depends(get_channel_binding_service),
    _admin: str = require_admin(),
):
    binding = await binding_service.get_binding(binding_id)
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    if get_enum_value(binding.channel_type) != "telegram":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot commands are only supported for Telegram bindings",
        )
    from app.services.bot_commands_service import get_commands_status

    return get_commands_status(binding)


@router.put(
    "/channel-bindings/{binding_id}/commands",
    response_model=list[dict[str, Any]],
)
async def update_binding_commands(
    binding_id: str,
    request: UpdateCommandsRequest,
    binding_service: ChannelBindingService = Depends(get_channel_binding_service),
    _admin: str = require_admin(),
):
    binding = await binding_service.get_binding(binding_id)
    if not binding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Binding not found")
    if get_enum_value(binding.channel_type) != "telegram":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bot commands are only supported for Telegram bindings",
        )

    current_metadata = dict(binding.metadata)
    existing_commands: dict[str, bool] = dict(current_metadata.get("telegram_commands") or {})
    existing_commands.update(request.commands)
    current_metadata["telegram_commands"] = existing_commands

    try:
        updated_binding = await binding_service.update_binding(
            binding_id=binding_id,
            metadata=current_metadata,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update commands: {str(e)}",
        )

    try:
        bot_token = await binding_service.get_access_token(binding_id)
        from app.services.bot_commands_service import sync_telegram_commands

        await sync_telegram_commands(bot_token, updated_binding)
    except Exception as exc:
        logger.warning(
            "Could not sync Telegram bot commands for binding %s: %s",
            binding_id,
            exc,
        )

    from app.services.bot_commands_service import get_commands_status

    return get_commands_status(updated_binding)
