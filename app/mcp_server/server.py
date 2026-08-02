from __future__ import annotations

import os
from pathlib import Path

from app.mcp_server.tools import (
    check_provider_in_network,
    map_diagnosis_to_specialties,
    retrieve_candidate_providers,
)
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

ROOT_PATH = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_PATH / ".env")

mcp = FastMCP("referral-tools-mcp")

USE_CASE_TOOL_MAP: dict[str, set[str]] = {
    "specialist_recommendation": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
    "referral_triage": {
        "diagnosis_to_specialty",
        "provider_candidates",
    },
    "insurance_validation": {
        "insurance_eligibility",
    },
    "provider_discovery": {
        "provider_candidates",
    },
    "alternative_provider_suggestion": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
    "admin_console": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
}


def _authorize_tool_call(tool_name: str, caller_role: str, internal_key: str) -> None:
    expected_key = os.getenv("MCP_INTERNAL_KEY", "").strip()
    if not expected_key:
        raise PermissionError("MCP auth is not configured on server.")

    if internal_key.strip() != expected_key:
        raise PermissionError("Unauthorized MCP caller.")

    normalized_role = caller_role.strip().lower()
    if normalized_role not in USE_CASE_TOOL_MAP:
        raise PermissionError(f"Role '{caller_role}' is not recognized.")

    allowed_tools = USE_CASE_TOOL_MAP[normalized_role]
    if tool_name not in allowed_tools:
        raise PermissionError(f"Role '{caller_role}' is not allowed for tool '{tool_name}'.")


@mcp.tool()
def diagnosis_to_specialty(
    diagnosis: str,
    internal_key: str,
    caller_role: str,
) -> list[str]:
    """Map diagnosis text to likely specialist domains."""
    _authorize_tool_call("diagnosis_to_specialty", caller_role, internal_key)
    return map_diagnosis_to_specialties(diagnosis)


@mcp.tool()
def provider_candidates(
    diagnosis: str,
    location: str,
    internal_key: str,
    caller_role: str,
    max_candidates: int = 10,
) -> list[dict]:
    """Retrieve provider candidates using ChromaDB RAG search."""
    _authorize_tool_call("provider_candidates", caller_role, internal_key)
    return retrieve_candidate_providers(diagnosis, location, max_candidates)


@mcp.tool()
def insurance_eligibility(
    provider_id: str,
    insurance_plan: str,
    internal_key: str,
    caller_role: str,
) -> bool:
    """Check if provider is within payer network."""
    _authorize_tool_call("insurance_eligibility", caller_role, internal_key)
    return check_provider_in_network(provider_id, insurance_plan)


if __name__ == "__main__":
    mcp.run()
