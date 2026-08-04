from __future__ import annotations

import re
from typing import Any

from app.agents.referral_triage_graph import run_referral_triage_flow
from app.config import DATA_DIR
from app.data_loader import load_json

REFERRAL_TRIAGE_ROLE = "referral_triage"


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.referral_triage.v1",
        "capability": "referral_triage",
        "display_name": "Referral Triage Agent",
        "description": "Assigns referral priority and suggests specialty domains.",
        "input_contract": {
            "required": ["diagnosis"],
            "optional": ["patient_id", "urgency_hint", "user_role", "question"],
        },
        "rbac_role": REFERRAL_TRIAGE_ROLE,
        "mcp_tools": ["triage_assess", "create_triage_ticket"],
    }


def _extract_text(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(1)).strip()


def _resolve_diagnosis_from_referrals(patient_id: str) -> str:
    if not patient_id:
        return ""
    rows = load_json(DATA_DIR / "referrals.json")
    patient_id_lower = patient_id.lower()
    for row in rows:
        if str(row.get("patient_id", "")).strip().lower() == patient_id_lower:
            diagnosis = str(row.get("diagnosis", "")).strip()
            if diagnosis:
                return diagnosis
    return ""


def referral_triage_agent(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis = str(payload.get("diagnosis", "")).strip()
    question = str(payload.get("question", "")).strip()
    if question and not diagnosis:
        diagnosis = _extract_text(r"diagnosis\s*(?:is|:|=|-)\s*([^,;]+)", question)

    patient_id = str(payload.get("patient_id", "")).strip()
    if question and not patient_id:
        patient_id = _extract_text(r"\b(PT-\d+)\b", question)

    if patient_id and not diagnosis:
        diagnosis = _resolve_diagnosis_from_referrals(patient_id)

    return run_referral_triage_flow(
        diagnosis=diagnosis,
        patient_id=patient_id,
        urgency_hint=str(payload.get("urgency_hint", "")).strip(),
        user_role=str(payload.get("user_role", "")).strip() or None,
    )


__all__ = ["REFERRAL_TRIAGE_ROLE", "build_agent_card", "referral_triage_agent"]
