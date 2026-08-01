"""
LangGraph pipeline for Alternative Provider Suggestion.

Triggered when the originally recommended provider exceeds the patient's
preferred appointment window. The pipeline:
  1. infer_specialties   – LLM maps diagnosis to canonical specialty names.
  2. fetch_alternatives  – RAG / MCP retrieves candidates; the excluded
                           provider is stripped from results.
  3. filter_by_window    – Only providers whose next slot is within
                           preferred_window_days are kept as "in-window".
                           Out-of-window providers are still returned as
                           fallbacks so the response is never empty.
  4. rank_alternatives   – Urgency-weighted scoring + LLM rationale per
                           candidate.
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from typing import Any, Callable, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from app.mcp_clients.specialist_recommendation_client import (
    MCPClientError,
    SpecialistRecommendationMCPClient,
)
from app.mcp_server.tools import (
    build_recommendation_rationale_llm_assisted,
    check_provider_in_network,
    days_until,
    infer_specialties_llm_assisted,
    retrieve_candidate_providers,
    score_provider_with_breakdown,
)

ALTERNATIVE_PROVIDER_ROLE = "alternative_provider_suggestion"


class AlternativeProviderState(TypedDict):
    diagnosis: str
    location: str
    insurance_plan: str
    excluded_provider_id: str          # original provider that exceeded the window
    preferred_window_days: int
    urgency: str
    max_results: int
    inferred_specialties: list[str]
    alternatives: list[dict[str, Any]]
    missing_information: list[str]
    llm_used: bool
    mcp_client: SpecialistRecommendationMCPClient | None
    mcp_enabled: bool
    tools_invoked: list[str]
    progress_callback: Callable[[str], None] | None


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def infer_specialties(state: AlternativeProviderState) -> AlternativeProviderState:
    progress = state.get("progress_callback")
    if progress:
        progress("Inferring specialist domains from diagnosis")
    specialties, _ = infer_specialties_llm_assisted(state["diagnosis"])
    state["inferred_specialties"] = specialties
    state["llm_used"] = True
    if not specialties:
        state["missing_information"].append("Unable to infer specialty from diagnosis")
    return state


def fetch_alternatives(state: AlternativeProviderState) -> AlternativeProviderState:
    progress = state.get("progress_callback")
    if progress:
        progress("Fetching alternative provider candidates")

    if "provider_candidates" not in state["tools_invoked"]:
        state["tools_invoked"].append("provider_candidates")

    candidates = retrieve_candidate_providers(
        state["diagnosis"],
        state["location"],
        max_candidates=20,          # fetch more to allow exclusion + filtering
        mcp_client=state["mcp_client"],
    )

    # Exclude the original provider that triggered this request
    excluded = state["excluded_provider_id"].strip()
    state["alternatives"] = [c for c in candidates if c["provider_id"] != excluded]
    return state


def rank_alternatives(state: AlternativeProviderState) -> AlternativeProviderState:
    progress = state.get("progress_callback")
    if progress:
        progress("Scoring and filtering alternative providers")

    if "insurance_eligibility" not in state["tools_invoked"]:
        state["tools_invoked"].append("insurance_eligibility")

    specialties = state["inferred_specialties"]
    scored: list[dict[str, Any]] = []

    for provider in state["alternatives"]:
        # Skip if specialty doesn't match inferred specialties
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
        within_window = wait_days <= state["preferred_window_days"]

        scored.append({
            "provider": provider,
            "provider_id": provider["provider_id"],
            "provider_name": provider["provider_name"],
            "specialty": provider["specialty"],
            "location": provider["location"],
            "accepts_insurance": accepted,
            "next_available_date": provider["next_available_date"],
            "wait_days": wait_days,
            "within_preferred_window": within_window,
            "score": score,
            "score_breakdown": score_breakdown,
        })

    # Sort: within-window providers first, then by score descending
    scored.sort(key=lambda x: (not x["within_preferred_window"], -x["score"]))
    top = scored[: state["max_results"]]

    if progress:
        progress("Generating AI rationales for alternative providers")

    alternatives: list[dict[str, Any]] = []
    for item in top:
        provider = item.pop("provider")
        rationale, _ = build_recommendation_rationale_llm_assisted(
            provider,
            specialties,
            state["insurance_plan"],
            mcp_client=state["mcp_client"],
            accepts_insurance=item["accepts_insurance"],
        )
        item["rationale"] = rationale
        alternatives.append(item)

    state["alternatives"] = alternatives
    return state


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_alternative_provider_graph() -> Any:
    builder = StateGraph(AlternativeProviderState)
    builder.add_node("infer_specialties", infer_specialties)
    builder.add_node("fetch_alternatives", fetch_alternatives)
    builder.add_node("rank_alternatives", rank_alternatives)

    builder.set_entry_point("infer_specialties")
    builder.add_edge("infer_specialties", "fetch_alternatives")
    builder.add_edge("fetch_alternatives", "rank_alternatives")
    builder.add_edge("rank_alternatives", END)

    return builder.compile()


def run_alternative_provider_flow(
    diagnosis: str,
    location: str,
    insurance_plan: str,
    excluded_provider_id: str,
    preferred_window_days: int = 7,
    urgency: str = "Routine",
    max_results: int = 5,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    graph = build_alternative_provider_graph()
    use_mcp = os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}

    base_state: dict[str, Any] = {
        "diagnosis": diagnosis,
        "location": location,
        "insurance_plan": insurance_plan,
        "excluded_provider_id": excluded_provider_id,
        "preferred_window_days": preferred_window_days,
        "urgency": urgency,
        "max_results": max_results,
        "inferred_specialties": [],
        "alternatives": [],
        "missing_information": [],
        "llm_used": False,
        "mcp_enabled": use_mcp,
        "tools_invoked": [],
        "progress_callback": progress_callback,
    }

    try:
        if use_mcp:
            with SpecialistRecommendationMCPClient(
                caller_role=ALTERNATIVE_PROVIDER_ROLE
            ) as mcp_client:
                base_state["mcp_client"] = mcp_client
                final_state = graph.invoke(base_state)
        else:
            base_state["mcp_client"] = None
            final_state = graph.invoke(base_state)
    except MCPClientError:
        raise

    alts = final_state["alternatives"]
    in_window_count = sum(1 for a in alts if a.get("within_preferred_window"))
    all_exceeded = bool(alts) and in_window_count == 0

    return {
        "request_id": str(uuid4()),
        "generated_at": datetime.now(UTC).isoformat(),
        "excluded_provider_id": excluded_provider_id,
        "preferred_window_days": preferred_window_days,
        "urgency": urgency,
        "inferred_specialties": final_state["inferred_specialties"],
        "alternatives": alts,
        "in_window_count": in_window_count,
        "missing_information": final_state["missing_information"],
        "llm_used": final_state["llm_used"],
        "decision_trace": {
            "capability": "alternative_provider_suggestion",
            "caller_role": ALTERNATIVE_PROVIDER_ROLE,
            "mcp_enabled": final_state["mcp_enabled"],
            "tools_invoked": final_state["tools_invoked"],
            "human_review_required": (
                urgency == "Urgent"
                or all_exceeded
                or any(a["score"] < 0.55 for a in alts)
            ),
        },
    }
