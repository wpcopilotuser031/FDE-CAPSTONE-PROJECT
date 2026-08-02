from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from app.mcp_clients.specialist_recommendation_client import SpecialistRecommendationMCPClient
from app.mcp_server.tools import check_provider_in_network

INSURANCE_VALIDATION_ROLE = "insurance_validation"


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.insurance_validation.v1",
        "capability": "insurance_validation",
        "display_name": "Insurance Validation Agent",
        "description": "Validates whether a provider is in-network for a payer plan.",
        "input_contract": {
            "required": ["provider_id", "insurance_plan"],
            "optional": [],
        },
        "rbac_role": INSURANCE_VALIDATION_ROLE,
        "mcp_tools": ["insurance_eligibility"],
    }


def _use_mcp_tools() -> bool:
    return os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def insurance_validation_agent(payload: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(payload.get("provider_id", "")).strip()
    insurance_plan = str(payload.get("insurance_plan", "")).strip()

    if not provider_id or not insurance_plan:
        return {
            "eligible": False,
            "missing_information": ["provider_id and insurance_plan are required"],
            "decision_trace": {
                "capability": "insurance_validation",
                "caller_role": INSURANCE_VALIDATION_ROLE,
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    tools_invoked: list[str] = []
    if _use_mcp_tools():
        with SpecialistRecommendationMCPClient(caller_role=INSURANCE_VALIDATION_ROLE) as mcp_client:
            eligible = mcp_client.insurance_eligibility(provider_id, insurance_plan)
            tools_invoked.append("insurance_eligibility")
    else:
        eligible = check_provider_in_network(provider_id, insurance_plan)

    return {
        "provider_id": provider_id,
        "insurance_plan": insurance_plan,
        "eligible": eligible,
        "generated_at": _utc_now(),
        "decision_trace": {
            "capability": "insurance_validation",
            "caller_role": INSURANCE_VALIDATION_ROLE,
            "mcp_enabled": _use_mcp_tools(),
            "tools_invoked": tools_invoked,
        },
    }


__all__ = ["INSURANCE_VALIDATION_ROLE", "build_agent_card", "insurance_validation_agent"]
