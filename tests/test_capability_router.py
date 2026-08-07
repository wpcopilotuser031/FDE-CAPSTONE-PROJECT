from app.agents.capability_router import (
    CapabilityDecision,
    QueryInterpretation,
    heuristic_slot_extraction,
    infer_capability_from_query,
    infer_query,
)
from app.agents.capability_entrypoint import route_capability
from app.agents.llm_gateway import LLMGatewayError


def test_infer_specialist_recommendation_capability() -> None:
    query = "Recommend specialist for diagnosis chest pain with Aetna insurance"
    decision = infer_capability_from_query(query)
    assert decision.capability == "specialist_recommendation"
    assert decision.confidence >= 0.5


def test_infer_specialist_recommendation_for_symptom_doctor_search() -> None:
    query = "Am having chest pain, find doctors in dallas in 30 days under aetna plan"
    decision = infer_capability_from_query(query)
    assert decision.capability == "specialist_recommendation"
    assert decision.confidence >= 0.6


def test_infer_unknown_capability() -> None:
    decision = infer_capability_from_query("What is the weather in Austin?")
    assert decision.capability == "unknown"


def test_infer_referral_triage_capability() -> None:
    decision = infer_capability_from_query("Need urgent triage and priority assignment for stroke symptoms")
    assert decision.capability == "referral_triage"


def test_infer_insurance_validation_capability() -> None:
    decision = infer_capability_from_query("Check payer eligibility and in-network coverage")
    assert decision.capability == "insurance_validation"


def test_infer_alternative_provider_capability() -> None:
    decision = infer_capability_from_query(
        "Find alternative providers for chest pain in Austin, TX, excluding provider PROV-001"
    )
    assert decision.capability == "alternative_provider_suggestion"
    assert decision.confidence >= 0.5


def test_heuristic_slot_extraction() -> None:
    slots = heuristic_slot_extraction(
        "Recommend specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna"
    )
    assert slots["diagnosis"] == "chest pain"
    assert slots["location"] == "Austin"
    assert slots["insurance_plan"] == "Aetna"


def test_heuristic_slot_extraction_alternative_provider() -> None:
    slots = heuristic_slot_extraction(
        "Find alternative providers for diagnosis: chest pain, location: Austin, TX, insurance: Aetna, excluding provider PROV-001, within 7 days, urgency: Routine"
    )
    assert slots["diagnosis"] == "chest pain"
    assert slots["location"] == "Austin"
    assert slots["insurance_plan"] == "Aetna"
    assert slots["excluded_provider_id"] == "PROV-001"
    assert slots["preferred_window_days"] == "7"
    assert slots["urgency"] == "Routine"


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


def test_conversational_route_missing_fields_is_contract_driven(monkeypatch) -> None:
    def _mock_infer_query(query, context=None):
        return QueryInterpretation(
            decision=CapabilityDecision(
                capability="specialist_recommendation",
                confidence=0.93,
                reason="test",
            ),
            slots={
                "diagnosis": "chest pain",
                "location": "Dallas",
                "insurance_plan": None,
                "excluded_provider_id": None,
                "preferred_window_days": "7",
                "urgency": None,
            },
            source="llm",
        )

    monkeypatch.setattr("app.agents.capability_entrypoint.infer_query", _mock_infer_query)

    result = route_capability(
        {
            "capability": "conversational_assistant",
            "payload": {"question": "Find me a specialist"},
        },
        caller_role="care_agent",
        session_token="test-session-missing-fields",
    )

    assert result["agent_transport"] == "none"
    answer = result["agent_result"]["answer"].lower()
    assert "insurance plan" in answer
    assert "date of birth" not in answer
    assert "member id" not in answer


