"""Channel binding service."""

import logging
import uuid
from typing import Any, Optional

from app.models.channel_binding import ChannelBinding, ChannelType
from app.storage.secrets import SecretsManager
from app.utils.datetime_utils import utc_now
from app.utils.enum_helpers import get_enum_value

logger = logging.getLogger(__name__)


def _secret_and_db_metadata(metadata: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep refresh_token in the secrets payload; never persist it on the binding row."""
    secret_meta = dict(metadata)
    db_meta = dict(metadata)
    db_meta.pop("refresh_token", None)
    return secret_meta, db_meta


class ChannelBindingService:
    """Service for managing channel bindings."""

    def __init__(
        self,
        db: Any,
        secrets_manager: SecretsManager,
    ):
        """Initialize channel binding service."""
        self.db = db
        self.secrets_manager = secrets_manager

    async def create_binding(
        self,
        agent_id: str,
        channel_type: str,
        channel_account_id: str,
        access_token: str,
        metadata: dict[str, Any],
        created_by: Optional[str] = None,
        channel_username: Optional[str] = None,
    ) -> ChannelBinding:
        """Create a new channel binding."""
        binding_id = str(uuid.uuid4())

        merged_metadata = dict(metadata or {})
        if channel_type == ChannelType.TIKTOK.value:
            from app.config import get_settings

            if not get_settings().tiktok_messaging_enabled:
                merged_metadata.setdefault("pending_access", True)

        secret_metadata, db_metadata = _secret_and_db_metadata(merged_metadata)

        secret_name = await self.secrets_manager.create_channel_token_secret(
            binding_id=binding_id,
            channel_type=channel_type,
            access_token=access_token,
            metadata=secret_metadata,
        )

        # Create binding record in the database
        binding = ChannelBinding(
            binding_id=binding_id,
            agent_id=agent_id,
            channel_type=ChannelType(channel_type),
            channel_account_id=channel_account_id,
            channel_username=channel_username,
            secret_name=secret_name,
            is_active=True,
            is_verified=False,
            metadata=db_metadata,
            created_by=created_by,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        await self.db.create_channel_binding(binding)

        logger.info(
            f"Created channel binding: {binding_id} for agent {agent_id}, channel {channel_type}"
        )
        return binding

    async def get_binding(self, binding_id: str) -> Optional[ChannelBinding]:
        """Get channel binding by ID."""
        return await self.db.get_channel_binding(binding_id)

    async def get_bindings_by_agent(
        self,
        agent_id: str,
        channel_type: Optional[str] = None,
        active_only: bool = True,
    ) -> list[ChannelBinding]:
        """Get all channel bindings for an agent."""
        return await self.db.get_channel_bindings_by_agent(
            agent_id=agent_id,
            channel_type=channel_type,
            active_only=active_only,
        )

    async def list_bindings_by_channel(
        self,
        channel_type: str,
        active_only: bool = True,
    ) -> list[ChannelBinding]:
        """List bindings of a channel type across agents."""
        return await self.db.list_channel_bindings_by_channel(
            channel_type=channel_type,
            active_only=active_only,
        )

    async def get_binding_by_account_id(
        self, channel_type: str, account_id: str
    ) -> Optional[ChannelBinding]:
        """Get channel binding by channel account ID."""
        return await self.db.get_channel_binding_by_account_id(
            channel_type=channel_type, account_id=account_id
        )

    async def get_access_token(self, binding_id: str) -> str:
        """Get access token for a binding."""
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        if not binding.is_active:
            raise ValueError(f"Binding {binding_id} is not active")

        token = await self.secrets_manager.get_channel_token(binding.secret_name)
        return token

    async def update_binding(
        self,
        binding_id: str,
        is_active: Optional[bool] = None,
        access_token: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        is_verified: Optional[bool] = None,
    ) -> ChannelBinding:
        """Update channel binding."""
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        update_kwargs: dict[str, Any] = {}

        if is_active is not None:
            update_kwargs["is_active"] = is_active

        if is_verified is not None:
            update_kwargs["is_verified"] = is_verified

        if access_token is not None:
            # Update token in Secrets Manager
            current_metadata = binding.metadata.copy()
            if metadata:
                current_metadata.update(metadata)
            secret_metadata, db_metadata = _secret_and_db_metadata(current_metadata)
            await self.secrets_manager.update_channel_token(
                secret_name=binding.secret_name,
                access_token=access_token,
                metadata=secret_metadata,
            )
            # Mark as unverified if token was updated
            update_kwargs["is_verified"] = False
            if metadata is not None:
                update_kwargs["metadata"] = db_metadata

        if metadata is not None and access_token is None:
            # Update metadata without updating token
            current_metadata = binding.metadata.copy()
            current_metadata.update(metadata)
            secret_metadata, db_metadata = _secret_and_db_metadata(current_metadata)
            # Persist metadata to the DB column so reads via get_binding() see the update.
            update_kwargs["metadata"] = db_metadata
            # Also keep the Secrets Manager in sync (it stores token + metadata together).
            token = await self.secrets_manager.get_channel_token(binding.secret_name)
            await self.secrets_manager.update_channel_token(
                secret_name=binding.secret_name,
                access_token=token,
                metadata=secret_metadata,
            )

        if update_kwargs:
            await self.db.update_channel_binding(binding_id, **update_kwargs)

        # Return updated binding
        updated_binding = await self.get_binding(binding_id)
        if not updated_binding:
            raise RuntimeError(f"Failed to retrieve updated binding {binding_id}")

        logger.info(f"Updated channel binding: {binding_id}")
        return updated_binding

    async def delete_binding(self, binding_id: str) -> None:
        """Delete channel binding and its secret.

        Best-effort: unset the platform webhook first. Failures are logged without
        tokens and never block DB/secret delete.
        """
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        try:
            token = await self.secrets_manager.get_channel_token(binding.secret_name)
        except Exception as e:
            token = None
            logger.warning(
                "Could not load token before webhook unset for binding %s: %s",
                binding_id,
                type(e).__name__,
            )

        if token:
            await self._best_effort_unset_webhook(binding, token)

        # Delete secret from Secrets Manager
        try:
            await self.secrets_manager.delete_channel_token_secret(binding.secret_name)
        except Exception as e:
            logger.warning(f"Failed to delete secret for binding {binding_id}: {e}")

        # Delete binding from the database
        await self.db.delete_channel_binding(binding_id)

        logger.info(f"Deleted channel binding: {binding_id}")

    async def _best_effort_unset_webhook(self, binding: ChannelBinding, token: str) -> None:
        channel = get_enum_value(binding.channel_type)
        binding_id = binding.binding_id
        try:
            from app.config import get_settings

            settings = get_settings()
            if channel == ChannelType.TELEGRAM.value:
                from app.services.telegram_service import TelegramService

                svc = TelegramService(self, self.db, settings)
                await svc.delete_webhook(token, binding_id)
            elif channel == ChannelType.VIBER.value:
                from app.services.viber_service import ViberService

                svc = ViberService(self, self.db, settings)
                await svc.unset_webhook(token, binding_id)
            elif channel == ChannelType.TIKTOK.value:
                from app.services.tiktok_service import TikTokService

                svc = TikTokService(self, self.db, settings)
                await svc.unset_webhook(binding_id)
                if token:
                    await svc.revoke_access_token(token)
            # Instagram webhooks are app-level in Meta; nothing to unregister per binding.
        except Exception as e:
            logger.warning(
                "Failed to unset %s webhook for binding %s: %s",
                channel,
                binding_id,
                type(e).__name__,
            )

    async def verify_binding(self, binding_id: str) -> bool:
        """Verify binding by checking token validity via API."""
        binding = await self.get_binding(binding_id)
        if not binding:
            raise ValueError(f"Binding {binding_id} not found")

        channel = get_enum_value(binding.channel_type)

        if channel == ChannelType.INSTAGRAM.value:
            try:
                from app.config import get_settings
                from app.services.instagram_service import InstagramService

                settings = get_settings()
                instagram_service = InstagramService(self, self.db, settings)
                token = await self.get_access_token(binding_id)
                meta = dict(binding.metadata or {})
                if meta.get("connected_via") == "oauth":
                    refreshed = await instagram_service.refresh_long_lived_token(token)
                    if refreshed and refreshed.get("access_token"):
                        token = refreshed["access_token"]
                        if refreshed.get("token_expires_at"):
                            meta["token_expires_at"] = refreshed["token_expires_at"]
                        await self.update_binding(
                            binding_id, access_token=token, metadata=meta
                        )
                check = await instagram_service.verify_access_token_detailed(
                    token, binding.channel_account_id
                )
                latest = await self.get_binding(binding_id)
                meta = dict((latest.metadata if latest else {}) or {})
                if check.app_review_pending:
                    meta["app_review_pending"] = True
                elif check.ok:
                    meta.pop("app_review_pending", None)
                await self.update_binding(
                    binding_id, is_verified=check.ok, metadata=meta
                )
                return check.ok
            except Exception as e:
                logger.error("Failed to verify Instagram binding %s: %s", binding_id, e)
                await self.update_binding(binding_id, is_verified=False)
                return False

        if channel == ChannelType.TELEGRAM.value:
            try:
                from app.config import get_settings
                from app.services.telegram_service import TelegramService

                settings = get_settings()
                telegram_service = TelegramService(self, self.db, settings)
                bot_token = await self.get_access_token(binding_id)

                is_valid = await telegram_service.verify_bot_token(bot_token)
                if not is_valid:
                    await self.update_binding(binding_id, is_verified=False)
                    return False

                base = (settings.app_url or "").rstrip("/")
                webhook_url = f"{base}/api/v1/telegram/webhook/{binding_id}"
                webhook_set = await telegram_service.set_webhook(binding_id, webhook_url)
                metadata = dict(binding.metadata or {})
                metadata["webhook_url"] = webhook_url
                await self.update_binding(
                    binding_id, is_verified=True, metadata=metadata
                )
                if webhook_set:
                    logger.info(
                        "Telegram webhook set for binding %s: %s",
                        binding_id,
                        webhook_url,
                    )
                else:
                    logger.warning(
                        "Telegram token valid but setWebhook failed for binding %s",
                        binding_id,
                    )
                return True
            except Exception as e:
                logger.error("Failed to verify Telegram binding %s: %s", binding_id, e)
                await self.update_binding(binding_id, is_verified=False)
                return False

        if channel == ChannelType.VIBER.value:
            try:
                from app.config import get_settings
                from app.services.viber_service import ViberService

                settings = get_settings()
                viber_service = ViberService(self, self.db, settings)
                token = await self.get_access_token(binding_id)
                is_valid = await viber_service.verify_auth_token(token)
                if not is_valid:
                    await self.update_binding(binding_id, is_verified=False)
                    return False

                base = (settings.app_url or "").rstrip("/")
                webhook_url = f"{base}/api/v1/viber/webhook/{binding_id}"
                webhook_set = await viber_service.set_webhook(binding_id, webhook_url)
                metadata = dict(binding.metadata or {})
                metadata["webhook_url"] = webhook_url
                await self.update_binding(
                    binding_id, is_verified=True, metadata=metadata
                )
                if not webhook_set:
                    logger.warning(
                        "Viber token valid but set_webhook failed for binding %s "
                        "(APP_URL must be HTTPS in production)",
                        binding_id,
                    )
                return True
            except Exception as e:
                logger.error("Failed to verify Viber binding %s: %s", binding_id, e)
                await self.update_binding(binding_id, is_verified=False)
                return False

        if channel == ChannelType.TIKTOK.value:
            from app.config import get_settings
            from app.services.tiktok_service import TikTokService

            settings = get_settings()
            metadata = dict(binding.metadata or {})
            if not settings.tiktok_messaging_enabled:
                metadata["pending_access"] = True
                await self.update_binding(
                    binding_id, is_verified=False, metadata=metadata
                )
                logger.info(
                    "TikTok messaging disabled — binding %s marked pending_access",
                    binding_id,
                )
                return False

            try:
                tiktok_service = TikTokService(self, self.db, settings)
                token = await self.get_access_token(binding_id)
                is_valid = await tiktok_service.verify_access_token(token)
                base = (settings.app_url or "").rstrip("/")
                webhook_url = f"{base}/api/v1/tiktok/webhook/{binding_id}"
                metadata["webhook_url"] = webhook_url
                metadata["pending_access"] = not is_valid
                if is_valid:
                    await tiktok_service.set_webhook(binding_id, webhook_url)
                await self.update_binding(
                    binding_id, is_verified=is_valid, metadata=metadata
                )
                return is_valid
            except Exception as e:
                logger.error("Failed to verify TikTok binding %s: %s", binding_id, e)
                metadata["pending_access"] = True
                await self.update_binding(
                    binding_id, is_verified=False, metadata=metadata
                )
                return False

        return binding.is_active

