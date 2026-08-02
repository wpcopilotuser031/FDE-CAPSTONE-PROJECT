from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from app.mcp_clients.specialist_recommendation_client import SpecialistRecommendationMCPClient
from app.mcp_server.tools import map_diagnosis_to_specialties

REFERRAL_TRIAGE_ROLE = "referral_triage"


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.referral_triage.v1",
        "capability": "referral_triage",
        "display_name": "Referral Triage Agent",
        "description": "Assigns referral priority and suggests specialty domains.",
        "input_contract": {
            "required": ["diagnosis"],
            "optional": [],
        },
        "rbac_role": REFERRAL_TRIAGE_ROLE,
        "mcp_tools": ["diagnosis_to_specialty", "provider_candidates"],
    }


def _use_mcp_tools() -> bool:
    return os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def referral_triage_agent(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis = str(payload.get("diagnosis", "")).strip()
    if not diagnosis:
        return {
            "triage_priority": "unknown",
            "priority_score": 0.0,
            "recommended_specialties": [],
            "missing_information": ["diagnosis is required"],
            "decision_trace": {
                "capability": "referral_triage",
                "caller_role": REFERRAL_TRIAGE_ROLE,
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    specialties: list[str]
    tools_invoked: list[str] = []
    if _use_mcp_tools():
        with SpecialistRecommendationMCPClient(caller_role=REFERRAL_TRIAGE_ROLE) as mcp_client:
            specialties = mcp_client.diagnosis_to_specialty(diagnosis)
            tools_invoked.append("diagnosis_to_specialty")
    else:
        specialties = map_diagnosis_to_specialties(diagnosis)

    diagnosis_lower = diagnosis.lower()
    high_urgency_terms = {"chest pain", "stroke", "sepsis", "hemorrhage"}
    medium_urgency_terms = {"worsening", "persistent", "uncontrolled"}

    if any(term in diagnosis_lower for term in high_urgency_terms):
        triage_priority = "high"
        priority_score = 0.9
    elif any(term in diagnosis_lower for term in medium_urgency_terms):
        triage_priority = "medium"
        priority_score = 0.65
    else:
        triage_priority = "low"
        priority_score = 0.4

    return {
        "triage_priority": triage_priority,
        "priority_score": priority_score,
        "recommended_specialties": specialties,
        "generated_at": _utc_now(),
        "decision_trace": {
            "capability": "referral_triage",
            "caller_role": REFERRAL_TRIAGE_ROLE,
            "mcp_enabled": _use_mcp_tools(),
            "tools_invoked": tools_invoked,
        },
    }


__all__ = ["REFERRAL_TRIAGE_ROLE", "build_agent_card", "referral_triage_agent"]
