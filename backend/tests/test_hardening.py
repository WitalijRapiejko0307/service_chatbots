"""Support matrix, rate-limit exemptions, log redaction, production encryption."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.middleware import RateLimitMiddleware, is_rate_limit_exempt, safe_query_params_for_log
from app.services.channel_support_matrix import (
    CHANNEL_SUPPORT_MATRIX,
    get_channel_support_matrix_payload,
)
from app.storage.postgres_secrets import require_production_encryption_key
from app.utils.logging_config import redact_secrets
from tests.conftest import DummySettings


def test_channel_support_matrix_matches_json_file():
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "configs" / "channel-support-matrix.json",
        Path("/app/configs/channel-support-matrix.json"),
        Path("/configs/channel-support-matrix.json"),
    ]
    json_path = next((p for p in candidates if p.is_file()), None)
    payload = get_channel_support_matrix_payload(tiktok_messaging_enabled=False)
    assert payload["tiktok_messaging_enabled"] is False
    assert "whatsapp" not in payload["channels"]
    assert "vk" not in payload["channels"]
    assert "max" not in payload["channels"]
    assert payload["matrix"] == CHANNEL_SUPPORT_MATRIX
    if json_path is not None:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["matrix"] == CHANNEL_SUPPORT_MATRIX


def test_rate_limit_exempt_paths():
    assert is_rate_limit_exempt("/health") is True
    assert is_rate_limit_exempt("/health/") is True
    assert is_rate_limit_exempt("/api/v1/telegram/webhook") is True
    assert is_rate_limit_exempt("/api/v1/telegram/webhook/abc") is True
    assert is_rate_limit_exempt("/api/v1/viber/webhook/abc") is True
    assert is_rate_limit_exempt("/api/v1/instagram/webhook") is True
    assert is_rate_limit_exempt("/api/v1/tiktok/webhook/abc") is True
    assert is_rate_limit_exempt("/api/v1/admin/channel-config") is False
    assert is_rate_limit_exempt("/api/v1/agents") is False


def test_webhook_and_health_not_rate_limited():
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, requests_per_minute=1)

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/api/v1/telegram/webhook/abc")
    def tg():
        return {"ok": True}

    @app.get("/api/v1/admin/ping")
    def ping():
        return {"ok": True}

    with patch("app.storage.redis.get_redis_client") as get_redis:
        client_mock = AsyncMock()
        client_mock.ping = AsyncMock(return_value=False)
        get_redis.return_value = client_mock
        http = TestClient(app)
        assert http.get("/health").status_code == 200
        assert http.get("/health").status_code == 200
        assert http.post("/api/v1/telegram/webhook/abc").status_code == 200
        assert http.post("/api/v1/telegram/webhook/abc").status_code == 200
        assert http.get("/api/v1/admin/ping").status_code == 200
        assert http.get("/api/v1/admin/ping").status_code == 429


def test_redact_secrets_masks_bot_token_and_oauth_code():
    token = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz012345"
    raw = f"bot={token} code=oauth-code-xyz access_token=act.secret"
    redacted = redact_secrets(raw)
    assert token not in redacted
    assert "oauth-code-xyz" not in redacted
    assert "act.secret" not in redacted
    assert "***" in redacted


def test_oauth_query_string_omitted_from_logs():
    class _QP:
        def multi_items(self):
            return [("code", "abc"), ("state", "s1")]

    assert safe_query_params_for_log("/api/v1/instagram/oauth/callback", _QP()) == ""
    assert "code=***" in safe_query_params_for_log("/api/v1/admin/x", _QP())


def test_production_requires_encryption_key():
    settings = DummySettings()
    settings.environment = "production"
    settings.secret_encryption_key = None
    with pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY"):
        require_production_encryption_key(settings)

    settings.secret_encryption_key = "not-a-fernet-key"
    with pytest.raises(RuntimeError, match="SECRET_ENCRYPTION_KEY"):
        require_production_encryption_key(settings)


def test_dev_allows_missing_encryption_key():
    settings = DummySettings()
    settings.environment = "development"
    settings.secret_encryption_key = None
    require_production_encryption_key(settings)


def test_production_accepts_valid_fernet_key():
    settings = DummySettings()
    settings.environment = "PRODUCTION"
    settings.secret_encryption_key = Fernet.generate_key().decode()
    require_production_encryption_key(settings)
