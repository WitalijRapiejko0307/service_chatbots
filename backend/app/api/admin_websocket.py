"""Admin WebSocket handler for real-time admin dashboard updates."""

import asyncio
import json
import logging
from typing import Dict, Optional

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import HTTPException

from app.config import get_settings
from app.models.conversation import Conversation
from app.utils.datetime_utils import to_utc_iso_string, utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)

router = APIRouter()

# Heartbeat interval (seconds)
HEARTBEAT_INTERVAL = 25
HEARTBEAT_TIMEOUT = 5


class AdminBroadcastManager:
    """Manages WebSocket connections for admin dashboard."""

    def __init__(self):
        """Initialize admin broadcast manager."""
        self.active_connections: Dict[str, WebSocket] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, websocket: WebSocket, admin_id: str) -> None:
        """Accept and store admin WebSocket connection."""
        await websocket.accept()
        self.active_connections[admin_id] = websocket

        # Start heartbeat task
        self.heartbeat_tasks[admin_id] = asyncio.create_task(
            self._heartbeat_loop(admin_id)
        )

        logger.info(f"Admin WebSocket connected: admin_id={admin_id}")

    async def disconnect(self, admin_id: str) -> None:
        """Remove admin WebSocket connection."""
        if admin_id in self.active_connections:
            del self.active_connections[admin_id]

        # Cancel heartbeat task
        if admin_id in self.heartbeat_tasks:
            self.heartbeat_tasks[admin_id].cancel()
            try:
                await self.heartbeat_tasks[admin_id]
            except asyncio.CancelledError:
                pass
            del self.heartbeat_tasks[admin_id]

        logger.info(f"Admin WebSocket disconnected: admin_id={admin_id}")

    async def broadcast_conversation_update(self, conversation: Conversation) -> None:
        """Broadcast conversation status update to all connected admins."""
        message = {
            "type": "conversation_updated",
            "conversation": {
                "conversation_id": conversation.conversation_id,
                "agent_id": conversation.agent_id,
                "status": get_enum_value(conversation.status),
                "created_at": (
                    to_utc_iso_string(conversation.created_at)
                    if hasattr(conversation.created_at, "isoformat")
                    else str(conversation.created_at)
                ),
                "updated_at": (
                    to_utc_iso_string(conversation.updated_at)
                    if hasattr(conversation.updated_at, "isoformat")
                    else str(conversation.updated_at)
                ),
                "closed_at": (
                    to_utc_iso_string(conversation.closed_at)
                    if conversation.closed_at
                    and hasattr(conversation.closed_at, "isoformat")
                    else (str(conversation.closed_at) if conversation.closed_at else None)
                ),
                "handoff_reason": conversation.handoff_reason,
                "request_type": conversation.request_type,
                "agent_context_reset_at": (
                    to_utc_iso_string(conversation.agent_context_reset_at)
                    if conversation.agent_context_reset_at
                    else None
                ),
            },
            "timestamp": to_utc_iso_string(utc_now()),
        }
        await self._broadcast(message)

    async def broadcast_new_escalation(
        self, conversation: Conversation, escalation_reason: Optional[str] = None
    ) -> None:
        """Broadcast new escalation (NEEDS_HUMAN) to all connected admins."""
        message = {
            "type": "conversation_escalated",
            "conversation": {
                "conversation_id": conversation.conversation_id,
                "agent_id": conversation.agent_id,
                "status": get_enum_value(conversation.status),
                "created_at": (
                    to_utc_iso_string(conversation.created_at)
                    if hasattr(conversation.created_at, "isoformat")
                    else str(conversation.created_at)
                ),
                "updated_at": (
                    to_utc_iso_string(conversation.updated_at)
                    if hasattr(conversation.updated_at, "isoformat")
                    else str(conversation.updated_at)
                ),
                "handoff_reason": conversation.handoff_reason,
                "request_type": conversation.request_type,
                "agent_context_reset_at": (
                    to_utc_iso_string(conversation.agent_context_reset_at)
                    if conversation.agent_context_reset_at
                    else None
                ),
            },
            "escalation_reason": escalation_reason or conversation.handoff_reason,
            "timestamp": to_utc_iso_string(utc_now()),
        }
        await self._broadcast(message)

    async def broadcast_stats_update(self, stats: dict) -> None:
        """Broadcast statistics update to all connected admins."""
        message = {
            "type": "stats_updated",
            "stats": stats,
            "timestamp": to_utc_iso_string(utc_now()),
        }
        await self._broadcast(message)

    async def _broadcast(self, message: dict) -> None:
        """Broadcast message to all connected admins."""
        if not self.active_connections:
            return

        disconnected_admins = []
        for admin_id, websocket in self.active_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(
                    f"Failed to send message to admin {admin_id}: {e}",
                    exc_info=True,
                )
                disconnected_admins.append(admin_id)

        # Clean up disconnected admins
        for admin_id in disconnected_admins:
            await self.disconnect(admin_id)

    async def _heartbeat_loop(self, admin_id: str) -> None:
        """Send periodic ping messages."""
        try:
            while admin_id in self.active_connections:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if admin_id in self.active_connections:
                    try:
                        await self.active_connections[admin_id].send_json(
                            {"type": "ping", "timestamp": None}
                        )
                    except Exception:
                        break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat error for admin {admin_id}: {e}")

    def is_connected(self, admin_id: str) -> bool:
        """Check if admin has active connection."""
        return admin_id in self.active_connections


