from __future__ import annotations

from datetime import UTC, datetime
import os
from typing import Any, Callable, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from app.mcp_server.tools import (
    build_recommendation_rationale_llm_assisted,
    check_provider_in_network,
    days_until,
    infer_specialties_llm_assisted,
    retrieve_candidate_providers,
    score_provider_with_breakdown,
)
from app.mcp_clients.specialist_recommendation_client import (
    MCPClientError,
    SpecialistRecommendationMCPClient,
)

SPECIALIST_RECOMMENDATION_ROLE = "specialist_recommendation"


class SpecialistRecommendationState(TypedDict):
    diagnosis: str
    location: str
    insurance_plan: str
    max_results: int
    urgency: str
    preferred_window_days: int
    inferred_specialties: list[str]
    candidates: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    missing_information: list[str]
    llm_used: bool
    mcp_client: SpecialistRecommendationMCPClient | None
    mcp_enabled: bool
    tools_invoked: list[str]
    progress_callback: Callable[[str], None] | None


def infer_specialties(state: SpecialistRecommendationState) -> SpecialistRecommendationState:
    progress = state.get("progress_callback")
    if progress:
        progress("Inferring specialist domains from diagnosis")
    specialties, _ = infer_specialties_llm_assisted(state["diagnosis"])
    state["inferred_specialties"] = specialties
    state["llm_used"] = True
    if not specialties:
        state["missing_information"].append("Unable to infer specialty from diagnosis")
    return state


def fetch_candidates(state: SpecialistRecommendationState) -> SpecialistRecommendationState:
    progress = state.get("progress_callback")
    if progress:
        progress("Retrieving candidate providers")
    if "provider_candidates" not in state["tools_invoked"]:
        state["tools_invoked"].append("provider_candidates")
    candidates = retrieve_candidate_providers(
        state["diagnosis"],
        state["location"],
        max_candidates=12,
        mcp_client=state["mcp_client"],
    )
    state["candidates"] = candidates
    return state


