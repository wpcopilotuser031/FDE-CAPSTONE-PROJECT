from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, TypedDict
from uuid import uuid4

from app.mcp_clients.referral_history_client import ReferralHistoryMCPClient

REFERRAL_HISTORY_ROLE = "referral_history"


class ReferralHistoryState(TypedDict):
    referral_id: str
    patient_id: str
    query: str
    history_items: list[dict[str, Any]]
    summary: str
    missing_information: list[str]
    mcp_enabled: bool
    tools_invoked: list[str]
    mcp_client: ReferralHistoryMCPClient
    progress_callback: Callable[[str], None] | None


def fetch_referral_history(state: ReferralHistoryState) -> ReferralHistoryState:
    progress = state.get("progress_callback")
    if progress:
        progress("Fetching referral history via MCP tools")

    if not state["referral_id"] and not state["patient_id"] and not state["query"]:
        state["missing_information"].append("patient_id or referral_id or query")
        state["history_items"] = []
        return state

    if "retrieve_referral_history" not in state["tools_invoked"]:
        state["tools_invoked"].append("retrieve_referral_history")

    state["history_items"] = state["mcp_client"].retrieve_referral_history(
        query=state["query"],
        patient_id=state["patient_id"],
        referral_id=state["referral_id"],
        max_results=5,
    )
    return state


def summarize_history(state: ReferralHistoryState) -> ReferralHistoryState:
    progress = state.get("progress_callback")
    if progress:
        progress("Summarizing referral history data")

    items = state["history_items"]
    if not items:
        state["summary"] = "No referral history was found for the supplied patient, referral id, or query."
        return state

    main = items[0]
    patient_id = main.get("patient_id", "unknown")
    referral_id = main.get("referral_id", "unknown")
    diagnosis = main.get("diagnosis", "unknown diagnosis")
    specialty = main.get("specialty", "unknown specialty")
    status = main.get("status", "unknown status")
    priority = main.get("priority", "unknown priority")
    submitted_at = main.get("submitted_at", "unknown submission date")
    missing_docs = main.get("documents_missing") or []
    missing_text = ", ".join(str(item) for item in missing_docs if str(item).strip()) or "none"
    count = len(items)

    summary = (
        f"Referral {referral_id} for patient {patient_id} is currently {status} "
        f"with diagnosis '{diagnosis}' for specialty {specialty}. Priority is {priority}, "
        f"submitted on {submitted_at}. Missing documents: {missing_text}."
    )
    if count > 1:
        summary += f" Showing {count} related referral history records."

    state["summary"] = summary
    return state


def run_referral_history_flow(
    *,
    referral_id: str = "",
    patient_id: str = "",
    query: str = "",
    user_role: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    with ReferralHistoryMCPClient(caller_role=REFERRAL_HISTORY_ROLE, user_role=user_role) as mcp_client:
        state: ReferralHistoryState = {
            "referral_id": referral_id,
            "patient_id": patient_id,
            "query": query,
            "history_items": [],
            "summary": "",
            "missing_information": [],
            "mcp_enabled": True,
            "tools_invoked": [],
            "mcp_client": mcp_client,
            "progress_callback": progress_callback,
        }

        state = fetch_referral_history(state)
        state = summarize_history(state)

    return {
        "request_id": str(uuid4()),
        "generated_at": datetime.now(UTC).isoformat(),
        "history_items": state["history_items"],
        "summary": state["summary"],
        "missing_information": state["missing_information"],
        "decision_trace": {
            "capability": "referral_history",
            "caller_role": REFERRAL_HISTORY_ROLE,
            "mcp_enabled": state["mcp_enabled"],
            "tools_invoked": state["tools_invoked"],
            "human_review_required": False,
        },
    }
