"""Minimal demo authentication: hardcoded users loaded from data/users.json and an
in-memory session store (no database, no persistence across process restarts).

This is intentionally simple for a capstone demo. It is NOT production-grade auth:
passwords are stored in plaintext in a JSON file and sessions live only in memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
import threading

from app.config import DATA_DIR

_USERS_PATH = DATA_DIR / "users.json"

_SESSIONS_LOCK = threading.Lock()
_SESSIONS: dict[str, "SessionInfo"] = {}


@dataclass
class SessionInfo:
    token: str
    username: str
    role: str
    display_name: str
    scope: str | None


def _load_users() -> list[dict[str, object]]:
    with _USERS_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    users = payload.get("users", [])
    return users if isinstance(users, list) else []


def authenticate(username: str, password: str) -> SessionInfo | None:
    username = username.strip()
    if not username or not password:
        return None

    for user in _load_users():
        if str(user.get("username", "")) == username and str(user.get("password", "")) == password:
            token = secrets.token_urlsafe(24)
            session = SessionInfo(
                token=token,
                username=username,
                role=str(user.get("role", "")).strip().lower(),
                display_name=str(user.get("display_name", username)),
                scope=user.get("scope") if isinstance(user.get("scope"), str) else None,
            )
            with _SESSIONS_LOCK:
                _SESSIONS[token] = session
            return session
    return None


def get_session(token: str | None) -> SessionInfo | None:
    if not token:
        return None
    with _SESSIONS_LOCK:
        return _SESSIONS.get(token.strip())


def end_session(token: str | None) -> None:
    if not token:
        return
    with _SESSIONS_LOCK:
        _SESSIONS.pop(token.strip(), None)


__all__ = ["SessionInfo", "authenticate", "get_session", "end_session"]