def test_conversational_route_reuses_prior_slots(monkeypatch) -> None:
    state = {"count": 0}

    def _mock_infer_query(query, context=None):
        state["count"] += 1
        if state["count"] == 1:
            return QueryInterpretation(
                decision=CapabilityDecision(
                    capability="specialist_recommendation",
                    confidence=0.9,
                    reason="test turn 1",
                ),
                slots={
                    "diagnosis": "heart pain",
                    "location": None,
                    "insurance_plan": None,
                    "excluded_provider_id": None,
                    "preferred_window_days": None,
                    "urgency": None,
                },
                source="llm",
            )
        return QueryInterpretation(
            decision=CapabilityDecision(
                capability="specialist_recommendation",
                confidence=0.9,
                reason="test turn 2",
            ),
            slots={
                "diagnosis": None,
                "location": "Dallas",
                "insurance_plan": "Aetna",
                "excluded_provider_id": None,
                "preferred_window_days": "7",
                "urgency": "Priority",
            },
            source="llm",
        )

    def _mock_http_invoke(capability, payload):
        if capability == "specialist_recommendation":
            assert payload["diagnosis"] == "heart pain"
            assert payload["location"] == "Dallas"
            assert payload["insurance_plan"] == "Aetna"
            return {
                "request_id": "REQ-CTX",
                "generated_at": "2026-01-01T00:00:00+00:00",
                "inferred_specialties": ["Cardiology"],
                "recommendations": [],
                "missing_information": [],
                "llm_used": True,
                "decision_trace": {
                    "capability": "specialist_recommendation",
                    "caller_role": "specialist_recommendation",
                    "mcp_enabled": True,
                    "tools_invoked": ["diagnosis_to_specialty"],
                    "human_review_required": False,
                },
            }
        return {
            "answer": "OK",
            "follow_up_suggestions": [],
            "llm_used": False,
            "decision_trace": {
                "capability": "conversational_assistant",
                "caller_role": "conversational_assistant",
                "mcp_enabled": False,
                "tools_invoked": [],
                "human_review_required": False,
            },
        }

    monkeypatch.setattr("app.agents.capability_entrypoint.infer_query", _mock_infer_query)
    monkeypatch.setattr("app.agents.capability_entrypoint._invoke_agent_http", _mock_http_invoke)

    session_token = "test-session-slot-reuse"
    first = route_capability(
        {
            "capability": "conversational_assistant",
            "payload": {"question": "Find me a specialist for heart pain"},
        },
        caller_role="care_agent",
        session_token=session_token,
    )
    assert first["agent_transport"] == "none"
    assert "location" in first["agent_result"]["answer"].lower()

    second = route_capability(
        {
            "capability": "conversational_assistant",
            "payload": {"question": "Dallas with Aetna"},
        },
        caller_role="care_agent",
        session_token=session_token,
    )
    assert second["selected_capability"] == "conversational_assistant"
    assert second.get("routed_capability") == "specialist_recommendation"


def test_insurance_capability_denied_for_patient() -> None:
    try:
        route_capability(
            {
                "capability": "insurance_validation",
                "payload": {"patient_id": "PT-001"},
            },
            caller_role="patient",
            session_token="role-test-patient",
        )
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not permitted" in str(exc)


def test_insurance_capability_denied_for_provider() -> None:
    try:
        route_capability(
            {
                "capability": "insurance_validation",
                "payload": {"patient_id": "PT-001"},
            },
            caller_role="provider",
            session_token="role-test-provider",
        )
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not permitted" in str(exc)


def test_referral_triage_capability_denied_for_provider() -> None:
    try:
        route_capability(
            {
                "capability": "referral_triage",
                "payload": {"diagnosis": "chest pain"},
            },
            caller_role="provider",
            session_token="role-test-provider-triage",
        )
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not permitted" in str(exc)


def test_referral_triage_capability_denied_for_patient() -> None:
    try:
        route_capability(
            {
                "capability": "referral_triage",
                "payload": {"diagnosis": "chest pain"},
            },
            caller_role="patient",
            session_token="role-test-patient-triage",
        )
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not permitted" in str(exc)


def test_conversational_insurance_route_for_care_agent_passes_user_role(monkeypatch) -> None:
    def _mock_infer_query(query, context=None):
        return QueryInterpretation(
            decision=CapabilityDecision(
                capability="insurance_validation",
                confidence=0.92,
                reason="insurance question",
            ),
            slots={},
            source="llm",
        )

    def _mock_http_invoke(capability, payload):
        if capability == "insurance_validation":
            assert payload.get("user_role") == "care_agent"
            assert "PT-001" in str(payload.get("question", ""))
            return {
                "mode": "patient_insurance_profile",
                "patient_id": "PT-001",
                "insurance_plan": "Aetna",
                "eligible": True,
                "missing_information": [],
                "decision_trace": {
                    "capability": "insurance_validation",
                    "caller_role": "insurance_validation",
                    "mcp_enabled": True,
                    "tools_invoked": ["patient_insurance_profile"],
                    "human_review_required": False,
                },
            }
        return {
            "answer": "ok",
            "follow_up_suggestions": [],
            "llm_used": False,
            "decision_trace": {
                "capability": "conversational_assistant",
                "caller_role": "conversational_assistant",
                "mcp_enabled": False,
                "tools_invoked": [],
                "human_review_required": False,
            },
        }

    monkeypatch.setattr("app.agents.capability_entrypoint.infer_query", _mock_infer_query)
    monkeypatch.setattr("app.agents.capability_entrypoint._invoke_agent_http", _mock_http_invoke)

    result = route_capability(
        {
            "capability": "conversational_assistant",
            "payload": {"question": "PT-001 is registered under which insurance plan?"},
        },
        caller_role="care_agent",
        session_token="care-agent-insurance-route",
    )
    assert result.get("routed_capability") == "insurance_validation"


