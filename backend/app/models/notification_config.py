"""Notification configuration models."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.utils.datetime_utils import to_utc_iso_string, utc_now


class NotificationType(str, Enum):
    """Notification type enumeration."""

    TELEGRAM = "telegram"


class NotificationConfig(BaseModel):
    """Notification configuration model."""

    config_id: str = Field(..., description="Unique notification config identifier (UUID)")
    notification_type: NotificationType = Field(
        ..., description="Type of notification channel"
    )
    bot_token_secret_name: Optional[str] = Field(
        default=None,
        description="Name of secret in AWS Secrets Manager, or config_id for PostgreSQL",
    )
    encrypted_bot_token: Optional[str] = Field(
        default=None,
        description="Encrypted bot token (PostgreSQL backend only)",
    )
    chat_id: str = Field(..., description="Telegram chat ID for receiving notifications")
    is_active: bool = Field(
        default=True, description="Whether notification config is active"
    )
    description: Optional[str] = Field(
        None, description="Optional description for admin reference"
    )
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    created_by: Optional[str] = Field(
        None, description="Admin user ID who created the config"
    )

    class Config:
        """Pydantic config."""

        use_enum_values = True
        json_encoders = {datetime: lambda v: to_utc_iso_string(v) if v else None}
