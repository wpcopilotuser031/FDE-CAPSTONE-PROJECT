from __future__ import annotations

import os
from typing import Any

from app.agents.alternative_provider_graph import run_alternative_provider_flow

ALTERNATIVE_PROVIDER_ROLE = "alternative_provider_suggestion"


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.alternative_provider_suggestion.v1",
        "capability": "alternative_provider_suggestion",
        "display_name": "Alternative Provider Suggestion Agent",
        "description": (
            "Suggests ranked alternative providers when the originally recommended provider exceeds the patient's "
            "preferred appointment window. Excludes the original provider, filters by availability window, and "
            "applies urgency-adjusted scoring."
        ),
        "input_contract": {
            "required": ["diagnosis", "location", "insurance_plan", "excluded_provider_id"],
            "optional": ["preferred_window_days", "urgency", "max_results"],
        },
        "rbac_role": ALTERNATIVE_PROVIDER_ROLE,
        "mcp_tools": ["diagnosis_to_specialty", "provider_candidates", "insurance_eligibility"],
    }


def _use_mcp_tools() -> bool:
    return os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}


def alternative_provider_agent(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis = str(payload.get("diagnosis", "")).strip()
    location = str(payload.get("location", "")).strip()
    insurance_plan = str(payload.get("insurance_plan", "")).strip()
    excluded_provider_id = str(payload.get("excluded_provider_id", "")).strip()

    if not diagnosis or not location or not insurance_plan or not excluded_provider_id:
        return {
            "alternatives": [],
            "missing_information": [
                "diagnosis, location, insurance_plan, and excluded_provider_id are required"
            ],
            "decision_trace": {
                "capability": "alternative_provider_suggestion",
                "caller_role": ALTERNATIVE_PROVIDER_ROLE,
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
                "human_review_required": False,
            },
        }

    return run_alternative_provider_flow(
        diagnosis=diagnosis,
        location=location,
        insurance_plan=insurance_plan,
        excluded_provider_id=excluded_provider_id,
        preferred_window_days=int(payload.get("preferred_window_days", 7)),
        urgency=str(payload.get("urgency", "Routine")).strip(),
        max_results=int(payload.get("max_results", 5)),
    )


__all__ = ["ALTERNATIVE_PROVIDER_ROLE", "build_agent_card", "alternative_provider_agent"]
