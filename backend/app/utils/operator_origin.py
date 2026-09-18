"""Public frontend origin for operator (human) post-OAuth redirects."""

from typing import Any


def operator_origin(settings: Any) -> str:
    """FRONTEND_URL, else first non-wildcard CORS origin, else APP_URL.

    Trailing slashes are stripped. Works with DummySettings via getattr.
    """
    frontend = getattr(settings, "frontend_url", None)
    if isinstance(frontend, str) and frontend.strip():
        return frontend.strip().rstrip("/")

    cors = getattr(settings, "cors_origins", None)
    if cors:
        origins = [cors] if isinstance(cors, str) else list(cors)
        for origin in origins:
            text = str(origin).strip().rstrip("/")
            if text and text != "*":
                return text

    app_url = getattr(settings, "app_url", None) or ""
    return str(app_url).rstrip("/")