# Global admin broadcast manager instance
admin_broadcast_manager = AdminBroadcastManager()


def get_admin_broadcast_manager() -> AdminBroadcastManager:
    """Get global admin broadcast manager instance."""
    return admin_broadcast_manager


async def verify_admin_token(token: Optional[str]) -> str:
    """Verify JWT (primary) or static ADMIN_TOKEN (fallback/dev); return admin_id.

    Mirrors ``app.api.auth.get_current_admin`` so the inbox WS accepts the same
    token the frontend stores after login (query ``?token=...``).
    """
    settings = get_settings()
    admin_token = getattr(settings, "admin_token", None)

    if not token:
        if not admin_token:
            if settings.debug:
                return "admin_user"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    if settings.jwt_secret_key:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=["HS256"],
            )
            email: str = payload.get("sub", "admin_user")
            return email
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Please log in again.",
            )
        except jwt.InvalidTokenError:
            pass

    if admin_token and token == admin_token:
        return "admin_user"

    if not settings.jwt_secret_key and not admin_token and settings.debug:
        return "admin_user"

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid authentication credentials",
    )


@router.websocket("/ws/admin")
async def admin_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for admin dashboard real-time updates."""
    query_params = dict(websocket.query_params)
    token = query_params.get("token")

    try:
        admin_id = await verify_admin_token(token)
    except HTTPException as e:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=e.detail)
        return

    await admin_broadcast_manager.connect(websocket, admin_id)

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "admin_id": admin_id,
                "timestamp": to_utc_iso_string(utc_now()),
            }
        )

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_text(), timeout=HEARTBEAT_TIMEOUT + 10
                )
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "timestamp": None})
                continue

            try:
                message_data = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": to_utc_iso_string(utc_now()),
                    }
                )
                continue

            message_type = message_data.get("type")

            if message_type == "pong":
                continue
            elif message_type == "ping":
                await websocket.send_json({"type": "pong", "timestamp": None})
            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"Unknown message type: {message_type}",
                        "timestamp": to_utc_iso_string(utc_now()),
                    }
                )

    except WebSocketDisconnect:
        logger.info(f"Admin WebSocket disconnected: admin_id={admin_id}")
    except Exception as e:
        logger.error(
            f"Admin WebSocket error for {admin_id}: {e}",
            exc_info=True,
        )
    finally:
        await admin_broadcast_manager.disconnect(admin_id)
