"""Instagram user profile model."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.utils.datetime_utils import to_utc_iso_string, utc_now


class InstagramUserProfile(BaseModel):
    """Instagram user profile information."""

    external_user_id: str = Field(..., description="Instagram-scoped ID (IGSID)")
    name: Optional[str] = Field(None, description="User's display name")
    username: Optional[str] = Field(None, description="Instagram username")
    profile_pic: Optional[str] = Field(None, description="Profile picture URL (expires in few days)")
    updated_at: datetime = Field(default_factory=utc_now, description="Last update timestamp")
    ttl: int = Field(..., description="TTL timestamp (updated_at + 5 days)")

    class Config:
        """Pydantic config."""

        json_encoders = {datetime: lambda v: to_utc_iso_string(v) if v else None}
