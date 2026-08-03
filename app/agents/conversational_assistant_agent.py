from __future__ import annotations

from typing import Any

from app.agents.llm_gateway import call_llm_json

CONVERSATIONAL_ASSISTANT_ROLE = "conversational_assistant"

_SYSTEM_PROMPT = (
    "You are a receptionist for an Intelligent Care Coordination & Referral Management Platform. "
    "Your role is to route questions to the right department and report what you find - NOT to make decisions or suggestions on your own. "
    "If a 'context' JSON object is provided with a 'routed_capability_result' key, a backend workflow was just executed. "
    "Summarize ONLY the actual data returned by that workflow - provider names, scores, wait times, specialties, eligibility status, etc. "
    "NEVER invent alternatives, suggestions, phone numbers, or workarounds. "
    "If the workflow returned empty results (no specialists found, no in-network providers, etc.), state that fact plainly: 'No specialists found in our system.' "
    "Do NOT suggest calling insurance companies, urgent care, or other workarounds - that is not your role. "
    "If context contains 'routing_missing_fields', ask the user for exactly those missing fields in plain language. "
    "Keep answers concise (under 100 words) and professional. "
    'Respond ONLY with a JSON object: {"answer": "...", "follow_up_suggestions": ["...", "..."]}. '
    "follow_up_suggestions should be 0-3 natural-language follow-up questions the user might ask about the result."
)


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.conversational_assistant.v1",
        "capability": "conversational_assistant",
        "display_name": "Conversational Assistant",
        "description": (
            "Answers free-form questions from patients, caregivers, providers, and payers "
            "about referrals, specialists, insurance, and platform usage, grounded in the "
            "most recent workflow context when available."
        ),
        "input_contract": {
            "required": ["question"],
            "optional": ["context", "asker_role"],
        },
        "rbac_role": CONVERSATIONAL_ASSISTANT_ROLE,
        "mcp_tools": [],
    }


def _format_recommendations(recommendations: list[dict[str, Any]]) -> str:
    """Format specialist recommendations as readable text."""
    if not recommendations:
        return "No recommendations found."

    lines = [f"Found {len(recommendations)} recommendation(s):"]
    for i, rec in enumerate(recommendations[:5], 1):  # Show top 5
        name = rec.get("provider_name", "Unknown")
        specialty = rec.get("specialty", "Unknown specialty")
        available = rec.get("next_available_date", "TBD")
        score = rec.get("score", 0)
        in_network = "✓ In-network" if rec.get("accepts_insurance") else "❌ Out-of-network"
        lines.append(
            f"{i}. {name} – {specialty} | {in_network} | Available: {available} | Score: {score:.2f}"
        )
    return "\n".join(lines)


def _fallback_answer(context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Generate fallback response. If context has routed results, format those instead of generic error."""
    # If LLM failed but we have actual agent results, display them anyway
    if context and "routed_capability_result" in context:
        routed = context["routed_capability_result"]
        result = routed.get("result", {})

        # Format specialist recommendations
        if routed.get("capability") == "specialist_recommendation":
            recommendations = result.get("recommendations", [])
            answer = _format_recommendations(recommendations)
            if recommendations:
                return {
                    "answer": answer,
                    "follow_up_suggestions": [
                        "Show me alternatives to the top provider",
                        "Filter by in-network providers only",
                        "What's the appointment window for each?",
                    ],
                }

    # Generic fallback if no context
    return {
        "answer": (
            "I couldn't reach the language model just now, so I can't answer that in "
            "detail. Please try again shortly, or contact your care coordinator for "
            "urgent questions."
        ),
        "follow_up_suggestions": [],
    }


def conversational_assistant_agent(payload: dict[str, Any]) -> dict[str, Any]:
    question = str(payload.get("question", "")).strip()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    asker_role = str(payload.get("asker_role", "")).strip() or "end user"

    decision_trace = {
        "capability": "conversational_assistant",
        "caller_role": CONVERSATIONAL_ASSISTANT_ROLE,
        "mcp_enabled": False,
        "tools_invoked": [],
        "human_review_required": False,
    }

    if not question:
        return {
            "answer": "Please type a question so I can help.",
            "follow_up_suggestions": [],
            "llm_used": False,
            "decision_trace": decision_trace,
        }

    user_prompt = (
        f"Asker role: {asker_role}\n"
        f"Question: {question}\n"
        f"Context (JSON, may be empty): {context}"
    )

    llm_used = False
    try:
        result = call_llm_json(_SYSTEM_PROMPT, user_prompt, max_tokens=400)
        answer = str(result.get("answer", "")).strip()
        follow_ups = result.get("follow_up_suggestions")
        if not isinstance(follow_ups, list):
            follow_ups = []
        follow_ups = [str(item).strip() for item in follow_ups if str(item).strip()][:3]
        if not answer:
            raise ValueError("LLM returned an empty answer.")
        llm_used = True
    except Exception:  # noqa: BLE001
        # LLM failed - but check if we have routed agent results to display anyway
        fallback = _fallback_answer(context=context)
        answer = fallback["answer"]
        follow_ups = fallback.get("follow_up_suggestions", [])

    return {
        "answer": answer,
        "follow_up_suggestions": follow_ups,
        "llm_used": llm_used,
        "decision_trace": decision_trace,
    }


__all__ = [
    "CONVERSATIONAL_ASSISTANT_ROLE",
    "build_agent_card",
    "conversational_assistant_agent",
]