def test_conversational_provider_cannot_bypass_rbac_on_misroute(monkeypatch) -> None:
    def _mock_infer_query(query, context=None):
        return QueryInterpretation(
            decision=CapabilityDecision(
                capability="provider_discovery",
                confidence=0.95,
                reason="llm misroute",
            ),
            slots={
                "diagnosis": "chest pain",
                "location": "Dallas",
                "insurance_plan": "BlueCross",
                "excluded_provider_id": None,
                "preferred_window_days": "2",
                "urgency": None,
            },
            source="llm",
        )

    monkeypatch.setattr("app.agents.capability_entrypoint.infer_query", _mock_infer_query)
    monkeypatch.setattr(
        "app.agents.capability_entrypoint.infer_capability_from_query",
        lambda _query: CapabilityDecision(
            capability="specialist_recommendation",
            confidence=0.82,
            reason="heuristic diagnosis-based recommendation",
        ),
    )

    result = route_capability(
        {
            "capability": "conversational_assistant",
            "payload": {"question": "I am having chest pain, need providers near Dallas in next 2 days under BlueCross"},
        },
        caller_role="provider",
        session_token="provider-misroute-rbac",
    )

    assert result["agent_transport"] == "none"
    assert "not authorized" in result["agent_result"]["answer"].lower()


def test_infer_referral_history_capability() -> None:
    decision = infer_capability_from_query("Show referral history for PT-001 and prior referrals")
    assert decision.capability == "referral_history"
    assert decision.confidence >= 0.5


def test_provider_can_use_referral_history_capability(monkeypatch) -> None:
    def _mock_invoke_agent(capability, payload):
        assert capability == "referral_history"
        assert payload["patient_id"] == "PT-001"
        return {
            "history_summary": "Referral history for PT-001.",
            "decision_trace": {
                "capability": "referral_history",
                "caller_role": "referral_history",
                "mcp_enabled": True,
                "tools_invoked": ["retrieve_referral_history"],
                "human_review_required": False,
            },
        }

    monkeypatch.setattr("app.agents.capability_entrypoint._invoke_agent_http", _mock_invoke_agent)

    result = route_capability(
        {
            "capability": "referral_history",
            "payload": {"patient_id": "PT-001"},
        },
        caller_role="provider",
        session_token="role-test-provider-referral-history",
    )

    assert result["selected_capability"] == "referral_history"
    assert result["selected_agent_card"]["rbac_role"] == "referral_history"
    assert result["agent_result"]["history_summary"] == "Referral history for PT-001."


def test_patient_cannot_use_referral_history_capability() -> None:
    try:
        route_capability(
            {
                "capability": "referral_history",
                "payload": {"patient_id": "PT-001"},
            },
            caller_role="patient",
            session_token="role-test-patient-referral-history",
        )
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not permitted" in str(exc)


def test_infer_referral_history_capability() -> None:
    decision = infer_capability_from_query(
        "Show me referral history for patient PT-001"
    )
    assert decision.capability == "referral_history"


def test_provider_can_use_referral_history() -> None:
    result = route_capability(
        {
            "capability": "referral_history",
            "payload": {"patient_id": "PT-001"},
        },
        caller_role="provider",
        session_token="role-test-provider-referral-history",
    )
    assert result["selected_capability"] == "referral_history"
    assert result["selected_agent_card"]["rbac_role"] == "referral_history"


def test_patient_cannot_use_referral_history() -> None:
    try:
        route_capability(
            {
                "capability": "referral_history",
                "payload": {"patient_id": "PT-001"},
            },
            caller_role="patient",
            session_token="role-test-patient-referral-history",
        )
        assert False, "Expected PermissionError"
    except PermissionError as exc:
        assert "not permitted" in str(exc)
