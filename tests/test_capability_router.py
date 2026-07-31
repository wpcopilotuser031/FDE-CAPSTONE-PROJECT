from app.agents.capability_router import (
    heuristic_slot_extraction,
    infer_capability_from_query,
    infer_query,
)
from app.agents.llm_gateway import LLMGatewayError


def test_infer_specialist_recommendation_capability() -> None:
    query = "Recommend specialist for diagnosis chest pain with Aetna insurance"
    decision = infer_capability_from_query(query)
    assert decision.capability == "specialist_recommendation"
    assert decision.confidence >= 0.5


def test_infer_unknown_capability() -> None:
    decision = infer_capability_from_query("What is the weather in Austin?")
    assert decision.capability == "unknown"


def test_infer_referral_triage_capability() -> None:
    decision = infer_capability_from_query("Need urgent triage and priority assignment for stroke symptoms")
    assert decision.capability == "referral_triage"


def test_infer_insurance_validation_capability() -> None:
    decision = infer_capability_from_query("Check payer eligibility and in-network coverage")
    assert decision.capability == "insurance_validation"


def test_heuristic_slot_extraction() -> None:
    slots = heuristic_slot_extraction(
        "Recommend specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna"
    )
    assert slots["diagnosis"] == "chest pain"
    assert slots["location"] == "Austin"
    assert slots["insurance_plan"] == "Aetna"


def test_infer_query_llm_success(monkeypatch) -> None:
    def _mock_llm_json(*args, **kwargs):
        return {
            "capability": "specialist_recommendation",
            "confidence": 0.92,
            "reason": "Referral recommendation request detected",
            "diagnosis": "chest pain",
            "location": "Austin, TX",
            "insurance_plan": "Aetna",
        }

    monkeypatch.setattr("app.agents.capability_router.call_llm_json", _mock_llm_json)
    interpretation = infer_query(
        "Recommend specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna"
    )
    assert interpretation.decision.capability == "specialist_recommendation"
    assert interpretation.source == "llm"


def test_infer_query_llm_required(monkeypatch) -> None:
    def _raise_llm_error(*args, **kwargs):
        raise LLMGatewayError("gateway down")

    monkeypatch.setattr("app.agents.capability_router.call_llm_json", _raise_llm_error)

    try:
        infer_query("Recommend specialist")
        assert False, "Expected LLMGatewayError"
    except LLMGatewayError:
        assert True
