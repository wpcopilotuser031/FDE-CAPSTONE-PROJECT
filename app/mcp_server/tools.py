from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.agents.llm_gateway import LLMGatewayError, call_llm_json
from app.mcp_clients.specialist_recommendation_client import SpecialistRecommendationMCPClient
from app.config import DATA_DIR
from app.data_loader import load_json

_provider_index: Any | None = None


def _get_provider_index() -> Any:
    global _provider_index
    if _provider_index is None:
        # Lazy import avoids hard dependency on chromadb for non-RAG tool paths
        # such as insurance validation and patient coverage lookups.
        from app.rag.provider_index import ProviderIndex

        _provider_index = ProviderIndex()
    return _provider_index


def map_diagnosis_to_specialties(diagnosis: str) -> list[str]:
    mapping = load_json(DATA_DIR / "diagnosis_specialties.json")
    diagnosis_lower = diagnosis.strip().lower()

    specialties = set(mapping.get(diagnosis_lower, []))
    if not specialties:
        for key, mapped_specialties in mapping.items():
            if key in diagnosis_lower:
                specialties.update(mapped_specialties)

    return sorted(specialties)


def infer_specialties_llm_assisted(diagnosis: str) -> tuple[list[str], str]:
    """Use LLM to infer specialty candidates, then validate against known specialties."""

    mapping = load_json(DATA_DIR / "diagnosis_specialties.json")
    allowed_specialties = sorted({specialty for values in mapping.values() for specialty in values})

    system_prompt = (
        "You are a clinical triage assistant. "
        "Return strict JSON with key specialties as an array of strings. "
        "Only choose from this allowed set: "
        + ", ".join(allowed_specialties)
        + "."
    )
    user_prompt = (
        "Infer specialty options for this diagnosis text. "
        f"Diagnosis: {diagnosis}"
    )

    response_json = call_llm_json(system_prompt=system_prompt, user_prompt=user_prompt)
    raw_specialties = response_json.get("specialties", [])
    if not isinstance(raw_specialties, list):
        raise LLMGatewayError("LLM specialties payload is invalid.")

    normalized = []
    allowed_lookup = {specialty.lower(): specialty for specialty in allowed_specialties}
    for item in raw_specialties:
        value = str(item).strip()
        canonical = allowed_lookup.get(value.lower())
        if canonical and canonical not in normalized:
            normalized.append(canonical)

    if not normalized:
        raise LLMGatewayError(
            "LLM did not return supported specialties. "
            f"Diagnosis='{diagnosis}'. Allowed specialties: {', '.join(allowed_specialties)}"
        )

    return normalized, "llm"


def retrieve_candidate_providers(
    diagnosis: str,
    location: str,
    max_candidates: int = 10,
    mcp_client: SpecialistRecommendationMCPClient | None = None,
) -> list[dict[str, Any]]:
    if mcp_client:
        return mcp_client.provider_candidates(diagnosis, location, max_candidates=max_candidates)

    # Map diagnosis to specialty first, then search for providers of that specialty in the location
    specialties = infer_specialties_llm_assisted(diagnosis)[0]

    if not specialties:
        return []

    # Query providers by specialty and location
    specialty_str = " ".join(specialties)
    query = f"{specialty_str} in {location}"
    return _get_provider_index().query(query, top_k=max_candidates)


def check_provider_in_network(
    provider_id: str,
    insurance_plan: str,
    mcp_client: SpecialistRecommendationMCPClient | None = None,
) -> bool:
    if mcp_client:
        return mcp_client.insurance_eligibility(provider_id, insurance_plan)

    networks = load_json(DATA_DIR / "insurance_networks.json")
    eligible_providers = set(networks.get(insurance_plan, []))
    return provider_id in eligible_providers


def list_provider_insurance_plans(provider_id: str) -> list[str]:
    providers = load_json(DATA_DIR / "providers.json")
    provider_id_lower = provider_id.strip().lower()
    for provider in providers:
        if str(provider.get("provider_id", "")).strip().lower() == provider_id_lower:
            plans = provider.get("insurance_networks", [])
            if isinstance(plans, list):
                return [str(plan) for plan in plans if str(plan).strip()]
            return []
    return []


