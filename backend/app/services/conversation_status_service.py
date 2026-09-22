"""Conversation updates with admin broadcast and escalation notifications."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from app.models.conversation import Conversation, ConversationStatus
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)


class ConversationStatusService:
    """Apply conversation updates and run transport/notification side effects."""

    def __init__(
        self,
        db: Any,
        *,
        broadcast_manager: Any = None,
        notification_service_factory: Optional[Callable[[], Any]] = None,
    ):
        self.db = db
        self._broadcast_manager = broadcast_manager
        self._notification_service_factory = notification_service_factory

    def _get_broadcast_manager(self) -> Any:
        if self._broadcast_manager is not None:
            return self._broadcast_manager
        from app.api.admin_websocket import get_admin_broadcast_manager

        return get_admin_broadcast_manager()

    def _create_notification_service(self) -> Any:
        if self._notification_service_factory is not None:
            return self._notification_service_factory()
        from app.config import get_settings
        from app.services.notification_service import NotificationService
        from app.storage.postgres_secrets import get_postgres_secrets_manager

        return NotificationService(
            db=self.db,
            secrets_manager=get_postgres_secrets_manager(),
            telegram_service=None,
        )

    async def update_conversation(
        self,
        conversation_id: str,
        status: Optional[ConversationStatus] = None,
        handoff_reason: Optional[str] = None,
        request_type: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[Conversation]:
        """Persist conversation changes and broadcast/notify when appropriate."""
        old = await self.db.get_conversation(conversation_id)
        old_status = get_enum_value(old.status) if old else None

        update_params: dict[str, Any] = dict(kwargs)
        if status:
            update_params["status"] = status
        if handoff_reason is not None:
            update_params["handoff_reason"] = handoff_reason
        if request_type is not None:
            update_params["request_type"] = request_type

        updated = await self.db.update_conversation(
            conversation_id,
            **update_params,
        )
        if updated:
            await self._handle_side_effects(
                updated,
                old_status=old_status,
                status=status,
                handoff_reason=handoff_reason,
            )
        return updated

    async def _handle_side_effects(
        self,
        updated: Conversation,
        *,
        old_status: Optional[str],
        status: Optional[ConversationStatus],
        handoff_reason: Optional[str],
    ) -> None:
        try:
            broadcast_manager = self._get_broadcast_manager()
            if (
                status
                and status == ConversationStatus.NEEDS_HUMAN
                and (old_status is None or old_status != ConversationStatus.NEEDS_HUMAN.value)
            ):
                await broadcast_manager.broadcast_new_escalation(updated, handoff_reason)
                try:
                    from app.config import get_settings
                    from app.models.agent_config import AgentConfig

                    notification_service = self._create_notification_service()
                    settings = get_settings()
                    agent_data = await self.db.get_agent(updated.agent_id)
                    agent_display_name = "Unknown Agent"
                    if agent_data and "config" in agent_data:
                        agent_config = AgentConfig.from_dict(agent_data["config"])
                        agent_display_name = agent_config.profile.agent_display_name
                    asyncio.create_task(
                        notification_service.send_escalation_notification(
                            conversation=updated,
                            escalation_reason=handoff_reason or "Escalation required",
                            agent_display_name=agent_display_name,
                            admin_panel_base_url=settings.app_url or None,
                        )
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to send escalation notifications: %s",
                        exc,
                        exc_info=True,
                    )
            else:
                await broadcast_manager.broadcast_conversation_update(updated)
        except Exception as exc:
            logger.warning("Failed to broadcast: %s", exc, exc_info=True)


def create_conversation_status_service(db: Any) -> ConversationStatusService:
    """Factory for the default conversation status service."""
    return ConversationStatusService(db)


async def update_conversation_with_notifications(
    db: Any,
    conversation_id: str,
    *,
    status: Optional[ConversationStatus] = None,
    handoff_reason: Optional[str] = None,
    request_type: Optional[str] = None,
    **kwargs: Any,
) -> Optional[Conversation]:
    """Convenience wrapper used by callers that expect storage side effects."""
    service = create_conversation_status_service(db)
    return await service.update_conversation(
        conversation_id,
        status=status,
        handoff_reason=handoff_reason,
        request_type=request_type,
        **kwargs,
    )
