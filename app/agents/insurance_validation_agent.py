from __future__ import annotations

from typing import Any

from app.agents.insurance_validation_graph import run_insurance_validation_flow

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
        "mcp_tools": ["insurance_eligibility", "patient_insurance_profile", "provider_insurance_plans"],
    }


def insurance_validation_agent(payload: dict[str, Any]) -> dict[str, Any]:
    return run_insurance_validation_flow(
        provider_id=str(payload.get("provider_id", "")).strip(),
        insurance_plan=str(payload.get("insurance_plan", "")).strip(),
        patient_id=str(payload.get("patient_id", "")).strip(),
        patient_name=str(payload.get("patient_name", "")).strip(),
        member_id=str(payload.get("member_id", "")).strip(),
        user_role=str(payload.get("user_role", "")).strip() or None,
    )


__all__ = ["INSURANCE_VALIDATION_ROLE", "build_agent_card", "insurance_validation_agent"]
