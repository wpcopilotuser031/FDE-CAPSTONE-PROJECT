from app.mcp_server.tools import (
    build_recommendation_rationale_llm_assisted,
    check_provider_in_network,
    create_triage_ticket,
    infer_specialties_llm_assisted,
    list_provider_insurance_plans,
    map_diagnosis_to_specialties,
    patient_insurance_profile,
    retrieve_candidate_providers,
    triage_assess,
)
from app.agents.llm_gateway import LLMGatewayError
from app.data_loader import load_json
from app.config import DATA_DIR


def test_map_diagnosis_to_specialties_exact() -> None:
    specialties = map_diagnosis_to_specialties("chest pain")
    assert "Cardiology" in specialties


def test_map_diagnosis_to_specialties_fuzzy() -> None:
    specialties = map_diagnosis_to_specialties("severe migraine with aura")
    assert "Neurology" in specialties


def test_check_provider_in_network() -> None:
    networks = load_json(DATA_DIR / "insurance_networks.json")
    aetna_members = networks.get("Aetna", [])
    assert len(aetna_members) > 0

    in_network_id = aetna_members[0]
    assert check_provider_in_network(in_network_id, "Aetna") is True

    # Choose an ID that does not exist to assert false path deterministically.
    assert check_provider_in_network("P999999", "Aetna") is False


def test_retrieve_candidate_providers() -> None:
    results = retrieve_candidate_providers("chest pain", "Austin, TX", max_candidates=5)
    assert len(results) > 0
    assert "provider_id" in results[0]


def test_list_provider_insurance_plans() -> None:
    plans = list_provider_insurance_plans("P1001")
    assert "Aetna" in plans


def test_patient_insurance_profile_lookup_by_patient_id() -> None:
    profile = patient_insurance_profile(patient_id="PT-001")
    assert profile["patient_id"] == "PT-001"
    assert profile["insurance_plan"] == "Aetna"


def test_patient_insurance_profile_lookup_by_patient_name_alias() -> None:
    profile = patient_insurance_profile(patient_name="Aviroop Basu")
    assert profile["patient_id"] == "PT-001"
    assert profile["insurance_plan"] == "Aetna"


def test_triage_assess_returns_priority_and_specialties() -> None:
    assessment = triage_assess("chest pain")
    assert assessment["triage_priority"] == "high"
    assert assessment["priority_score"] > 0.8
    assert "Cardiology" in assessment["recommended_specialties"]


def test_create_triage_ticket_generates_ticket_id() -> None:
    ticket = create_triage_ticket(
        reason="Need manual review",
        triage_priority="high",
        patient_id="PT-001",
    )
    assert ticket["ticket_id"].startswith("TCK-")
    assert ticket["status"] == "OPEN"


def test_infer_specialties_llm_assisted(monkeypatch) -> None:
    def _mock_llm_json(*args, **kwargs):
        return {"specialties": ["Neurology"]}

    monkeypatch.setattr("app.mcp_server.tools.call_llm_json", _mock_llm_json)
    specialties, source = infer_specialties_llm_assisted("severe migraine with aura")
    assert "Neurology" in specialties
    assert source == "llm"


def test_infer_specialties_llm_assisted_case_insensitive(monkeypatch) -> None:
    def _mock_llm_json(*args, **kwargs):
        return {"specialties": ["neurology"]}

    monkeypatch.setattr("app.mcp_server.tools.call_llm_json", _mock_llm_json)
    specialties, source = infer_specialties_llm_assisted("severe migraine with aura")
    assert specialties == ["Neurology"]
    assert source == "llm"


def test_rationale_llm_assisted(monkeypatch) -> None:
    def _mock_llm_json(*args, **kwargs):
        return {"rationale": "Cardiology match, in-network, and earliest nearby slot."}

    monkeypatch.setattr("app.mcp_server.tools.call_llm_json", _mock_llm_json)
    providers = load_json(DATA_DIR / "providers.json")
    provider = providers[0]
    rationale, source = build_recommendation_rationale_llm_assisted(provider, ["Cardiology"], "Aetna")
    assert rationale
    assert source == "llm"


def test_infer_specialties_llm_required(monkeypatch) -> None:
    def _raise_llm_error(*args, **kwargs):
        raise LLMGatewayError("gateway down")

    monkeypatch.setattr("app.mcp_server.tools.call_llm_json", _raise_llm_error)

    try:
        infer_specialties_llm_assisted("migraine")
        assert False, "Expected LLMGatewayError"
    except LLMGatewayError:
        assert True
