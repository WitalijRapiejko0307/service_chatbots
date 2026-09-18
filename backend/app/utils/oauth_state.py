"""Signed OAuth `state` helpers (CSRF + agent binding)."""

import hashlib
import hmac
from typing import Optional


def make_oauth_state(agent_id: str, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), agent_id.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    return f"{agent_id}:{digest}"


def parse_oauth_state(state: str, secret: str) -> Optional[str]:
    if ":" not in state:
        return None
    agent_id, digest = state.split(":", 1)
    expected = hmac.new(secret.encode("utf-8"), agent_id.encode("utf-8"), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(digest, expected):
        return None
    return agent_id