def _resolve_patient_id(patient_id: str, patient_name: str, member_id: str) -> str | None:
    if patient_id.strip():
        return patient_id.strip()

    users_payload = load_json(DATA_DIR / "users.json")
    users = users_payload.get("users", []) if isinstance(users_payload, dict) else []

    if member_id.strip():
        member_id_lower = member_id.strip().lower()
        for user in users:
            scope = str(user.get("scope", "")).strip()
            if scope.lower() == member_id_lower:
                return scope

    if patient_name.strip():
        patient_name_lower = patient_name.strip().lower()
        for user in users:
            display_name = str(user.get("display_name", "")).strip().lower()
            if display_name == patient_name_lower:
                scope = str(user.get("scope", "")).strip()
                if scope:
                    return scope

    return None


def patient_insurance_profile(
    patient_id: str = "",
    patient_name: str = "",
    member_id: str = "",
    insurance_plan: str = "",
) -> dict[str, Any]:
    resolved_patient_id = _resolve_patient_id(patient_id, patient_name, member_id)
    if not resolved_patient_id:
        return {
            "patient_id": None,
            "insurance_plan": None,
            "eligible": False,
            "patient_found": False,
            "eligibility_records": [],
            "missing_information": ["patient_id or patient_name or member_id"],
        }

    patients = load_json(DATA_DIR / "patients.json")
    resolved_lower = resolved_patient_id.lower()
    patient_row = next(
        (row for row in patients if str(row.get("patient_id", "")).strip().lower() == resolved_lower),
        None,
    )

    eligibility_rows = load_json(DATA_DIR / "eligibility.json")
    matching = [
        row
        for row in eligibility_rows
        if str(row.get("patient_id", "")).strip().lower() == resolved_lower
    ]

    plan = ""
    if patient_row:
        plan = str(patient_row.get("insurance_plan", "")).strip()
    if not plan and matching:
        plan = str(matching[0].get("insurance_plan", "")).strip()

    effective_plan = insurance_plan.strip() or plan
    effective_plan_lower = effective_plan.lower()

    filtered_rows = matching
    if effective_plan_lower:
        filtered_rows = [
            row
            for row in matching
            if str(row.get("insurance_plan", "")).strip().lower() == effective_plan_lower
        ]

    eligible = any(bool(row.get("eligible")) for row in filtered_rows)

    return {
        "patient_id": resolved_patient_id,
        "patient_name": str(patient_row.get("name", "")).strip() if patient_row else "",
        "insurance_plan": effective_plan or None,
        "eligible": eligible,
        "patient_found": patient_row is not None,
        "eligibility_records": [
            {
                "referral_id": row.get("referral_id"),
                "insurance_plan": row.get("insurance_plan"),
                "eligible": row.get("eligible"),
                "copay": row.get("copay"),
                "authorization_required": row.get("authorization_required"),
                "notes": row.get("notes"),
            }
            for row in filtered_rows
        ],
        "missing_information": [] if (effective_plan or patient_row or matching) else ["insurance plan"],
    }


def triage_assess(diagnosis: str, urgency_hint: str = "") -> dict[str, Any]:
    diagnosis_lower = diagnosis.strip().lower()
    urgency_hint_lower = urgency_hint.strip().lower()

    high_urgency_terms = {"chest pain", "stroke", "sepsis", "hemorrhage", "heart attack"}
    medium_urgency_terms = {"worsening", "persistent", "uncontrolled", "severe"}

    if "urgent" in urgency_hint_lower or any(term in diagnosis_lower for term in high_urgency_terms):
        triage_priority = "high"
        priority_score = 0.9
    elif "priority" in urgency_hint_lower or any(term in diagnosis_lower for term in medium_urgency_terms):
        triage_priority = "medium"
        priority_score = 0.65
    else:
        triage_priority = "low"
        priority_score = 0.4

    specialties = map_diagnosis_to_specialties(diagnosis)
    return {
        "triage_priority": triage_priority,
        "priority_score": priority_score,
        "recommended_specialties": specialties,
    }


def create_triage_ticket(
    reason: str,
    triage_priority: str,
    patient_id: str = "",
) -> dict[str, Any]:
    ticket_id = f"TCK-{str(uuid4()).split('-')[0].upper()}"
    return {
        "ticket_id": ticket_id,
        "status": "OPEN",
        "queue": "human-triage",
        "triage_priority": triage_priority,
        "patient_id": patient_id or None,
        "reason": reason,
        "created_at": datetime.now(UTC).isoformat(),
    }


def days_until(date_str: str) -> int:
    target = datetime.strptime(date_str, "%Y-%m-%d").date()
    today = datetime.now(UTC).date()
    return max((target - today).days, 0)


