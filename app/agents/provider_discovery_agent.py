from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from app.config import DATA_DIR
from app.data_loader import load_json
from app.mcp_clients.specialist_recommendation_client import SpecialistRecommendationMCPClient
from app.mcp_server.tools import days_until, retrieve_candidate_providers

PROVIDER_DISCOVERY_ROLE = "provider_discovery"


def build_agent_card() -> dict[str, Any]:
    return {
        "agent_id": "agent.provider_discovery.v1",
        "capability": "provider_discovery",
        "display_name": "Provider Discovery Agent",
        "description": "Finds candidate providers by diagnosis or specialty in a given geography.",
        "input_contract": {
            "required": ["location"],
            "optional": ["diagnosis", "specialty", "insurance_plan", "preferred_window_days", "max_results"],
        },
        "rbac_role": PROVIDER_DISCOVERY_ROLE,
        "mcp_tools": ["provider_candidates"],
    }


def _use_mcp_tools() -> bool:
    return os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _split_specialties(raw: str) -> list[str]:
    normalized = raw.replace("/", ",").replace("|", ",")
    normalized = normalized.replace(" and ", ",").replace(" or ", ",")
    values = [part.strip() for part in normalized.split(",")]
    return [value for value in values if value]


def _filter_local_providers(
    *,
    location: str,
    specialties: list[str],
    insurance_plan: str,
    preferred_window_days: int,
    max_results: int,
) -> list[dict[str, Any]]:
    providers = load_json(DATA_DIR / "providers.json")
    location_lower = location.lower()
    specialty_set = {item.lower() for item in specialties}
    insurance_lower = insurance_plan.lower()

    filtered: list[dict[str, Any]] = []
    for provider in providers:
        provider_location = str(provider.get("location", "")).lower()
        if location_lower and location_lower not in provider_location:
            continue

        provider_specialty = str(provider.get("specialty", ""))
        if specialty_set and provider_specialty.lower() not in specialty_set:
            continue

        provider_networks = [str(item) for item in provider.get("insurance_networks", [])]
        if insurance_lower and insurance_lower not in {item.lower() for item in provider_networks}:
            continue

        if preferred_window_days > 0:
            next_date = str(provider.get("next_available_date", ""))
            if not next_date or days_until(next_date) > preferred_window_days:
                continue

        filtered.append(dict(provider))

    filtered.sort(key=lambda item: str(item.get("next_available_date", "9999-12-31")))
    return filtered[:max_results]


def provider_discovery_agent(payload: dict[str, Any]) -> dict[str, Any]:
    diagnosis = str(payload.get("diagnosis", "")).strip()
    specialty = str(payload.get("specialty", "")).strip()
    location = str(payload.get("location", "")).strip()
    insurance_plan = str(payload.get("insurance_plan", "")).strip()
    preferred_window_days = int(payload.get("preferred_window_days", 0))
    max_results = int(payload.get("max_results", 5))

    missing_information: list[str] = []
    if not location:
        missing_information.append("location")
    if not diagnosis and not specialty:
        missing_information.append("diagnosis or specialty")

    if missing_information:
        return {
            "providers": [],
            "missing_information": missing_information,
            "decision_trace": {
                "capability": "provider_discovery",
                "caller_role": PROVIDER_DISCOVERY_ROLE,
                "mcp_enabled": _use_mcp_tools(),
                "tools_invoked": [],
            },
        }

    tools_invoked: list[str] = []
    if specialty:
        specialties = _split_specialties(specialty)
        providers = _filter_local_providers(
            location=location,
            specialties=specialties,
            insurance_plan=insurance_plan,
            preferred_window_days=preferred_window_days,
            max_results=max_results,
        )
    elif _use_mcp_tools():
        with SpecialistRecommendationMCPClient(caller_role=PROVIDER_DISCOVERY_ROLE) as mcp_client:
            providers = mcp_client.provider_candidates(diagnosis, location, max_candidates=max_results)
            tools_invoked.append("provider_candidates")
    else:
        providers = retrieve_candidate_providers(diagnosis, location, max_candidates=max_results)

    if insurance_plan and not specialty:
        insurance_lower = insurance_plan.lower()
        providers = [
            item
            for item in providers
            if insurance_lower in {str(network).lower() for network in item.get("insurance_networks", [])}
        ]

    if preferred_window_days > 0 and not specialty:
        providers = [
            item
            for item in providers
            if str(item.get("next_available_date", "")) and days_until(str(item.get("next_available_date"))) <= preferred_window_days
        ]
        providers.sort(key=lambda item: str(item.get("next_available_date", "9999-12-31")))
        providers = providers[:max_results]

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
