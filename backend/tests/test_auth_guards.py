"""Fail-closed auth guards — super-admin list and DEBUG bypass."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

import app.api.auth as auth_module
from app.api.auth import get_current_admin, is_super_admin_email, require_super_admin
from app.api.v1.auth_router import get_me


class AuthSettings:
    debug = True
    environment = "development"
    jwt_secret_key = None
    admin_token = None


@pytest.fixture(autouse=True)
def reset_super_admin_warning_flag():
    auth_module._warned_empty_super_admin_list = False
    yield
    auth_module._warned_empty_super_admin_list = False


@pytest.mark.asyncio
async def test_require_super_admin_denies_when_list_empty(monkeypatch):
    monkeypatch.setattr("app.api.auth.get_super_admin_emails", lambda: [])
    with pytest.raises(HTTPException) as exc:
        await require_super_admin(current_user="any@example.com")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Super admin access required"


@pytest.mark.asyncio
async def test_require_super_admin_allows_when_email_in_list(monkeypatch):
    monkeypatch.setattr(
        "app.api.auth.get_super_admin_emails",
        lambda: ["admin@example.com"],
    )
    result = await require_super_admin(current_user="Admin@Example.com")
    assert result == "Admin@Example.com"


@pytest.mark.asyncio
async def test_require_super_admin_denies_when_email_not_in_list(monkeypatch):
    monkeypatch.setattr(
        "app.api.auth.get_super_admin_emails",
        lambda: ["admin@example.com"],
    )
    with pytest.raises(HTTPException) as exc:
        await require_super_admin(current_user="other@example.com")
    assert exc.value.status_code == 403
    assert exc.value.detail == "Super admin access required"


def test_is_super_admin_email_false_when_list_empty(monkeypatch):
    monkeypatch.setattr("app.api.auth.get_super_admin_emails", lambda: [])
    assert is_super_admin_email("any@example.com") is False


@pytest.mark.asyncio
async def test_get_me_reports_not_super_admin_when_list_empty(monkeypatch):
    monkeypatch.setattr("app.api.auth.get_super_admin_emails", lambda: [])
    response = await get_me(current_user="any@example.com")
    assert response.email == "any@example.com"
    assert response.is_super_admin is False


@pytest.mark.asyncio
async def test_debug_bypass_blocked_in_production(monkeypatch):
    settings = AuthSettings()
    settings.debug = True
    settings.environment = "production"
    monkeypatch.setattr("app.api.auth.get_settings", lambda: settings)

    with pytest.raises(HTTPException) as exc:
        await get_current_admin(credentials=None)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Authentication required"


@pytest.mark.asyncio
async def test_debug_bypass_allowed_in_development(monkeypatch):
    settings = AuthSettings()
    settings.debug = True
    settings.environment = "development"
    monkeypatch.setattr("app.api.auth.get_settings", lambda: settings)

    user = await get_current_admin(credentials=None)
    assert user == "admin_user"


def test_empty_super_admin_list_logs_warning_once(monkeypatch):
    monkeypatch.setattr("app.api.auth.get_super_admin_emails", lambda: [])

    with patch.object(auth_module.logger, "warning") as warning_mock:
        assert is_super_admin_email("a@example.com") is False
        assert is_super_admin_email("b@example.com") is False

    warning_mock.assert_called_once()
    assert "ALLOWED_ADMIN_EMAILS" in warning_mock.call_args.args[0]
