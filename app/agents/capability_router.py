from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

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

ALTERNATIVE_PROVIDER_KEYWORDS = {
    "alternative",
    "alternatives",
    "alternate",
    "another",
    "other",
    "instead",
    "exclude",
    "excluding",
    "except",
    "besides",
    "replacement",
}

TRIAGE_KEYWORDS = {
    "triage",
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

DOCUMENT_EXTRACTION_KEYWORDS = {
    "extract",
    "icd",
    "cpt",
    "diagnosis code",
    "procedure code",
    "document",
    "referral note",
    "clinical code",
    "medical code",
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
        "excluded_provider_id": _extract_field(
            r"(?:excluding|except|exclude)\s+(?:provider\s+)?([A-Za-z0-9\-_]+)",
            query,
        ),
        "preferred_window_days": _extract_field(r"(?:within|in)\s+(\d+)\s+days?", query),
        "urgency": _extract_field(r"urgency\s*[:=-]\s*([A-Za-z]+)", query),
    }


def infer_capability_from_query(query: str) -> CapabilityDecision:
    query_lower = query.lower()
    recommendation_score = sum(1 for keyword in RECOMMENDATION_KEYWORDS if keyword in query_lower)
    alternative_score = 0
    if any(term in query_lower for term in {"alternative", "alternatives", "alternate", "another"}):
        alternative_score += 2
    if any(term in query_lower for term in {"other provider", "other providers", "instead of", "besides", "except", "excluding", "exclude"}):
        alternative_score += 2
    if "provider" in query_lower and ("other" in query_lower or "alternative" in query_lower):
        alternative_score += 1
    triage_score = sum(1 for keyword in TRIAGE_KEYWORDS if keyword in query_lower)
    insurance_score = sum(1 for keyword in INSURANCE_KEYWORDS if keyword in query_lower)
    discovery_score = sum(1 for keyword in DISCOVERY_KEYWORDS if keyword in query_lower)
    extraction_score = sum(1 for keyword in DOCUMENT_EXTRACTION_KEYWORDS if keyword in query_lower)

    scored_capabilities = [
        ("alternative_provider_suggestion", alternative_score),
        ("specialist_recommendation", recommendation_score),
        ("referral_triage", triage_score),
        ("insurance_validation", insurance_score),
        ("provider_discovery", discovery_score),
        ("document_code_extraction", extraction_score),
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


def infer_query_with_llm(query: str, context: dict[str, Any] | None = None) -> QueryInterpretation:
    system_prompt = (
        "You are a healthcare referral capability router. Route to the most specific capability:\n"
        "- specialist_recommendation: when asking for provider/specialist recommendations for a DIAGNOSIS (e.g., 'I have chest pain, find me cardiologists')\n"
        "- referral_triage: when explicitly asking to assess priority/urgency level of a referral\n"
        "- alternative_provider_suggestion: when asking for alternatives to a previously recommended provider\n"
        "- insurance_validation: when asking if a provider is in-network\n"
        "- provider_discovery: when DIRECTLY SEARCHING for providers by specialty NAME (e.g., 'find me cardiologists', 'search for gastroenterologists')\n"
        "\n"
        "KEY DISTINCTION:\n"
        "- 'I have heart pain, find me specialists' → specialist_recommendation (diagnosis-based)\n"
        "- 'Find me Cardiology providers' → provider_discovery (specialty-based)\n"
        "\n"
        "When user mentions specialty names (Cardiology, Gastroenterology, Orthopedics, etc.):\n"
        "1. If paired with a DIAGNOSIS ('I have chest pain, find cardiologists') → specialist_recommendation\n"
        "2. If just the SPECIALTY NAME ('find cardiologists', 'search gastroenterology') → provider_discovery\n"
        "\n"
        "IMPORTANT: If a previous result is provided in context with recommendations, and the user asks for 'alternatives to [Provider Name]':\n"
        "1. Route to 'alternative_provider_suggestion'\n"
        "2. Extract the provider_id by matching [Provider Name] against the recommendations in context\n"
        "3. Return the matched provider_id as 'excluded_provider_id'\n"
        "\n"
        "Return only strict JSON with keys: capability, confidence, reason, diagnosis, location, insurance_plan, "
        "excluded_provider_id, preferred_window_days, urgency. "
        "If a field is missing, return null. Confidence must be between 0 and 1."
    )

    context_str = ""
    if context and "routed_capability_result" in context:
        prev_result = context["routed_capability_result"].get("result", {})
        if prev_result.get("recommendations"):
            context_str = "\nPrevious recommendations available:\n"
            for rec in prev_result["recommendations"]:
                context_str += f"- {rec.get('provider_name')} (ID: {rec.get('provider_id')}, {rec.get('specialty')})\n"

    user_prompt = f"User query: {query}{context_str}"

    response_json = call_llm_json(system_prompt=system_prompt, user_prompt=user_prompt)

    capability = str(response_json.get("capability", "unknown"))
    confidence = float(response_json.get("confidence", 0.35))
    reason = str(response_json.get("reason", "LLM routing decision"))

    if capability not in {
        "specialist_recommendation",
        "referral_triage",
        "insurance_validation",
        "provider_discovery",
        "alternative_provider_suggestion",
        "unknown",
    }:
        capability = "unknown"

    slots = {
        "diagnosis": response_json.get("diagnosis"),
        "location": response_json.get("location"),
        "insurance_plan": response_json.get("insurance_plan"),
        "excluded_provider_id": response_json.get("excluded_provider_id"),
        "preferred_window_days": response_json.get("preferred_window_days"),
        "urgency": response_json.get("urgency"),
    }
    slots = {key: (str(value).strip() if value is not None else None) for key, value in slots.items()}

    return QueryInterpretation(
        decision=CapabilityDecision(capability=capability, confidence=round(max(0.0, min(confidence, 1.0)), 2), reason=reason),
        slots=slots,
        source="llm",
    )


def infer_query(query: str, context: dict[str, Any] | None = None) -> QueryInterpretation:
    return infer_query_with_llm(query, context=context)
