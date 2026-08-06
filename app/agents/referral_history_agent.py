from __future__ import annotations

import re
from typing import Any

from app.agents.referral_history_graph import run_referral_history_flow

REFERRAL_HISTORY_ROLE = "referral_history"


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.referral_history.v1",
        "capability": "referral_history",
        "display_name": "Referral History Agent",
        "description": "Summarizes referral history and relevant prior referral context for specialists before consultation.",
        "input_contract": {
            "required": [],
            "optional": ["patient_id", "referral_id", "query", "question", "user_role"],
        },
        "rbac_role": REFERRAL_HISTORY_ROLE,
        "mcp_tools": ["retrieve_referral_history"],
    }


def _extract_text(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(1)).strip()


def referral_history_agent(payload: dict[str, Any]) -> dict[str, Any]:
    referral_id = str(payload.get("referral_id", "")).strip()
    patient_id = str(payload.get("patient_id", "")).strip()
    query = str(payload.get("query", "")).strip()
    question = str(payload.get("question", "")).strip()

    if question:
        if not referral_id:
            referral_id = _extract_text(r"\b(REF-\d+)\b", question)
        if not patient_id:
            patient_id = _extract_text(r"\b(PT-\d+)\b", question)
        if not query:
            query = question

    return run_referral_history_flow(
        referral_id=referral_id,
        patient_id=patient_id,
        query=query,
        user_role=str(payload.get("user_role", "")).strip() or None,
    )


__all__ = ["REFERRAL_HISTORY_ROLE", "build_agent_card", "referral_history_agent"]
