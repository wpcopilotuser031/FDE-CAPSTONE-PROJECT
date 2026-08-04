from __future__ import annotations

import re
from typing import Any

from app.agents.insurance_validation_graph import run_insurance_validation_flow

INSURANCE_VALIDATION_ROLE = "insurance_validation"


def _extract_text(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(1)).strip()


def _extract_fields_from_question(question: str) -> dict[str, str]:
    fields: dict[str, str] = {
        "patient_id": "",
        "patient_name": "",
        "member_id": "",
        "provider_id": "",
        "insurance_plan": "",
    }

    fields["patient_id"] = _extract_text(r"\b(PT-\d+)\b", question)
    fields["member_id"] = _extract_text(r"member\s*id\s*[:=-]\s*([A-Za-z0-9\-_]+)", question)
    fields["provider_id"] = _extract_text(r"\b(P\d{3,})\b", question)
    fields["patient_name"] = _extract_text(r"patient\s+name\s*(?:is|:|=|-)\s*([^,;]+)", question)
    fields["insurance_plan"] = _extract_text(r"insurance\s*plan\s*(?:is|:|=|-)\s*([^,;]+)", question)

    return fields


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
    provider_id = str(payload.get("provider_id", "")).strip()
    insurance_plan = str(payload.get("insurance_plan", "")).strip()
    patient_id = str(payload.get("patient_id", "")).strip()
    patient_name = str(payload.get("patient_name", "")).strip()
    member_id = str(payload.get("member_id", "")).strip()
    question = str(payload.get("question", "")).strip()

    if question:
        inferred = _extract_fields_from_question(question)
        patient_id = patient_id or inferred["patient_id"]
        patient_name = patient_name or inferred["patient_name"]
        member_id = member_id or inferred["member_id"]
        provider_id = provider_id or inferred["provider_id"]
        insurance_plan = insurance_plan or inferred["insurance_plan"]

    return run_insurance_validation_flow(
        provider_id=provider_id,
        insurance_plan=insurance_plan,
        patient_id=patient_id,
        patient_name=patient_name,
        member_id=member_id,
        user_role=str(payload.get("user_role", "")).strip() or None,
    )


__all__ = ["INSURANCE_VALIDATION_ROLE", "build_agent_card", "insurance_validation_agent"]
