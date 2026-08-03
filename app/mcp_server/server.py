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

# Capability-level RBAC: which tools each capability/agent is allowed to invoke
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
    "conversational_assistant": set(),
}

# User-role-level RBAC: which tools each END USER role is allowed to access via MCP
# This is checked BEFORE capability-level RBAC and represents what the logged-in user can do
USER_ROLE_TOOL_MAP: dict[str, set[str]] = {
    "patient": {
        "diagnosis_to_specialty",
        "provider_candidates",
        # INTENTIONALLY EXCLUDED: "insurance_eligibility" - patients can't check coverage details
    },
    "provider": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
    "care_agent": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
}


def _authorize_tool_call(
    tool_name: str,
    caller_role: str,
    internal_key: str,
    user_role: str | None = None,
) -> None:
    """
    Authorize MCP tool calls with dual-layer RBAC:
    1. User-role check (if provided): what the END USER is allowed to do
    2. Caller-role check: what the capability/service is allowed to invoke

    Both must pass for authorization to succeed.

    Args:
        tool_name: The MCP tool being invoked (e.g., "diagnosis_to_specialty")
        caller_role: The capability/service invoking the tool (e.g., "specialist_recommendation")
        internal_key: The shared MCP secret for authentication
        user_role: The logged-in end user's role (patient/provider/care_agent) - if provided, checked first
    """
    expected_key = os.getenv("MCP_INTERNAL_KEY", "").strip()
    if not expected_key:
        raise PermissionError("MCP auth is not configured on server.")

    if internal_key.strip() != expected_key:
        raise PermissionError("Unauthorized MCP caller.")

    # Layer 1: Check USER role (end-user permissions) if provided
    if user_role:
        normalized_user_role = user_role.strip().lower()
        if normalized_user_role not in USER_ROLE_TOOL_MAP:
            raise PermissionError(f"User role '{user_role}' is not recognized.")

        user_allowed_tools = USER_ROLE_TOOL_MAP[normalized_user_role]
        if tool_name not in user_allowed_tools:
            raise PermissionError(
                f"User role '{user_role}' is not permitted to access tool '{tool_name}'. "
                f"This user can only access: {', '.join(sorted(user_allowed_tools)) or '(none)'}"
            )

    # Layer 2: Check CAPABILITY role (service permissions) - always checked
    normalized_caller_role = caller_role.strip().lower()
    if normalized_caller_role not in USE_CASE_TOOL_MAP:
        raise PermissionError(f"Caller role '{caller_role}' is not recognized.")

    allowed_tools = USE_CASE_TOOL_MAP[normalized_caller_role]
    if tool_name not in allowed_tools:
        raise PermissionError(
            f"Capability '{caller_role}' is not allowed for tool '{tool_name}'. "
            f"This capability can only invoke: {', '.join(sorted(allowed_tools)) or '(none)'}"
        )


@mcp.tool()
def diagnosis_to_specialty(
    diagnosis: str,
    internal_key: str,
    caller_role: str,
    user_role: str | None = None,
) -> list[str]:
    """Map diagnosis text to likely specialist domains.

    Args:
        diagnosis: The diagnosis text to map
        internal_key: Shared MCP authentication key
        caller_role: The capability/service invoking this tool
        user_role: Optional end-user role for dual-layer RBAC (patient/provider/care_agent)
    """
    _authorize_tool_call("diagnosis_to_specialty", caller_role, internal_key, user_role=user_role)
    return map_diagnosis_to_specialties(diagnosis)


@mcp.tool()
def provider_candidates(
    diagnosis: str,
    location: str,
    internal_key: str,
    caller_role: str,
    max_candidates: int = 10,
    user_role: str | None = None,
) -> list[dict]:
    """Retrieve provider candidates using ChromaDB RAG search.

    Args:
        diagnosis: The diagnosis to search for
        location: Geographic location for provider search
        internal_key: Shared MCP authentication key
        caller_role: The capability/service invoking this tool
        max_candidates: Maximum number of providers to return
        user_role: Optional end-user role for dual-layer RBAC (patient/provider/care_agent)
    """
    _authorize_tool_call("provider_candidates", caller_role, internal_key, user_role=user_role)
    return retrieve_candidate_providers(diagnosis, location, max_candidates)


@mcp.tool()
def insurance_eligibility(
    provider_id: str,
    insurance_plan: str,
    internal_key: str,
    caller_role: str,
    user_role: str | None = None,
) -> bool:
    """Check if provider is within payer network.

    Args:
        provider_id: The provider ID to check
        insurance_plan: The insurance plan name
        internal_key: Shared MCP authentication key
        caller_role: The capability/service invoking this tool
        user_role: Optional end-user role for dual-layer RBAC (patient/provider/care_agent)
    """
    _authorize_tool_call("insurance_eligibility", caller_role, internal_key, user_role=user_role)
    return check_provider_in_network(provider_id, insurance_plan)


if __name__ == "__main__":
    mcp.run()
