"""PostgreSQL storage for Instagram user profiles."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from app.models.instagram_user_profile import InstagramUserProfile
from app.storage.postgres import get_pool
from app.utils.datetime_utils import to_utc_iso_string

logger = logging.getLogger(__name__)


def _calculate_profile_ttl(base_time: datetime) -> int:
    return int((base_time + timedelta(days=5)).timestamp())


class PostgresInstagramProfileStorage:
    """CRUD operations for Instagram user profiles."""

    async def create_or_update_instagram_profile(
        self, profile: InstagramUserProfile
    ) -> InstagramUserProfile:
        ttl = _calculate_profile_ttl(profile.updated_at)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO instagram_profiles (external_user_id, name, username, profile_pic, updated_at, ttl)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (external_user_id) DO UPDATE SET
                    name = EXCLUDED.name, username = EXCLUDED.username, profile_pic = EXCLUDED.profile_pic,
                    updated_at = EXCLUDED.updated_at, ttl = EXCLUDED.ttl
                """,
                profile.external_user_id,
                profile.name,
                profile.username,
                profile.profile_pic,
                profile.updated_at,
                ttl,
            )
        return profile

    async def get_instagram_profile(self, external_user_id: str) -> Optional[InstagramUserProfile]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM instagram_profiles WHERE external_user_id = $1",
                external_user_id,
            )
        if not row:
            return None
        d = dict(row)
        if d.get("updated_at") and isinstance(d["updated_at"], datetime):
            d["updated_at"] = to_utc_iso_string(d["updated_at"])
        return InstagramUserProfile(**d)
