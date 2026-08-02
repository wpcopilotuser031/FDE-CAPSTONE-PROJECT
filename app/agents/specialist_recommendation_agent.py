from __future__ import annotations

from typing import Any

from app.agents.specialist_recommendation_graph import (
    SPECIALIST_RECOMMENDATION_ROLE,
    run_specialist_recommendation_flow,
)


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.specialist_recommendation.v1",
        "capability": "specialist_recommendation",
        "display_name": "Specialist Recommendation Agent",
        "description": "Recommends ranked specialists by diagnosis, geography, and payer coverage.",
        "input_contract": {
            "required": ["diagnosis", "location", "insurance_plan"],
            "optional": ["max_results"],
        },
        "rbac_role": SPECIALIST_RECOMMENDATION_ROLE,
        "mcp_tools": ["diagnosis_to_specialty", "provider_candidates", "insurance_eligibility"],
    }


def specialist_recommendation_agent(payload: dict[str, Any]) -> dict[str, Any]:
    return run_specialist_recommendation_flow(
        diagnosis=str(payload.get("diagnosis", "")).strip(),
        location=str(payload.get("location", "")).strip(),
        insurance_plan=str(payload.get("insurance_plan", "")).strip(),
        max_results=int(payload.get("max_results", 5)),
        urgency=str(payload.get("urgency", "Routine")).strip(),
        preferred_window_days=int(payload.get("preferred_window_days", 7)),
    )


__all__ = [
    "SPECIALIST_RECOMMENDATION_ROLE",
    "build_agent_card",
    "specialist_recommendation_agent",
]
