from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Any
from urllib import error, request as urlrequest

from app.agents.alternative_provider_agent import build_agent_card as build_alternative_provider_card
from app.agents.capability_router import infer_capability_from_query, infer_query
from app.agents.conversational_assistant_agent import build_agent_card as build_conversational_assistant_card
from app.agents.insurance_validation_agent import build_agent_card as build_insurance_validation_card
from app.agents.provider_discovery_agent import build_agent_card as build_provider_discovery_card
from app.agents.referral_triage_agent import build_agent_card as build_referral_triage_card
from app.agents.specialist_recommendation_agent import build_agent_card as build_specialist_card


@dataclass
class AgentCard:
    agent_id: str
    capability: str
    display_name: str
    description: str
    input_contract: dict[str, Any]
    rbac_role: str
    mcp_tools: list[str]


def _build_agent_cards() -> list[AgentCard]:
    card_builders = [
        build_specialist_card,
        build_referral_triage_card,
        build_provider_discovery_card,
        build_insurance_validation_card,
        build_alternative_provider_card,
        build_conversational_assistant_card,
    ]
    return [
        AgentCard(
            agent_id=card_data["agent_id"],
            capability=card_data["capability"],
            display_name=card_data["display_name"],
            description=card_data["description"],
            input_contract=card_data["input_contract"],
            rbac_role=card_data["rbac_role"],
            mcp_tools=card_data["mcp_tools"],
        )
        for card_data in (builder() for builder in card_builders)
    ]


_AGENT_CARDS: list[AgentCard] = _build_agent_cards()

_ACTIONABLE_CAPABILITIES = {
    "specialist_recommendation",
    "referral_triage",
    "insurance_validation",
    "provider_discovery",
    "alternative_provider_suggestion",
}

_ROUTING_CONFIDENCE_THRESHOLD = 0.6

# Phrases that imply the user wants data/actions this platform never implemented as a
# real agent/capability (e.g. patient medical history, chart notes, scheduling). These
# must be hard-blocked with a deterministic message BEFORE the conversational assistant
# LLM is invoked - otherwise the LLM may "helpfully" answer anyway by grounding itself in
# unrelated leftover context (e.g. a previous specialist recommendation), which looks like
# a real answer but is not backed by any actual data source or authorization check.
_UNSUPPORTED_TOPIC_PHRASES = (
    "patient history",
    "medical history",
    "medical record",
    "health record",
    "chart note",
    "clinical note",
    "lab result",
    "test result",
    "prescription",
    "medication list",
    "diagnosis history",
    "book an appointment",
    "book appointment",
    "schedule an appointment",
    "schedule appointment",
)


def _matches_unsupported_topic(question: str) -> str | None:
    question_lower = question.lower()
    for phrase in _UNSUPPORTED_TOPIC_PHRASES:
        if phrase in question_lower:
            return phrase
    return None

# Human end-user role -> capabilities that role is permitted to trigger, either
# explicitly or via the conversational assistant's auto-routing. This is a second,
# human-facing RBAC layer on top of the existing agent-to-MCP-tool RBAC in
# app/mcp_server/server.py (USE_CASE_TOOL_MAP), which governs service identity
# rather than the logged-in end user's role.
ROLE_CAPABILITY_MAP: dict[str, set[str]] = {
    "patient": {
        "specialist_recommendation",
        "alternative_provider_suggestion",
        "insurance_validation",
        "provider_discovery",
        "conversational_assistant",
    },
    "provider": {
        "specialist_recommendation",
        "alternative_provider_suggestion",
        "referral_triage",
        "insurance_validation",
        "provider_discovery",
        "conversational_assistant",
    },
    "care_agent": {
        "specialist_recommendation",
        "alternative_provider_suggestion",
        "referral_triage",
        "insurance_validation",
        "provider_discovery",
        "conversational_assistant",
    },
}


def _role_allows(caller_role: str | None, capability: str) -> bool:
    if caller_role is None:
        # No authenticated end-user role attached to this call (e.g. server-to-server
        # or test harness) - fall back to permissive behavior for backward compatibility.
        return True
    allowed = ROLE_CAPABILITY_MAP.get(caller_role.strip().lower())
    if allowed is None:
        return False
    return capability in allowed

