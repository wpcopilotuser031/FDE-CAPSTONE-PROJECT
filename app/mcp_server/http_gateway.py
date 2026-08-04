from __future__ import annotations

from typing import Any

from app.mcp_server.server import _authorize_tool_call
from app.mcp_server.tools import (
    check_provider_in_network,
    list_provider_insurance_plans,
    map_diagnosis_to_specialties,
    patient_insurance_profile,
    retrieve_candidate_providers,
)


def call_tool_http(tool_name: str, arguments: dict[str, Any]) -> Any:
    caller_role = str(arguments.get("caller_role", "")).strip()
    internal_key = str(arguments.get("internal_key", "")).strip()
    user_role = arguments.get("user_role")
    user_role = str(user_role).strip() if user_role is not None else None

    _authorize_tool_call(tool_name, caller_role, internal_key, user_role=user_role)

    if tool_name == "diagnosis_to_specialty":
        diagnosis = str(arguments.get("diagnosis", "")).strip()
        return map_diagnosis_to_specialties(diagnosis)

    if tool_name == "provider_candidates":
        diagnosis = str(arguments.get("diagnosis", "")).strip()
        location = str(arguments.get("location", "")).strip()
        max_candidates = int(arguments.get("max_candidates", 10))
        return retrieve_candidate_providers(diagnosis, location, max_candidates)

    if tool_name == "insurance_eligibility":
        provider_id = str(arguments.get("provider_id", "")).strip()
        insurance_plan = str(arguments.get("insurance_plan", "")).strip()
        return check_provider_in_network(provider_id, insurance_plan)

    if tool_name == "patient_insurance_profile":
        return patient_insurance_profile(
            patient_id=str(arguments.get("patient_id", "")).strip(),
            patient_name=str(arguments.get("patient_name", "")).strip(),
            member_id=str(arguments.get("member_id", "")).strip(),
            insurance_plan=str(arguments.get("insurance_plan", "")).strip(),
        )

    if tool_name == "provider_insurance_plans":
        provider_id = str(arguments.get("provider_id", "")).strip()
        return list_provider_insurance_plans(provider_id)

    raise ValueError(f"Unsupported MCP tool '{tool_name}'.")
