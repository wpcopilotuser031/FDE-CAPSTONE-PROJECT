from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from app.agents.specialist_recommendation_graph import run_specialist_recommendation_flow
from app.mcp_clients.specialist_recommendation_client import SpecialistRecommendationMCPClient
from app.mcp_server.tools import (
    check_provider_in_network,
    map_diagnosis_to_specialties,
    retrieve_candidate_providers,
)


def _use_mcp_tools() -> bool:
    return os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def specialist_recommendation_agent(payload: dict[str, Any]) -> dict[str, Any]:
    return run_specialist_recommendation_flow(
        diagnosis=str(payload.get("diagnosis", "")).strip(),
        location=str(payload.get("location", "")).strip(),
        insurance_plan=str(payload.get("insurance_plan", "")).strip(),
        max_results=int(payload.get("max_results", 5)),
    )


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
                "caller_role": "referral_triage",
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    specialties: list[str]
    tools_invoked: list[str] = []
    if _use_mcp_tools():
        with SpecialistRecommendationMCPClient(caller_role="referral_triage") as mcp_client:
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
            "caller_role": "referral_triage",
            "mcp_enabled": _use_mcp_tools(),
            "tools_invoked": tools_invoked,
        },
    }


def provider_discovery_agent(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis = str(payload.get("diagnosis", "")).strip()
    location = str(payload.get("location", "")).strip()
    max_results = int(payload.get("max_results", 5))

    if not diagnosis or not location:
        return {
            "providers": [],
            "missing_information": ["diagnosis and location are required"],
            "decision_trace": {
                "capability": "provider_discovery",
                "caller_role": "provider_discovery",
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    tools_invoked: list[str] = []
    if _use_mcp_tools():
        with SpecialistRecommendationMCPClient(caller_role="provider_discovery") as mcp_client:
            providers = mcp_client.provider_candidates(diagnosis, location, max_candidates=max_results)
            tools_invoked.append("provider_candidates")
    else:
        providers = retrieve_candidate_providers(diagnosis, location, max_candidates=max_results)

    return {
        "providers": providers,
        "generated_at": _utc_now(),
        "decision_trace": {
            "capability": "provider_discovery",
            "caller_role": "provider_discovery",
            "mcp_enabled": _use_mcp_tools(),
            "tools_invoked": tools_invoked,
        },
    }


def insurance_validation_agent(payload: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(payload.get("provider_id", "")).strip()
    insurance_plan = str(payload.get("insurance_plan", "")).strip()

    if not provider_id or not insurance_plan:
        return {
            "eligible": False,
            "missing_information": ["provider_id and insurance_plan are required"],
            "decision_trace": {
                "capability": "insurance_validation",
                "caller_role": "insurance_validation",
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    tools_invoked: list[str] = []
    if _use_mcp_tools():
        with SpecialistRecommendationMCPClient(caller_role="insurance_validation") as mcp_client:
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
            "caller_role": "insurance_validation",
            "mcp_enabled": _use_mcp_tools(),
            "tools_invoked": tools_invoked,
        },
    }
