from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib import error, request as urlrequest

from dotenv import load_dotenv

ROOT_PATH = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_PATH / ".env", override=False)


class ReferralTriageMCPClientError(RuntimeError):
    pass


class ReferralTriageMCPClient:
    """Blocking HTTP MCP client for referral triage workflows."""

    def __init__(self, caller_role: str, user_role: str | None = None) -> None:
        self._caller_role = caller_role.strip().lower()
        self._user_role = user_role.strip().lower() if user_role else None
        self._internal_key = os.getenv("MCP_INTERNAL_KEY", "").strip()
        self._transport = os.getenv("MCP_TRANSPORT", "http").strip().lower()
        self._http_base_url = os.getenv("MCP_HTTP_BASE_URL", "http://127.0.0.1:8092").rstrip("/")

    def __enter__(self) -> "ReferralTriageMCPClient":
        if not self._caller_role:
            raise ReferralTriageMCPClientError("MCP caller role is required.")
        if not self._internal_key:
            raise ReferralTriageMCPClientError("MCP auth key missing. Set MCP_INTERNAL_KEY in .env.")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        payload = {
            **arguments,
            "caller_role": self._caller_role,
            "internal_key": self._internal_key,
        }
        if self._user_role:
            payload["user_role"] = self._user_role

        if self._transport != "http":
            raise ReferralTriageMCPClientError("Only HTTP transport is supported for MCP calls. Set MCP_TRANSPORT=http.")
        return self._call_tool_http(name, payload)

    def _call_tool_http(self, name: str, payload: dict[str, Any]) -> Any:
        endpoint = f"{self._http_base_url}/api/v1/mcp/call"
        body = json.dumps({"tool_name": name, "arguments": payload}).encode("utf-8")
        req = urlrequest.Request(
            endpoint,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlrequest.urlopen(req, timeout=20) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise ReferralTriageMCPClientError(f"MCP HTTP call failed for tool '{name}': {detail or exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise ReferralTriageMCPClientError(f"MCP HTTP call failed for tool '{name}': {exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ReferralTriageMCPClientError(f"MCP HTTP tool '{name}' returned invalid JSON response.") from exc

        if not isinstance(parsed, dict) or "result" not in parsed:
            raise ReferralTriageMCPClientError(f"MCP HTTP tool '{name}' returned invalid payload.")
        return parsed["result"]

    def triage_assess(self, diagnosis: str, urgency_hint: str = "") -> dict[str, Any]:
        result = self._call_tool(
            "triage_assess",
            {
                "diagnosis": diagnosis,
                "urgency_hint": urgency_hint,
            },
        )
        if isinstance(result, dict):
            return dict(result)
        raise ReferralTriageMCPClientError("triage_assess returned invalid payload.")

    def create_triage_ticket(self, reason: str, triage_priority: str, patient_id: str = "") -> dict[str, Any]:
        result = self._call_tool(
            "create_triage_ticket",
            {
                "reason": reason,
                "triage_priority": triage_priority,
                "patient_id": patient_id,
            },
        )
        if isinstance(result, dict):
            return dict(result)
        raise ReferralTriageMCPClientError("create_triage_ticket returned invalid payload.")
