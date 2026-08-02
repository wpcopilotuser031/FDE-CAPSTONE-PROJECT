from __future__ import annotations

from typing import Any

from app.agents.llm_gateway import call_llm_json

CONVERSATIONAL_ASSISTANT_ROLE = "conversational_assistant"

_SYSTEM_PROMPT = (
    "You are the AI assistant embedded in an Intelligent Care Coordination & Referral "
    "Management Platform used by patients, caregivers, primary care providers, specialists, "
    "and payers. Answer the user's question clearly, in plain language appropriate for the "
    "asker's role. If a 'context' JSON object is provided, ground your answer in it - for "
    "example the most recent specialist recommendations, alternative providers, or audit "
    "trace - and never invent provider names, scores, dates, or insurance details that are "
    "not present in the context. If context contains a 'routed_capability_result' key, an "
    "agent workflow was just executed live to answer this exact question - summarize its "
    "actual data (provider names, scores, wait times, specialties, etc.) directly instead of "
    "giving a generic answer. If context contains 'routing_missing_fields', the platform "
    "detected the user wants to run a specific workflow but is missing required details - ask "
    "the user for exactly those missing fields in plain language. If you lack enough "
    "information to answer confidently, say so plainly and suggest what the user should "
    "provide or do next (e.g. submit a referral, run a recommendation, or contact a care "
    "coordinator). Keep answers concise (under 150 words) unless the user explicitly asks for "
    "more detail. "
    'Respond ONLY with a JSON object of the shape: {"answer": "...", "follow_up_suggestions": ["...", "..."]}. '
    "follow_up_suggestions should be 0-3 short natural-language next questions the user might ask."
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


def _fallback_answer() -> dict[str, Any]:
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
        fallback = _fallback_answer()
        answer = fallback["answer"]
        follow_ups = fallback["follow_up_suggestions"]

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
