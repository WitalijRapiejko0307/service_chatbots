"""Admin API endpoints."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.auth import require_admin
from app.api.exceptions import ConversationNotFoundError
from app.api.websocket import connection_manager
from app.config import get_settings
from app.dependencies import CommonDependencies
from app.models.conversation import Conversation, ConversationStatus, MarketingStatus
from app.models.message import Message, MessageChannel, MessageRole
from app.services.channel_sender import get_channel_sender
from app.utils.datetime_utils import (
    parse_query_datetime,
    parse_utc_datetime,
    to_utc_iso_string,
    utc_now,
)
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

router = APIRouter()


class HandoffRequest(BaseModel):
    """Request to handoff conversation to human."""

    admin_id: str = Field(..., description="Admin user ID", min_length=1)
    reason: Optional[str] = Field(
        None, description="Reason for handoff", max_length=500
    )


class HandoffResponse(BaseModel):
    """Response for handoff."""

    conversation_id: str
    status: str
    message: str


@router.get("/conversations")
async def list_conversations(
    agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
    status: Optional[str] = Query(None, description="Filter by conversation status"),
    marketing_status: Optional[str] = Query(None, description="Filter by marketing status (legacy)"),
    crm_stage_id: Optional[str] = Query(None, description="Filter by CRM stage UUID"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of conversations"),
    sort_by: str = Query(
        default="created_at",
        description="Sort field: created_at or updated_at",
    ),
    sort_order: str = Query(
        default="desc",
        description="Sort direction: asc or desc",
    ),
    created_from: Optional[str] = Query(
        None,
        description="Filter: conversation created_at >= this (ISO date/datetime, UTC)",
    ),
    created_to: Optional[str] = Query(
        None,
        description="Filter: conversation created_at <= this (ISO date/datetime, UTC; date-only = end of day UTC)",
    ),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """List conversations (admin view)."""
    if sort_by not in ("created_at", "updated_at"):
        raise HTTPException(
            status_code=400,
            detail="Invalid sort_by. Valid values: created_at, updated_at",
        )
    if sort_order not in ("asc", "desc"):
        raise HTTPException(
            status_code=400,
            detail="Invalid sort_order. Valid values: asc, desc",
        )

    try:
        dt_from = parse_query_datetime(created_from, end_of_day=False)
        dt_to = parse_query_datetime(created_to, end_of_day=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    if dt_from is not None and dt_to is not None and dt_from > dt_to:
        raise HTTPException(
            status_code=400,
            detail="created_from must be before or equal to created_to",
        )

    status_enum = None
    if status:
        try:
            status_enum = ConversationStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}. Valid values: {', '.join([s.value for s in ConversationStatus])}",
            )

    if marketing_status:
        valid_marketing_statuses = [s.value for s in MarketingStatus]
        if marketing_status not in valid_marketing_statuses:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid marketing_status: {marketing_status}. Valid values: {', '.join(valid_marketing_statuses)}",
            )

    conversations = await deps.db.list_conversations(
        agent_id=agent_id,
        status=status_enum,
        marketing_status=marketing_status,
        crm_stage_id=crm_stage_id,
        limit=limit,
        sort_by=sort_by,
        sort_order=sort_order,
        created_from=dt_from,
        created_to=dt_to,
    )
    return conversations


@router.get("/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(
    conversation_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Get conversation by ID (admin view)."""

    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    conversation_channel = get_enum_value(conversation.channel)
    if conversation_channel == MessageChannel.INSTAGRAM.value and conversation.external_user_id:
        profile = await deps.db.get_instagram_profile(conversation.external_user_id)
        if profile:
            conversation.external_user_name = profile.name
            conversation.external_user_username = profile.username
            conversation.external_user_profile_pic = profile.profile_pic

    return conversation


