from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from app.mcp_clients.specialist_recommendation_client import SpecialistRecommendationMCPClient
from app.mcp_server.tools import retrieve_candidate_providers

PROVIDER_DISCOVERY_ROLE = "provider_discovery"


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.provider_discovery.v1",
        "capability": "provider_discovery",
        "display_name": "Provider Discovery Agent",
        "description": "Finds candidate providers for a diagnosis in a given geography.",
        "input_contract": {
            "required": ["diagnosis", "location"],
            "optional": ["max_results"],
        },
        "rbac_role": PROVIDER_DISCOVERY_ROLE,
        "mcp_tools": ["provider_candidates"],
    }


def _use_mcp_tools() -> bool:
    return os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def provider_discovery_agent(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis = str(payload.get("diagnosis", "")).strip()
    location = str(payload.get("location", "")).strip()
    max_results = int(payload.get("max_results", 5))

    if not diagnosis or not location:
        return {
            "providers": [],
            "missing_information": ["diagnosis and location are required"],
            "decision_trace": {
                "capability": "provider_discovery",
                "caller_role": PROVIDER_DISCOVERY_ROLE,
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    tools_invoked: list[str] = []
    if _use_mcp_tools():
        with SpecialistRecommendationMCPClient(caller_role=PROVIDER_DISCOVERY_ROLE) as mcp_client:
            providers = mcp_client.provider_candidates(diagnosis, location, max_candidates=max_results)
            tools_invoked.append("provider_candidates")
    else:
        providers = retrieve_candidate_providers(diagnosis, location, max_candidates=max_results)

    return {
        "providers": providers,
        "generated_at": _utc_now(),
        "decision_trace": {
            "capability": "provider_discovery",
            "caller_role": PROVIDER_DISCOVERY_ROLE,
            "mcp_enabled": _use_mcp_tools(),
            "tools_invoked": tools_invoked,
        },
    }


__all__ = ["PROVIDER_DISCOVERY_ROLE", "build_agent_card", "provider_discovery_agent"]
