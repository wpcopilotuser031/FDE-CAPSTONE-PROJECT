from __future__ import annotations

from dataclasses import dataclass
import re

from app.agents.llm_gateway import LLMGatewayError, call_llm_json


@dataclass
class CapabilityDecision:
    capability: str
    confidence: float
    reason: str


@dataclass
class QueryInterpretation:
    decision: CapabilityDecision
    slots: dict[str, str | None]
    source: str


RECOMMENDATION_KEYWORDS = {
    "recommend",
    "specialist",
    "doctor",
    "provider",
    "diagnosis",
    "insurance",
    "network",
    "referral",
}

TRIAGE_KEYWORDS = {
    "triage",
    "urgent",
    "acuity",
    "priority",
    "severity",
}

INSURANCE_KEYWORDS = {
    "eligibility",
    "coverage",
    "payer",
    "in-network",
    "out-of-network",
}

DISCOVERY_KEYWORDS = {
    "find",
    "discover",
    "nearby",
    "directory",
}


def _extract_field(pattern: str, query: str) -> str | None:
    match = re.search(pattern, query, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip()


def heuristic_slot_extraction(query: str) -> dict[str, str | None]:
    return {
        "diagnosis": _extract_field(r"diagnosis\s*[:=-]\s*([^,;]+)", query),
        "location": _extract_field(r"location\s*[:=-]\s*([^,;]+)", query),
        "insurance_plan": _extract_field(r"insurance\s*[:=-]\s*([^,;]+)", query),
    }


def infer_capability_from_query(query: str) -> CapabilityDecision:
    query_lower = query.lower()
    recommendation_score = sum(1 for keyword in RECOMMENDATION_KEYWORDS if keyword in query_lower)
    triage_score = sum(1 for keyword in TRIAGE_KEYWORDS if keyword in query_lower)
    insurance_score = sum(1 for keyword in INSURANCE_KEYWORDS if keyword in query_lower)
    discovery_score = sum(1 for keyword in DISCOVERY_KEYWORDS if keyword in query_lower)

    scored_capabilities = [
        ("specialist_recommendation", recommendation_score),
        ("referral_triage", triage_score),
        ("insurance_validation", insurance_score),
        ("provider_discovery", discovery_score),
    ]
    capability, score = max(scored_capabilities, key=lambda item: item[1])

    if score >= 2:
        confidence = min(0.5 + (score * 0.08), 0.95)
        return CapabilityDecision(
            capability=capability,
            confidence=round(confidence, 2),
            reason=f"The query best matches capability '{capability}'.",
        )

    return CapabilityDecision(
        capability="unknown",
        confidence=0.35,
        reason="Not enough referral recommendation signals found.",
    )


def infer_query_with_llm(query: str) -> QueryInterpretation:
    system_prompt = (
        "You are a healthcare referral capability router. "
        "Return only strict JSON with keys: capability, confidence, reason, diagnosis, location, insurance_plan. "
        "Allowed capability values: specialist_recommendation, referral_triage, insurance_validation, provider_discovery, unknown. "
        "If a field is missing, return null. Confidence must be between 0 and 1."
    )
    user_prompt = f"User query: {query}"

    response_json = call_llm_json(system_prompt=system_prompt, user_prompt=user_prompt)

    capability = str(response_json.get("capability", "unknown"))
    confidence = float(response_json.get("confidence", 0.35))
    reason = str(response_json.get("reason", "LLM routing decision"))

    if capability not in {
        "specialist_recommendation",
        "referral_triage",
        "insurance_validation",
        "provider_discovery",
        "unknown",
    }:
        capability = "unknown"

    slots = {
        "diagnosis": response_json.get("diagnosis"),
        "location": response_json.get("location"),
        "insurance_plan": response_json.get("insurance_plan"),
    }
    slots = {key: (str(value).strip() if value is not None else None) for key, value in slots.items()}

    return QueryInterpretation(
        decision=CapabilityDecision(capability=capability, confidence=round(max(0.0, min(confidence, 1.0)), 2), reason=reason),
        slots=slots,
        source="llm",
    )


def infer_query(query: str) -> QueryInterpretation:
    return infer_query_with_llm(query)
