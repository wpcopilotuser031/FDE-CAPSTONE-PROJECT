from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from app.config import DATA_DIR
from app.data_loader import load_json
from app.mcp_clients.specialist_recommendation_client import SpecialistRecommendationMCPClient
from app.mcp_server.tools import check_provider_in_network

INSURANCE_VALIDATION_ROLE = "insurance_validation"


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.insurance_validation.v1",
        "capability": "insurance_validation",
        "display_name": "Insurance Validation Agent",
        "description": "Checks provider in-network eligibility or retrieves a patient's current insurance plan.",
        "input_contract": {
            "required": [],
            "optional": ["provider_id", "insurance_plan", "patient_id", "patient_name", "member_id"],
        },
        "rbac_role": INSURANCE_VALIDATION_ROLE,
        "mcp_tools": ["insurance_eligibility"],
    }


def _use_mcp_tools() -> bool:
    return os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_patient_id(patient_id: str, patient_name: str, member_id: str) -> str | None:
    if patient_id:
        return patient_id

    users = load_json(DATA_DIR / "users.json")
    users_list = users.get("users", []) if isinstance(users, dict) else []

    if member_id:
        for user in users_list:
            if str(user.get("scope", "")).strip().lower() == member_id.lower():
                return str(user.get("scope", "")).strip()

    if patient_name:
        for user in users_list:
            if str(user.get("display_name", "")).strip().lower() == patient_name.lower():
                scope = str(user.get("scope", "")).strip()
                if scope:
                    return scope

    return None


def _lookup_patient_plan(patient_id: str) -> dict[str, Any] | None:
    patient_id_lower = patient_id.lower()

    patients = load_json(DATA_DIR / "patients.json")
    patient_row = next(
        (row for row in patients if str(row.get("patient_id", "")).strip().lower() == patient_id_lower),
        None,
    )

    eligibility_rows = load_json(DATA_DIR / "eligibility.json")
    matching_eligibility = [
        row
        for row in eligibility_rows
        if str(row.get("patient_id", "")).strip().lower() == patient_id_lower
    ]

    plan_from_patient = str(patient_row.get("insurance_plan", "")).strip() if patient_row else ""
    plan_from_eligibility = ""
    if matching_eligibility:
        plan_from_eligibility = str(matching_eligibility[0].get("insurance_plan", "")).strip()

    insurance_plan = plan_from_patient or plan_from_eligibility
    if not insurance_plan:
        return None

    return {
        "patient_id": patient_id,
        "insurance_plan": insurance_plan,
        "patient_record_found": patient_row is not None,
        "eligibility_records": [
            {
                "referral_id": row.get("referral_id"),
                "eligible": row.get("eligible"),
                "copay": row.get("copay"),
                "authorization_required": row.get("authorization_required"),
            }
            for row in matching_eligibility
        ],
    }


def insurance_validation_agent(payload: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(payload.get("provider_id", "")).strip()
    insurance_plan = str(payload.get("insurance_plan", "")).strip()
    patient_id = str(payload.get("patient_id", "")).strip()
    patient_name = str(payload.get("patient_name", "")).strip()
    member_id = str(payload.get("member_id", "")).strip()

    resolved_patient_id = _resolve_patient_id(patient_id, patient_name, member_id)

    if resolved_patient_id and not provider_id:
        patient_plan = _lookup_patient_plan(resolved_patient_id)
        if not patient_plan:
            return {
                "eligible": False,
                "missing_information": ["insurance plan not found for the patient"],
                "decision_trace": {
                    "capability": "insurance_validation",
                    "caller_role": INSURANCE_VALIDATION_ROLE,
                    "mcp_enabled": _use_mcp_tools(),
                    "tools_invoked": [],
                },
            }

        return {
            **patient_plan,
            "generated_at": _utc_now(),
            "decision_trace": {
                "capability": "insurance_validation",
                "caller_role": INSURANCE_VALIDATION_ROLE,
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    if provider_id and not insurance_plan:
        return {
            "eligible": False,
            "missing_information": ["insurance_plan is required when provider_id is provided"],
            "decision_trace": {
                "capability": "insurance_validation",
                "caller_role": INSURANCE_VALIDATION_ROLE,
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    if not provider_id and not insurance_plan:
        return {
            "eligible": False,
            "missing_information": [
                "provide either patient_id/patient_name/member_id for plan lookup, or provider_id with insurance_plan for eligibility check"
            ],
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
