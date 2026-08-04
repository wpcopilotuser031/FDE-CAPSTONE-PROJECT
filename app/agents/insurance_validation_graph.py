from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Callable, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from app.mcp_clients.insurance_validation_client import (
    InsuranceValidationMCPClient,
    InsuranceValidationMCPClientError,
)

INSURANCE_VALIDATION_ROLE = "insurance_validation"


class InsuranceValidationState(TypedDict):
    provider_id: str
    insurance_plan: str
    patient_id: str
    patient_name: str
    member_id: str
    user_role: str | None
    mode: str
    result: dict[str, Any]
    missing_information: list[str]
    mcp_enabled: bool
    tools_invoked: list[str]
    mcp_client: InsuranceValidationMCPClient
    progress_callback: Callable[[str], None] | None


def determine_mode(state: InsuranceValidationState) -> InsuranceValidationState:
    has_patient_identity = bool(state["patient_id"] or state["patient_name"] or state["member_id"])
    has_provider_identity = bool(state["provider_id"])

    if has_patient_identity and not has_provider_identity:
        state["mode"] = "patient"
    elif has_provider_identity:
        state["mode"] = "provider"
    else:
        state["mode"] = "unknown"
        state["missing_information"].append(
            "provide patient_id/patient_name/member_id for patient insurance lookup, or provider_id for provider eligibility"
        )
    return state


def run_patient_lookup(state: InsuranceValidationState) -> InsuranceValidationState:
    progress = state.get("progress_callback")
    if progress:
        progress("Retrieving patient insurance profile")

    if "patient_insurance_profile" not in state["tools_invoked"]:
        state["tools_invoked"].append("patient_insurance_profile")

    profile = state["mcp_client"].patient_insurance_profile(
        patient_id=state["patient_id"],
        patient_name=state["patient_name"],
        member_id=state["member_id"],
        insurance_plan=state["insurance_plan"],
    )

    if profile.get("missing_information"):
        for item in profile.get("missing_information", []):
            value = str(item).strip()
            if value and value not in state["missing_information"]:
                state["missing_information"].append(value)

    state["result"] = {
        "mode": "patient_insurance_profile",
        "patient_id": profile.get("patient_id"),
        "patient_name": profile.get("patient_name"),
        "insurance_plan": profile.get("insurance_plan"),
        "eligible": bool(profile.get("eligible")),
        "patient_found": bool(profile.get("patient_found")),
        "eligibility_records": profile.get("eligibility_records", []),
    }
    return state


def run_provider_lookup(state: InsuranceValidationState) -> InsuranceValidationState:
    progress = state.get("progress_callback")
    if progress:
        progress("Retrieving provider eligibility and accepted plans")

    if not state["insurance_plan"]:
        state["missing_information"].append("insurance_plan")
        return state

    if "provider_insurance_plans" not in state["tools_invoked"]:
        state["tools_invoked"].append("provider_insurance_plans")
    plans = state["mcp_client"].provider_insurance_plans(state["provider_id"])

    if "insurance_eligibility" not in state["tools_invoked"]:
        state["tools_invoked"].append("insurance_eligibility")
    eligible = state["mcp_client"].insurance_eligibility(
        state["provider_id"],
        state["insurance_plan"],
    )

    state["result"] = {
        "mode": "provider_eligibility",
        "provider_id": state["provider_id"],
        "insurance_plan": state["insurance_plan"],
        "eligible": eligible,
        "accepted_plans": plans,
    }
    return state


def route_mode(state: InsuranceValidationState) -> str:
    if state["mode"] == "patient":
        return "patient"
    if state["mode"] == "provider":
        return "provider"
    return END


def build_insurance_validation_graph():
    graph_builder = StateGraph(InsuranceValidationState)
    graph_builder.add_node("determine_mode", determine_mode)
    graph_builder.add_node("patient", run_patient_lookup)
    graph_builder.add_node("provider", run_provider_lookup)

    graph_builder.set_entry_point("determine_mode")
    graph_builder.add_conditional_edges("determine_mode", route_mode)
    graph_builder.add_edge("patient", END)
    graph_builder.add_edge("provider", END)

    return graph_builder.compile()


def run_insurance_validation_flow(
    *,
    provider_id: str = "",
    insurance_plan: str = "",
    patient_id: str = "",
    patient_name: str = "",
    member_id: str = "",
    user_role: str | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    graph = build_insurance_validation_graph()

    try:
        with InsuranceValidationMCPClient(
            caller_role=INSURANCE_VALIDATION_ROLE,
            user_role=user_role,
        ) as mcp_client:
            initial_state: InsuranceValidationState = {
                "provider_id": provider_id,
                "insurance_plan": insurance_plan,
                "patient_id": patient_id,
                "patient_name": patient_name,
                "member_id": member_id,
                "user_role": user_role,
                "mode": "",
                "result": {},
                "missing_information": [],
                "mcp_enabled": True,
                "tools_invoked": [],
                "mcp_client": mcp_client,
                "progress_callback": progress_callback,
            }
            final_state = graph.invoke(initial_state)
    except InsuranceValidationMCPClientError:
        raise

    payload = dict(final_state.get("result", {}))
    payload.update(
        {
            "request_id": str(uuid4()),
            "generated_at": datetime.now(UTC).isoformat(),
            "missing_information": final_state.get("missing_information", []),
            "decision_trace": {
                "capability": "insurance_validation",
                "caller_role": INSURANCE_VALIDATION_ROLE,
                "mcp_enabled": True,
                "tools_invoked": final_state.get("tools_invoked", []),
                "human_review_required": False,
            },
        }
    )

    return payload