@router.post(
    "/conversations/{conversation_id}/handoff",
    response_model=HandoffResponse,
    status_code=status.HTTP_200_OK,
)
async def handoff_conversation(
    conversation_id: str,
    request: HandoffRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Handoff conversation to human admin (HUMAN_ACTIVE — AI stays silent until return)."""

    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    try:
        updated = await deps.db.update_conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.HUMAN_ACTIVE,
            handoff_reason=request.reason or "Manual handoff",
        )

        await deps.db.create_audit_log(
            admin_id=request.admin_id,
            action="handoff",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={"reason": request.reason},
        )

        status_value = (
            get_enum_value(updated.status) if updated else ConversationStatus.HUMAN_ACTIVE.value
        )

        return HandoffResponse(
            conversation_id=conversation_id,
            status=status_value,
            message="Conversation handed off to human",
        )
    except Exception as e:
        logger.error(f"Error handing off conversation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to handoff conversation: {str(e)}",
        )


class ReturnToAIRequest(BaseModel):
    """Request to return conversation to AI."""

    admin_id: str = Field(..., description="Admin user ID", min_length=1)


@router.post("/conversations/{conversation_id}/return")
async def return_to_ai(
    conversation_id: str,
    request: ReturnToAIRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Return conversation to AI (AI_ACTIVE)."""

    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    try:
        updated = await deps.db.update_conversation(
            conversation_id=conversation_id,
            status=ConversationStatus.AI_ACTIVE,
        )

        await deps.db.create_audit_log(
            admin_id=request.admin_id,
            action="return_to_ai",
            resource_type="conversation",
            resource_id=conversation_id,
        )

        status_value = (
            get_enum_value(updated.status) if updated else ConversationStatus.AI_ACTIVE.value
        )

        return {
            "conversation_id": conversation_id,
            "status": status_value,
            "message": "Conversation returned to AI",
        }
    except Exception as e:
        logger.error(f"Error returning conversation to AI: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to return conversation to AI: {str(e)}",
        )


class ResetAgentContextRequest(BaseModel):
    """Request to set agent context watermark (exclude older messages from LLM context)."""

    admin_id: str = Field(..., description="Admin user ID", min_length=1)


@router.post("/conversations/{conversation_id}/reset-agent-context")
async def reset_agent_context(
    conversation_id: str,
    request: ResetAgentContextRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Mark now as agent context reset: messages at or before this time are not sent to the agent."""
    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    now = utc_now()
    try:
        updated = await deps.db.update_conversation(
            conversation_id=conversation_id,
            agent_context_reset_at=now,
        )
        await deps.db.create_audit_log(
            admin_id=request.admin_id,
            action="reset_agent_context",
            resource_type="conversation",
            resource_id=conversation_id,
        )
        reset_iso = (
            to_utc_iso_string(updated.agent_context_reset_at)
            if updated and updated.agent_context_reset_at
            else to_utc_iso_string(now)
        )
        return {
            "conversation_id": conversation_id,
            "agent_context_reset_at": reset_iso,
            "message": "Agent context reset",
        }
    except Exception as e:
        logger.error(f"Error resetting agent context: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reset agent context: {str(e)}",
        )


@router.get("/audit")
async def get_audit_logs(
    admin_id: Optional[str] = Query(None, description="Filter by admin ID"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    action: Optional[str] = Query(None, description="Filter by action"),
    start_date: Optional[str] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[str] = Query(None, description="End date (ISO format)"),
    sort: str = Query(default="desc", description="Sort order: 'asc' or 'desc'"),
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of logs"),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Get audit logs with filtering and sorting."""
    try:
        if sort not in ["asc", "desc"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid sort parameter. Must be 'asc' or 'desc'",
            )

        start_datetime = None
        end_datetime = None
        if start_date:
            try:
                start_datetime = parse_utc_datetime(start_date)
            except ValueError as e:
                logger.warning(f"Invalid start_date format: {start_date}, error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid start_date format. Use ISO format (e.g., 2024-01-01T00:00:00Z)",
                )
        if end_date:
            try:
                end_datetime = parse_utc_datetime(end_date)
            except ValueError as e:
                logger.warning(f"Invalid end_date format: {end_date}, error: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid end_date format. Use ISO format (e.g., 2024-01-01T00:00:00Z)",
                )

        logs = await deps.db.list_audit_logs(
            admin_id=admin_id,
            resource_type=resource_type,
            action=action,
            start_date=start_datetime,
            end_date=end_datetime,
            sort_desc=sort == "desc",
            limit=limit,
        )

        if not isinstance(logs, list):
            logger.warning(f"list_audit_logs returned non-list: {type(logs)}")
            return []

        return logs
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_audit_logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit logs: {str(e)}",
        )


class SendAdminMessageRequest(BaseModel):
    """Request to send admin message."""

    admin_id: str = Field(..., description="Admin user ID", min_length=1)
    content: str = Field(default="", description="Message text (may be empty when sending media only)", max_length=10000)
    media_url: Optional[str] = Field(None, description="Public URL of attached media (from /api/v1/media/upload)")
    media_type: Optional[str] = Field(None, description="Media category: image, video, audio, document")
    media_filename: Optional[str] = Field(None, description="Original filename of the attached media")


class SendAdminMessageResponse(BaseModel):
    """Response for admin message."""

    message_id: str
    role: str
    content: str
    timestamp: str
    media_url: Optional[str] = None
    media_type: Optional[str] = None


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=SendAdminMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_admin_message(
    conversation_id: str,
    request: SendAdminMessageRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Send a message as admin in a conversation."""

    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    status_value = get_enum_value(conversation.status)
    if status_value not in [
        ConversationStatus.NEEDS_HUMAN.value,
        ConversationStatus.HUMAN_ACTIVE.value,
    ]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Admin can only send messages when conversation status is NEEDS_HUMAN or HUMAN_ACTIVE",
        )

    if not request.content and not request.media_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either content or media_url must be provided",
        )

    try:
        message_id = str(uuid.uuid4())
        msg_metadata: dict = {}
        if request.media_url:
            msg_metadata["media_url"] = request.media_url
        if request.media_type:
            msg_metadata["media_type"] = request.media_type
        if request.media_filename:
            msg_metadata["media_filename"] = request.media_filename

        admin_message = Message(
            message_id=message_id,
            conversation_id=conversation_id,
            agent_id=conversation.agent_id,
            role=MessageRole.ADMIN,
            content=request.content or "",
            channel=conversation.channel,
            external_user_id=conversation.external_user_id,
            timestamp=utc_now(),
            metadata=msg_metadata,
            media_url=request.media_url,
            media_type=request.media_type,
        )

        await deps.db.create_message(admin_message)

        conversation_channel = get_enum_value(conversation.channel)
        channel_enum = (
            MessageChannel(conversation_channel)
            if isinstance(conversation_channel, str)
            else conversation.channel
        )

        # Web chat: push as role=admin via the live chat WS (WebChatSender defaults to agent).
        if conversation_channel == MessageChannel.WEB_CHAT.value:
            try:
                await connection_manager.send_message(
                    conversation_id,
                    {
                        "type": "message",
                        "message_id": message_id,
                        "role": "admin",
                        "content": request.content,
                        "media_url": request.media_url,
                        "media_type": request.media_type,
                        "timestamp": to_utc_iso_string(admin_message.timestamp),
                    },
                )
            except Exception as ws_error:
                logger.warning(f"Failed to send admin message via WebSocket: {ws_error}")
        else:
            sender = get_channel_sender(channel_enum, deps.db)
            try:
                await sender.send_message(
                    conversation_id=conversation_id,
                    message_text=request.content,
                    media_url=request.media_url,
                    media_type=request.media_type,
                    message_id=message_id,
                    is_human_reply=True,
                )
                logger.info(
                    f"Sent admin message to {conversation_channel} conversation {conversation_id}"
                )
            except ValueError as e:
                logger.error(f"Failed to send {conversation_channel} message: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Cannot send message to {conversation_channel} conversation: {str(e)}",
                )
            except Exception as e:
                logger.error(
                    f"Failed to deliver admin message via {conversation_channel}: {e}",
                    exc_info=True,
                )

        await deps.db.create_audit_log(
            admin_id=request.admin_id,
            action="send_message",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={"message_id": message_id},
        )

        role_value = get_enum_value(admin_message.role)
        return SendAdminMessageResponse(
            message_id=message_id,
            role=role_value,
            content=admin_message.content,
            timestamp=to_utc_iso_string(admin_message.timestamp),
            media_url=admin_message.media_url,
            media_type=admin_message.media_type,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending admin message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send admin message: {str(e)}",
        )


class RefreshProfileResponse(BaseModel):
    """Response for profile refresh."""

    name: Optional[str] = None
    username: Optional[str] = None
    profile_pic: Optional[str] = None
    error: Optional[str] = None


class UpdateMarketingStatusRequest(BaseModel):
    """Request to update marketing status."""

    marketing_status: str = Field(..., description="New marketing status")
    rejection_reason: Optional[str] = Field(
        None, description="Reason for rejection (required when marketing_status is REJECTED)", max_length=1000
    )
    admin_id: str = Field(..., description="Admin user ID", min_length=1)


class UpdateMarketingStatusResponse(BaseModel):
    """Response for marketing status update."""

    conversation_id: str
    marketing_status: str
    rejection_reason: Optional[str] = None
    message: str


@router.post(
    "/conversations/{conversation_id}/refresh-profile",
    response_model=RefreshProfileResponse,
    status_code=status.HTTP_200_OK,
)
async def refresh_instagram_profile(
    conversation_id: str,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Refresh Instagram user profile from Graph API."""
    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    from app.services.channel_binding_service import ChannelBindingService
    from app.services.instagram_service import InstagramService
    from app.storage.resolver import get_secrets_manager

    secrets_manager = get_secrets_manager()
    binding_service = ChannelBindingService(deps.db, secrets_manager)
    instagram_service = InstagramService(binding_service, deps.db, get_settings())
    try:
        profile, error = await instagram_service.refresh_profile_for_conversation(conversation)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    if not profile:
        return RefreshProfileResponse(error=error or "Graph API did not return a profile")

    return RefreshProfileResponse(
        name=profile.name,
        username=profile.username,
        profile_pic=profile.profile_pic,
    )


@router.patch(
    "/conversations/{conversation_id}/marketing-status",
    response_model=UpdateMarketingStatusResponse,
    status_code=status.HTTP_200_OK,
)
async def update_marketing_status(
    conversation_id: str,
    request: UpdateMarketingStatusRequest,
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Update marketing status of a conversation."""

    valid_marketing_statuses = [s.value for s in MarketingStatus]
    if request.marketing_status not in valid_marketing_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid marketing_status: {request.marketing_status}. Valid values: {', '.join(valid_marketing_statuses)}",
        )

    if request.marketing_status == MarketingStatus.REJECTED.value:
        if not request.rejection_reason or not request.rejection_reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="rejection_reason is required when marketing_status is REJECTED",
            )

    conversation = await deps.db.get_conversation(conversation_id)
    if not conversation:
        raise ConversationNotFoundError(conversation_id)

    old_marketing_status = get_enum_value(conversation.marketing_status) if conversation.marketing_status else MarketingStatus.NEW.value

    try:
        update_kwargs = {
            "marketing_status": request.marketing_status,
        }

        if request.marketing_status == MarketingStatus.REJECTED.value:
            update_kwargs["rejection_reason"] = request.rejection_reason
        else:
            update_kwargs["rejection_reason"] = None

        updated = await deps.db.update_conversation(
            conversation_id=conversation_id,
            **update_kwargs,
        )

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update marketing status",
            )

        await deps.db.create_audit_log(
            admin_id=request.admin_id,
            action="update_marketing_status",
            resource_type="conversation",
            resource_id=conversation_id,
            metadata={
                "old_marketing_status": old_marketing_status,
                "new_marketing_status": request.marketing_status,
                "rejection_reason": request.rejection_reason if request.marketing_status == MarketingStatus.REJECTED.value else None,
            },
        )

        try:
            from app.api.admin_websocket import get_admin_broadcast_manager
            broadcast_manager = get_admin_broadcast_manager()
            await broadcast_manager.broadcast_conversation_update(updated)
        except Exception as e:
            logger.warning(
                f"Failed to broadcast marketing status update: {e}",
                exc_info=True,
            )

        return UpdateMarketingStatusResponse(
            conversation_id=conversation_id,
            marketing_status=request.marketing_status,
            rejection_reason=request.rejection_reason if request.marketing_status == MarketingStatus.REJECTED.value else None,
            message="Marketing status updated successfully",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating marketing status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update marketing status: {str(e)}",
        )


class EndUserRow(BaseModel):
    """One aggregated end-user row for admin stats."""

    agent_id: str
    agent_display_name: Optional[str] = None
    channel: str
    external_user_id: str
    display_name: Optional[str] = None
    username: Optional[str] = None
    last_seen_at: Optional[str] = None
    conversation_count: int = Field(..., ge=0)


class EndUsersPageResponse(BaseModel):
    """Paginated distinct end users."""

    total: int = Field(..., ge=0)
    items: list[EndUserRow]


@router.get("/stats/end-users", response_model=EndUsersPageResponse)
async def list_stats_end_users(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """List unique end users (by agent + channel + external_user_id), paginated."""
    total = await deps.db.count_distinct_end_users()
    rows = await deps.db.list_distinct_end_users(limit=limit, offset=offset)
    return EndUsersPageResponse(total=total, items=[EndUserRow(**r) for r in rows])


@router.get("/stats")
async def get_stats(
    period: Optional[str] = Query(
        default="today",
        description="Time period: 'today', 'last_7_days', 'last_30_days'",
    ),
    include_comparison: bool = Query(
        default=False,
        description="Include comparison with previous period",
    ),
    deps: CommonDependencies = Depends(),
    _admin: str = require_admin(),
):
    """Get statistics with optional period filtering and comparison."""
    valid_periods = ["today", "last_7_days", "last_30_days"]
    if period not in valid_periods:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid period. Must be one of: {', '.join(valid_periods)}",
        )

    from datetime import timezone as tz
    now = utc_now()
    if period == "today":
        start_date = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=tz.utc)
        end_date = now
    elif period == "last_7_days":
        start_date = now - timedelta(days=7)
        end_date = now
    else:
        start_date = now - timedelta(days=30)
        end_date = now

    all_conversations = await deps.db.list_conversations(limit=1000)

    period_conversations = []
    for c in all_conversations:
        if not c.created_at:
            continue
        created_dt = None
        if isinstance(c.created_at, datetime):
            created_dt = c.created_at
        elif isinstance(c.created_at, str):
            try:
                created_dt = parse_utc_datetime(c.created_at)
            except (ValueError, AttributeError):
                continue
        if created_dt is None:
            continue
        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=tz.utc)
        _start = start_date.replace(tzinfo=tz.utc) if start_date.tzinfo is None else start_date
        _end = end_date.replace(tzinfo=tz.utc) if end_date.tzinfo is None else end_date
        if _start <= created_dt <= _end:
            period_conversations.append(c)

    unique_end_users = await deps.db.count_distinct_end_users()

    stats = {
        "total_conversations": len(period_conversations),
        "ai_active": sum(
            1
            for c in period_conversations
            if get_enum_value(c.status) == ConversationStatus.AI_ACTIVE.value
        ),
        "needs_human": sum(
            1
            for c in period_conversations
            if get_enum_value(c.status) == ConversationStatus.NEEDS_HUMAN.value
        ),
        "human_active": sum(
            1
            for c in period_conversations
            if get_enum_value(c.status) == ConversationStatus.HUMAN_ACTIVE.value
        ),
        "closed": sum(
            1
            for c in period_conversations
            if get_enum_value(c.status) == ConversationStatus.CLOSED.value
        ),
        "marketing_new": sum(
            1
            for c in period_conversations
            if get_enum_value(c.marketing_status) == MarketingStatus.NEW.value
        ),
        "marketing_booked": sum(
            1
            for c in period_conversations
            if get_enum_value(c.marketing_status) == MarketingStatus.BOOKED.value
        ),
        "marketing_no_response": sum(
            1
            for c in period_conversations
            if get_enum_value(c.marketing_status) == MarketingStatus.NO_RESPONSE.value
        ),
        "marketing_rejected": sum(
            1
            for c in period_conversations
            if get_enum_value(c.marketing_status) == MarketingStatus.REJECTED.value
        ),
        "period": period,
        "unique_end_users": unique_end_users,
    }

    from app.storage.postgres_crm import PostgresCRMStorage
    crm_storage = PostgresCRMStorage()
    stats["crm_stage_stats"] = await crm_storage.get_stage_counts(
        start_date=start_date, end_date=end_date
    )

    if include_comparison:
        if period == "today":
            prev_start = start_date - timedelta(days=1)
            prev_end = start_date
        elif period == "last_7_days":
            prev_start = start_date - timedelta(days=7)
            prev_end = start_date
        else:
            prev_start = start_date - timedelta(days=30)
            prev_end = start_date

        prev_conversations = []
        for c in all_conversations:
            if not c.created_at:
                continue
            created_dt = None
            if isinstance(c.created_at, datetime):
                created_dt = c.created_at
            elif isinstance(c.created_at, str):
                try:
                    created_dt = parse_utc_datetime(c.created_at)
                except (ValueError, AttributeError):
                    continue
            if created_dt is None:
                continue
            if created_dt.tzinfo is None:
                created_dt = created_dt.replace(tzinfo=tz.utc)
            _ps = prev_start.replace(tzinfo=tz.utc) if prev_start.tzinfo is None else prev_start
            _pe = prev_end.replace(tzinfo=tz.utc) if prev_end.tzinfo is None else prev_end
            if _ps <= created_dt < _pe:
                prev_conversations.append(c)

        prev_stats = {
            "total_conversations": len(prev_conversations),
            "ai_active": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.status) == ConversationStatus.AI_ACTIVE.value
            ),
            "needs_human": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.status) == ConversationStatus.NEEDS_HUMAN.value
            ),
            "human_active": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.status) == ConversationStatus.HUMAN_ACTIVE.value
            ),
            "closed": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.status) == ConversationStatus.CLOSED.value
            ),
            "marketing_new": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.marketing_status) == MarketingStatus.NEW.value
            ),
            "marketing_booked": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.marketing_status) == MarketingStatus.BOOKED.value
            ),
            "marketing_no_response": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.marketing_status) == MarketingStatus.NO_RESPONSE.value
            ),
            "marketing_rejected": sum(
                1
                for c in prev_conversations
                if get_enum_value(c.marketing_status) == MarketingStatus.REJECTED.value
            ),
        }

        stats["comparison"] = {
            "total_conversations": stats["total_conversations"] - prev_stats["total_conversations"],
            "ai_active": stats["ai_active"] - prev_stats["ai_active"],
            "needs_human": stats["needs_human"] - prev_stats["needs_human"],
            "human_active": stats["human_active"] - prev_stats["human_active"],
            "closed": stats["closed"] - prev_stats["closed"],
            "marketing_new": stats["marketing_new"] - prev_stats["marketing_new"],
            "marketing_booked": stats["marketing_booked"] - prev_stats["marketing_booked"],
            "marketing_no_response": stats["marketing_no_response"] - prev_stats["marketing_no_response"],
            "marketing_rejected": stats["marketing_rejected"] - prev_stats["marketing_rejected"],
        }

    return stats


# ── Channel configuration (in-scope channels only; no WhatsApp / VK / MAX) ────

@router.get("/channel-config")
async def get_channel_config(_admin: str = require_admin()):
    """Return webhook URLs and verify tokens for supported channels (admin only)."""
    settings = get_settings()
    base = settings.app_url.rstrip("/") if settings.app_url else ""

    ig_verify_token = settings.instagram_webhook_verify_token or ""
    ig_app_secret_set = bool(settings.instagram_app_secret)

    if settings.secret_encryption_key:
        try:
            from app.storage.postgres_secrets import get_postgres_secrets_manager
            mgr = get_postgres_secrets_manager()

            db_ig_token = await mgr.get_global_setting("instagram_verify_token")
            if db_ig_token:
                ig_verify_token = db_ig_token
            ig_app_secret_set = (
                (await mgr.get_global_setting("instagram_app_secret")) is not None
                or bool(settings.instagram_app_secret)
            )
        except Exception as e:
            logger.warning(f"channel-config: could not read DB settings: {e}")

    return {
        "app_url": base,
        "instagram_webhook_url": f"{base}/api/v1/instagram/webhook",
        "instagram_verify_token": ig_verify_token,
        "instagram_app_secret_configured": ig_app_secret_set,
        "telegram_webhook_base": f"{base}/api/v1/telegram/webhook",
        "viber_webhook_base": f"{base}/api/v1/viber/webhook",
        "tiktok_webhook_base": f"{base}/api/v1/tiktok/webhook",
        "tiktok_messaging_enabled": bool(settings.tiktok_messaging_enabled),
        "instagram_oauth_available": bool(settings.instagram_app_id),
        "tiktok_oauth_available": bool(settings.tiktok_app_id),
    }


@router.get("/channel-support-matrix")
async def get_channel_support_matrix(_admin: str = require_admin()):
    """Read-only per-channel capability matrix (admin only)."""
    from app.services.channel_support_matrix import get_channel_support_matrix_payload

    settings = get_settings()
    return get_channel_support_matrix_payload(
        tiktok_messaging_enabled=bool(settings.tiktok_messaging_enabled),
    )


class ChannelSettingsRequest(BaseModel):
    verify_token: Optional[str] = Field(None, min_length=4, max_length=256)
    app_secret: Optional[str] = Field(None, max_length=512)


@router.put("/instagram-settings")
async def update_instagram_settings(
    body: ChannelSettingsRequest,
    _admin: str = require_admin(),
):
    """Save Instagram app-level settings (verify token + app secret) to the DB."""
    from app.storage.postgres_secrets import get_postgres_secrets_manager
    mgr = get_postgres_secrets_manager()

    if body.verify_token is not None:
        await mgr.set_global_setting("instagram_verify_token", body.verify_token)
    if body.app_secret is not None:
        await mgr.set_global_setting("instagram_app_secret", body.app_secret)

    return {"message": "Instagram settings updated successfully"}