def score_provider(
    provider: dict[str, Any],
    specialties: list[str],
    requested_location: str,
    insurance_plan: str,
    mcp_client: SpecialistRecommendationMCPClient | None = None,
) -> float:
    score = 0.0

    if provider["specialty"] in specialties:
        score += 0.45
    if requested_location.lower().split(",")[0].strip() in provider["location"].lower():
        score += 0.25
    if check_provider_in_network(provider["provider_id"], insurance_plan, mcp_client=mcp_client):
        score += 0.2

    wait_days = days_until(provider["next_available_date"])
    score += max(0.0, 0.1 - (wait_days * 0.01))
    return round(score, 4)


def score_provider_with_breakdown(
    provider: dict[str, Any],
    specialties: list[str],
    requested_location: str,
    insurance_plan: str,
    mcp_client: SpecialistRecommendationMCPClient | None = None,
    accepts_insurance: bool | None = None,
    urgency: str = "Routine",
) -> tuple[float, dict[str, float]]:
    # Weight table: higher urgency shifts weight toward availability (wait time).
    _urgency_weights = {
        "Urgent":   {"specialty": 0.35, "location": 0.15, "insurance": 0.15, "wait_max": 0.35, "wait_decay": 0.035},
        "Priority": {"specialty": 0.40, "location": 0.20, "insurance": 0.20, "wait_max": 0.20, "wait_decay": 0.020},
        "Routine":  {"specialty": 0.45, "location": 0.25, "insurance": 0.20, "wait_max": 0.10, "wait_decay": 0.010},
    }
    weights = _urgency_weights.get(urgency, _urgency_weights["Routine"])

    specialty_component = weights["specialty"] if provider["specialty"] in specialties else 0.0
    location_component = weights["location"] if requested_location.lower().split(",")[0].strip() in provider["location"].lower() else 0.0
    in_network = accepts_insurance
    if in_network is None:
        in_network = check_provider_in_network(
            provider["provider_id"],
            insurance_plan,
            mcp_client=mcp_client,
        )
    insurance_component = weights["insurance"] if in_network else 0.0
    wait_days = days_until(provider["next_available_date"])
    wait_time_component = max(0.0, weights["wait_max"] - (wait_days * weights["wait_decay"]))

    total = round(specialty_component + location_component + insurance_component + wait_time_component, 4)
    return total, {
        "specialty_component": round(specialty_component, 4),
        "location_component": round(location_component, 4),
        "insurance_component": round(insurance_component, 4),
        "wait_time_component": round(wait_time_component, 4),
    }


def build_recommendation_rationale(
    provider: dict[str, Any],
    specialties: list[str],
    insurance_plan: str,
    mcp_client: SpecialistRecommendationMCPClient | None = None,
) -> str:
    reasons: list[str] = []

    if provider["specialty"] in specialties:
        reasons.append("specialty match")
    if check_provider_in_network(provider["provider_id"], insurance_plan, mcp_client=mcp_client):
        reasons.append("in-network")
    reasons.append(f"next availability {provider['next_available_date']}")
    return ", ".join(reasons)


def build_recommendation_rationale_llm_assisted(
    provider: dict[str, Any],
    specialties: list[str],
    insurance_plan: str,
    mcp_client: SpecialistRecommendationMCPClient | None = None,
    accepts_insurance: bool | None = None,
) -> tuple[str, str]:
    system_prompt = (
        "You are a referral recommendation assistant. "
        "Return strict JSON with key rationale. "
        "Keep rationale short, factual, and under 22 words."
    )
    in_network = accepts_insurance
    if in_network is None:
        in_network = check_provider_in_network(provider["provider_id"], insurance_plan, mcp_client=mcp_client)

    user_prompt = (
        "Draft recommendation rationale for this provider:\n"
        f"provider_name={provider['provider_name']}\n"
        f"specialty={provider['specialty']}\n"
        f"location={provider['location']}\n"
        f"next_available_date={provider['next_available_date']}\n"
        f"requested_specialties={specialties}\n"
        f"insurance_plan={insurance_plan}\n"
        f"is_in_network={in_network}"
    )

    response_json = call_llm_json(system_prompt=system_prompt, user_prompt=user_prompt, max_tokens=120)
    rationale = str(response_json.get("rationale", "")).strip()
    if not rationale:
        raise LLMGatewayError("LLM rationale payload is empty.")
    return rationale, "llm"
