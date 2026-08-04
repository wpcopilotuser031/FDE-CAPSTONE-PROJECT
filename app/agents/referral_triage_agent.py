from __future__ import annotations

import re
from typing import Any

from app.agents.referral_triage_graph import run_referral_triage_flow

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


def referral_triage_agent(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis = str(payload.get("diagnosis", "")).strip()
    question = str(payload.get("question", "")).strip()
    if question and not diagnosis:
        diagnosis = _extract_text(r"diagnosis\s*(?:is|:|=|-)\s*([^,;]+)", question)

    patient_id = str(payload.get("patient_id", "")).strip()
    if question and not patient_id:
        patient_id = _extract_text(r"\b(PT-\d+)\b", question)

    return run_referral_triage_flow(
        diagnosis=diagnosis,
        patient_id=patient_id,
        urgency_hint=str(payload.get("urgency_hint", "")).strip(),
        user_role=str(payload.get("user_role", "")).strip() or None,
    )


__all__ = ["REFERRAL_TRIAGE_ROLE", "build_agent_card", "referral_triage_agent"]