def rank_recommendations(state: SpecialistRecommendationState) -> SpecialistRecommendationState:
    progress = state.get("progress_callback")
    if progress:
        progress("Scoring candidates and checking eligibility")

    specialties = state["inferred_specialties"]
    scored: list[dict[str, Any]] = []

    if "insurance_eligibility" not in state["tools_invoked"]:
        state["tools_invoked"].append("insurance_eligibility")

    for provider in state["candidates"]:
        if specialties and provider["specialty"] not in specialties:
            continue

        accepted = check_provider_in_network(
            provider["provider_id"],
            state["insurance_plan"],
            mcp_client=state["mcp_client"],
        )
        score, score_breakdown = score_provider_with_breakdown(
            provider,
            specialties,
            state["location"],
            state["insurance_plan"],
            mcp_client=state["mcp_client"],
            accepts_insurance=accepted,
            urgency=state["urgency"],
        )

        wait_days = days_until(provider["next_available_date"])
        exceeded_wait_window = wait_days > state["preferred_window_days"]

        scored.append(
            {
                "provider": provider,
                "provider_id": provider["provider_id"],
                "provider_name": provider["provider_name"],
                "specialty": provider["specialty"],
                "location": provider["location"],
                "accepts_insurance": accepted,
                "next_available_date": provider["next_available_date"],
                "score": score,
                "score_breakdown": score_breakdown,
                "exceeded_wait_window": exceeded_wait_window,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    top_scored = scored[: state["max_results"]]

    if progress:
        progress("Generating final AI rationales for top providers")

    recommendations: list[dict[str, Any]] = []
    for item in top_scored:
        provider = item.pop("provider")
        rationale, _ = build_recommendation_rationale_llm_assisted(
            provider,
            specialties,
            state["insurance_plan"],
            mcp_client=state["mcp_client"],
            accepts_insurance=item["accepts_insurance"],
        )
        item["rationale"] = rationale
        recommendations.append(item)

    state["recommendations"] = recommendations

    if not state["recommendations"]:
        state["missing_information"].append("No suitable specialists found")

    return state


def build_specialist_recommendation_graph():
    graph_builder = StateGraph(SpecialistRecommendationState)
    graph_builder.add_node("infer_specialties", infer_specialties)
    graph_builder.add_node("fetch_candidates", fetch_candidates)
    graph_builder.add_node("rank_recommendations", rank_recommendations)

    graph_builder.set_entry_point("infer_specialties")
    graph_builder.add_edge("infer_specialties", "fetch_candidates")
    graph_builder.add_edge("fetch_candidates", "rank_recommendations")
    graph_builder.add_edge("rank_recommendations", END)

    return graph_builder.compile()

def run_specialist_recommendation_flow(
    diagnosis: str,
    location: str,
    insurance_plan: str,
    max_results: int,
    urgency: str = "Routine",
    preferred_window_days: int = 7,
    progress_callback: Callable[[str], None] | None = None,
    user_role: str | None = None,
) -> dict[str, Any]:
    """
    Execute specialist recommendation workflow.

    Args:
        diagnosis: Patient diagnosis
        location: Geographic location for provider search
        insurance_plan: Patient insurance plan name
        max_results: Maximum recommendations to return
        urgency: Referral urgency (Routine/Priority/Urgent)
        preferred_window_days: Preferred appointment window in days
        progress_callback: Optional callback for progress updates
        user_role: Logged-in end-user role (patient/provider/care_agent) - enables user-level RBAC checks
    """
    graph = build_specialist_recommendation_graph()

    use_mcp = os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}

    try:
        if use_mcp:
            with SpecialistRecommendationMCPClient(
                caller_role=SPECIALIST_RECOMMENDATION_ROLE,
                user_role=user_role,
            ) as mcp_client:
                initial_state: SpecialistRecommendationState = {
                    "diagnosis": diagnosis,
                    "location": location,
                    "insurance_plan": insurance_plan,
                    "max_results": max_results,
                    "urgency": urgency,
                    "preferred_window_days": preferred_window_days,
                    "inferred_specialties": [],
                    "candidates": [],
                    "recommendations": [],
                    "missing_information": [],
                    "llm_used": False,
                    "mcp_client": mcp_client,
                    "mcp_enabled": True,
                    "tools_invoked": [],
                    "progress_callback": progress_callback,
                }
                final_state = graph.invoke(initial_state)
        else:
            initial_state = {
                "diagnosis": diagnosis,
                "location": location,
                "insurance_plan": insurance_plan,
                "max_results": max_results,
                "urgency": urgency,
                "preferred_window_days": preferred_window_days,
                "inferred_specialties": [],
                "candidates": [],
                "recommendations": [],
                "missing_information": [],
                "llm_used": False,
                "mcp_client": None,
                "mcp_enabled": False,
                "tools_invoked": [],
                "progress_callback": progress_callback,
            }
            final_state = graph.invoke(initial_state)
    except MCPClientError:
        raise

    recs = final_state["recommendations"]
    all_exceeded_window = bool(recs) and all(item.get("exceeded_wait_window", False) for item in recs)
    low_score = any(item["score"] < 0.65 for item in recs)
    human_review_required = (
        urgency == "Urgent"
        or low_score
        or (urgency in {"Urgent", "Priority"} and all_exceeded_window)
    )

    return {
        "request_id": str(uuid4()),
        "generated_at": datetime.now(UTC).isoformat(),
        "inferred_specialties": final_state["inferred_specialties"],
        "recommendations": final_state["recommendations"],
        "missing_information": final_state["missing_information"],
        "llm_used": final_state["llm_used"],
        "decision_trace": {
            "capability": "specialist_recommendation",
            "caller_role": SPECIALIST_RECOMMENDATION_ROLE,
            "mcp_enabled": final_state["mcp_enabled"],
            "tools_invoked": final_state["tools_invoked"],
            "human_review_required": human_review_required,
        },
    }
