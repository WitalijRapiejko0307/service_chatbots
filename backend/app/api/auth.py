"""Authentication and authorization utilities."""

import logging
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import get_settings
from app.services.otp_service import get_super_admin_emails

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

_warned_empty_super_admin_list = False


def _is_dev_auth_bypass_allowed(settings) -> bool:
    """Allow unauthenticated dev access only outside production."""
    if not settings.debug:
        return False
    env = str(getattr(settings, "environment", "") or "").lower()
    return env != "production"


def _warn_empty_super_admin_list() -> None:
    global _warned_empty_super_admin_list
    if _warned_empty_super_admin_list:
        return
    _warned_empty_super_admin_list = True
    logger.warning(
        "ALLOWED_ADMIN_EMAILS is not configured; super-admin functions are unavailable to all users."
    )


def is_super_admin_email(email: str) -> bool:
    """Return True when email is in ALLOWED_ADMIN_EMAILS (case-insensitive)."""
    allowed = get_super_admin_emails()
    if not allowed:
        _warn_empty_super_admin_list()
        return False
    return email.lower() in allowed


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """Authenticate admin via JWT (primary) or static ADMIN_TOKEN (fallback/dev)."""
    settings = get_settings()

    if not credentials:
        admin_token = getattr(settings, "admin_token", None)
        if not admin_token:
            # Allow unauthenticated access only in non-production debug/dev mode.
            if _is_dev_auth_bypass_allowed(settings):
                return "admin_user"
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # 1. Try JWT verification
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
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            pass

    # 2. Fallback: static ADMIN_TOKEN (backward compat / dev mode)
    admin_token = getattr(settings, "admin_token", None)
    if admin_token and token == admin_token:
        return "admin_user"

    # 3. Dev mode: no token configured — allow access only outside production
    if not settings.jwt_secret_key and not admin_token and _is_dev_auth_bypass_allowed(settings):
        return "admin_user"

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid authentication credentials",
    )


async def require_super_admin(
    current_user: str = Depends(get_current_admin),
) -> str:
    """Dependency that allows access only to super admins (from ALLOWED_ADMIN_EMAILS)."""
    if not is_super_admin_email(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin access required",
        )
    return current_user


def require_admin():
    """Dependency to require admin authentication."""
    return Depends(get_current_admin)
