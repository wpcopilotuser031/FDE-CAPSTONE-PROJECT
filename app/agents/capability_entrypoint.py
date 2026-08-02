from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from typing import Any
from urllib import error, request as urlrequest

from app.agents.alternative_provider_agent import build_agent_card as build_alternative_provider_card
from app.agents.capability_router import infer_capability_from_query, infer_query
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


def route_capability(params: dict[str, Any]) -> dict[str, Any]:
    capability, payload = _select_capability(params)
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


def handle_jsonrpc_request(request: dict[str, Any]) -> dict[str, Any]:
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
            result = route_capability(params)
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
    except Exception as exc:  # noqa: BLE001
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": -32000,
                "message": f"Server error: {exc}",
            },
        }