def _invoke_agent_http(capability: str, payload: dict[str, Any]) -> dict[str, Any]:
    base_url = os.getenv("AGENT_RUNTIME_BASE_URL", "http://127.0.0.1:8091").rstrip("/")
    endpoint = f"{base_url}/api/v1/agents/{capability}/invoke"
    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
    except error.URLError as exc:
        raise RuntimeError(f"HTTP agent call failed for capability '{capability}': {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"HTTP agent call returned non-JSON response for capability '{capability}'.") from exc

    if isinstance(parsed, dict):
        return parsed
    raise RuntimeError(f"HTTP agent call returned invalid payload for capability '{capability}'.")


def _invoke_agent(capability: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    transport = os.getenv("AGENT_CALL_TRANSPORT", "http").strip().lower()
    if transport != "http":
        raise RuntimeError(
            "Only HTTP transport is supported for agent invocation. Set AGENT_CALL_TRANSPORT=http."
        )
    return _invoke_agent_http(capability, payload), "http"


def list_agent_cards() -> list[dict[str, Any]]:
    return [asdict(card) for card in _AGENT_CARDS]


def _card_by_capability(capability: str) -> AgentCard | None:
    for card in _AGENT_CARDS:
        if card.capability == capability:
            return card
    return None


def _select_capability(params: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    requested_capability = str(params.get("capability", "")).strip()
    payload = params.get("payload")
    query = str(params.get("query", "")).strip()

    if not isinstance(payload, dict):
        payload = {}

    if requested_capability:
        return requested_capability, payload

    if query:
        interpretation = infer_query(query)
        if interpretation.decision.capability != "unknown":
            for key, value in interpretation.slots.items():
                if value and key not in payload:
                    payload[key] = value
            return interpretation.decision.capability, payload

        heuristic = infer_capability_from_query(query)
        return heuristic.capability, payload

    return "unknown", payload


def _missing_required_fields(card: AgentCard, slots: dict[str, Any]) -> list[str]:
    return [field for field in card.input_contract.get("required", []) if not slots.get(field)]


def _route_conversational_assistant(payload: dict[str, Any], caller_role: str | None = None) -> dict[str, Any]:
    """Answers via the conversational assistant, but first tries to detect whether the
    question actually implies an actionable capability (e.g. "recommend a specialist for
    chest pain in Austin with Aetna") and, if enough slots are present AND the caller's
    role is permitted to use that capability, executes it live so the assistant can
    ground its answer in real computed data instead of just talking generically about
    the platform."""
    question = str(payload.get("question", "")).strip()
    asker_role = payload.get("asker_role")
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    context = dict(context)

    if question:
        unsupported_phrase = _matches_unsupported_topic(question)
        if unsupported_phrase:
            # Hard stop: don't let the LLM "helpfully" answer this by grounding itself
            # in unrelated leftover context (e.g. a prior specialist recommendation).
            # There is no real agent/data source behind this request, so refuse
            # deterministically instead of letting the model improvise.
            return {
                "selected_capability": "conversational_assistant",
                "selected_agent_card": asdict(_card_by_capability("conversational_assistant")),
                "agent_transport": "none",
                "agent_result": {
                    "answer": (
                        "I'm not able to help with that. This assistant only supports "
                        "specialist recommendations, referral triage, insurance validation, "
                        "provider discovery, and alternative provider suggestions - it does "
                        "not have access to patient medical history, records, or scheduling."
                    ),
                    "follow_up_suggestions": [],
                    "llm_used": False,
                    "decision_trace": {
                        "capability": "unsupported",
                        "caller_role": caller_role,
                        "mcp_enabled": False,
                        "tools_invoked": [],
                        "human_review_required": False,
                    },
                },
            }

    routed_capability: str | None = None
    routed_card: AgentCard | None = None
    routed_result: dict[str, Any] | None = None

    if question:
        interpretation = infer_query(question)
        decision = interpretation.decision

        if decision.capability in _ACTIONABLE_CAPABILITIES and decision.confidence >= _ROUTING_CONFIDENCE_THRESHOLD:
            if not _role_allows(caller_role, decision.capability):
                # Hard stop: the conversational assistant must not use the LLM to
                # "work around" a denied capability (e.g. by falling back on stale
                # context from an earlier, permitted turn). Return a deterministic
                # authorization error instead of invoking the assistant agent.
                denied_card = _card_by_capability(decision.capability)
                return {
                    "selected_capability": "conversational_assistant",
                    "selected_agent_card": asdict(_card_by_capability("conversational_assistant")),
                    "agent_transport": "none",
                    "agent_result": {
                        "answer": (
                            "You are not authorized to perform this action. "
                            f"The '{denied_card.display_name if denied_card else decision.capability}' "
                            "capability is restricted to other roles."
                        ),
                        "follow_up_suggestions": [],
                        "llm_used": False,
                        "decision_trace": {
                            "capability": decision.capability,
                            "caller_role": caller_role,
                            "mcp_enabled": False,
                            "tools_invoked": [],
                            "human_review_required": False,
                        },
                    },
                }
            else:
                candidate_card = _card_by_capability(decision.capability)
                slots = {key: value for key, value in interpretation.slots.items() if value}

                if candidate_card:
                    missing = _missing_required_fields(candidate_card, slots)
                    if not missing:
                        try:
                            routed_result, _ = _invoke_agent(decision.capability, slots)
                            routed_capability = decision.capability
                            routed_card = candidate_card
                        except Exception as exc:  # noqa: BLE001
                            context["routing_attempt_failed"] = {
                                "capability": decision.capability,
                                "error": str(exc),
                            }
                    else:
                        context["routing_missing_fields"] = {
                            "capability": decision.capability,
                            "missing_fields": missing,
                        }

    if routed_result is not None:
        context["routed_capability_result"] = {
            "capability": routed_capability,
            "result": routed_result,
        }

    assistant_payload = {
        "question": question,
        "asker_role": asker_role,
        "context": context,
    }
    agent_result, transport = _invoke_agent("conversational_assistant", assistant_payload)

    response: dict[str, Any] = {
        "selected_capability": "conversational_assistant",
        "selected_agent_card": asdict(_card_by_capability("conversational_assistant")),
        "agent_transport": transport,
        "agent_result": agent_result,
    }
    if routed_capability and routed_card:
        response["routed_capability"] = routed_capability
        response["routed_agent_card"] = asdict(routed_card)
        response["routed_agent_result"] = routed_result
    return response


def route_capability(params: dict[str, Any], caller_role: str | None = None) -> dict[str, Any]:
    capability, payload = _select_capability(params)

    if capability == "conversational_assistant":
        return _route_conversational_assistant(payload, caller_role=caller_role)

    if not _role_allows(caller_role, capability):
        raise PermissionError(
            f"Role '{caller_role}' is not permitted to use capability '{capability}'."
        )

    card = _card_by_capability(capability)

    if not card:
        raise ValueError(
            f"No agent card registered for capability '{capability}'. Provide params.capability or a routable query."
        )

    result, transport = _invoke_agent(capability, payload)

    return {
        "selected_capability": capability,
        "selected_agent_card": asdict(card),
        "agent_transport": transport,
        "agent_result": result,
    }


def handle_jsonrpc_request(request: dict[str, Any], caller_role: str | None = None) -> dict[str, Any]:
    request_id = request.get("id")
    method = str(request.get("method", "")).strip()
    jsonrpc_version = request.get("jsonrpc")

    if jsonrpc_version != "2.0":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32600,
                "message": "Invalid Request: jsonrpc must be '2.0'.",
            },
        }

    try:
        if method == "agents.cards":
            result = {"agent_cards": list_agent_cards()}
        elif method == "capability.route":
            params = request.get("params", {})
            if not isinstance(params, dict):
                raise ValueError("params must be an object.")
            result = route_capability(params, caller_role=caller_role)
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }
    except ValueError as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32602,
                "message": str(exc),
            },
        }
    except PermissionError as exc:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32001,
                "message": str(exc),
            },
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": f"Server error: {exc}",
            },
        }
