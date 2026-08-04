from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from app.mcp_clients.referral_triage_client import (
    ReferralTriageMCPClient,
    ReferralTriageMCPClientError,
)

REFERRAL_TRIAGE_ROLE = "referral_triage"


class ReferralTriageState(TypedDict):
    diagnosis: str
    patient_id: str
    urgency_hint: str
    triage_priority: str
    priority_score: float
    recommended_specialties: list[str]
    ticket: dict[str, Any]
    missing_information: list[str]
    mcp_enabled: bool
    tools_invoked: list[str]
    mcp_client: ReferralTriageMCPClient
    progress_callback: Callable[[str], None] | None


def assess_triage(state: ReferralTriageState) -> ReferralTriageState:
    progress = state.get("progress_callback")
    if progress:
        progress("Assessing referral triage priority")

    if not state["diagnosis"]:
        state["missing_information"].append("diagnosis")
        return state

    if "triage_assess" not in state["tools_invoked"]:
        state["tools_invoked"].append("triage_assess")

    assessment = state["mcp_client"].triage_assess(
        diagnosis=state["diagnosis"],
        urgency_hint=state["urgency_hint"],
    )

    state["triage_priority"] = str(assessment.get("triage_priority", "unknown"))
    state["priority_score"] = float(assessment.get("priority_score", 0.0))
    state["recommended_specialties"] = [str(item) for item in assessment.get("recommended_specialties", [])]
    return state


def create_ticket(state: ReferralTriageState) -> ReferralTriageState:
    progress = state.get("progress_callback")
    if progress:
        progress("Creating ticket for human intervention")

    if state["missing_information"]:
        state["ticket"] = {}
        return state

    if "create_triage_ticket" not in state["tools_invoked"]:
        state["tools_invoked"].append("create_triage_ticket")

    reason = (
        f"Referral triage requested for diagnosis '{state['diagnosis']}' "
        f"with assessed priority '{state['triage_priority']}'."
    )
    state["ticket"] = state["mcp_client"].create_triage_ticket(
        reason=reason,
        triage_priority=state["triage_priority"],
        patient_id=state["patient_id"],
    )
    return state


def build_referral_triage_graph():
    graph_builder = StateGraph(ReferralTriageState)
    graph_builder.add_node("assess_triage", assess_triage)
    graph_builder.add_node("create_ticket", create_ticket)

    graph_builder.set_entry_point("assess_triage")
    graph_builder.add_edge("assess_triage", "create_ticket")
    graph_builder.add_edge("create_ticket", END)

    return graph_builder.compile()


def run_referral_triage_flow(
    *,
    diagnosis: str,
    patient_id: str = "",
    urgency_hint: str = "",
    user_role: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    graph = build_referral_triage_graph()

    try:
        with ReferralTriageMCPClient(
            caller_role=REFERRAL_TRIAGE_ROLE,
            user_role=user_role,
        ) as mcp_client:
            initial_state: ReferralTriageState = {
                "diagnosis": diagnosis,
                "patient_id": patient_id,
                "urgency_hint": urgency_hint,
                "triage_priority": "unknown",
                "priority_score": 0.0,
                "recommended_specialties": [],
                "ticket": {},
                "missing_information": [],
                "mcp_enabled": True,
                "tools_invoked": [],
                "mcp_client": mcp_client,
                "progress_callback": progress_callback,
            }
            final_state = graph.invoke(initial_state)
    except ReferralTriageMCPClientError:
        raise

    return {
        "request_id": str(uuid4()),
        "generated_at": datetime.now(UTC).isoformat(),
        "triage_priority": final_state["triage_priority"],
        "priority_score": final_state["priority_score"],
        "recommended_specialties": final_state["recommended_specialties"],
        "human_intervention_ticket": final_state["ticket"],
        "missing_information": final_state["missing_information"],
        "decision_trace": {
            "capability": "referral_triage",
            "caller_role": REFERRAL_TRIAGE_ROLE,
            "mcp_enabled": True,
            "tools_invoked": final_state["tools_invoked"],
            "human_review_required": True,
        },
    }
