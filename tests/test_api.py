from fastapi.testclient import TestClient

from app.agents.llm_gateway import LLMGatewayError
from app.agent_runtime import app as agent_runtime_app
from app.mcp_gateway import app as mcp_gateway_app
from app.mcp_clients.specialist_recommendation_client import MCPClientError
from app.main import app

client = TestClient(app)
agent_runtime_client = TestClient(agent_runtime_app)
mcp_gateway_client = TestClient(mcp_gateway_app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_recommend_specialists(monkeypatch) -> None:
    monkeypatch.setenv("USE_MCP_TOOLS", "false")
    monkeypatch.setattr(
        "app.agents.specialist_recommendation_graph.infer_specialties_llm_assisted",
        lambda diagnosis: (["Cardiology"], "llm"),
    )
    monkeypatch.setattr(
        "app.agents.specialist_recommendation_graph.build_recommendation_rationale_llm_assisted",
        lambda provider, specialties, insurance, mcp_client=None, accepts_insurance=None: ("LLM rationale", "llm"),
    )

    payload = {
        "patient_id": "PT-001",
        "diagnosis": "chest pain",
        "location": "Austin, TX",
        "insurance_plan": "Aetna",
        "max_results": 3,
    }

    response = client.post("/api/v1/recommend-specialists", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert body["request_id"]
    assert "Cardiology" in body["inferred_specialties"]
    assert len(body["recommendations"]) > 0
    assert body["recommendations"][0]["provider_id"]
    assert body["llm_used"] is True


def test_recommend_specialists_returns_503_on_llm_failure(monkeypatch) -> None:
    monkeypatch.setenv("USE_MCP_TOOLS", "false")
    def _raise_llm_error(*args, **kwargs):
        raise LLMGatewayError("LLM did not return supported specialties.")

    monkeypatch.setattr("app.agents.specialist_recommendation_graph.infer_specialties_llm_assisted", _raise_llm_error)

    payload = {
        "patient_id": "PT-001",
        "diagnosis": "chest pain",
        "location": "Austin, TX",
        "insurance_plan": "Aetna",
        "max_results": 3,
    }

    response = client.post("/api/v1/recommend-specialists", json=payload)
    assert response.status_code == 503
    assert "LLM dependency unavailable" in response.json()["detail"]


def test_recommend_specialists_returns_503_on_mcp_failure(monkeypatch) -> None:
    monkeypatch.setenv("USE_MCP_TOOLS", "true")
    def _raise_mcp_error(self):
        raise MCPClientError("MCP server unavailable")

    monkeypatch.setattr("app.mcp_clients.specialist_recommendation_client.SpecialistRecommendationMCPClient.__enter__", _raise_mcp_error)

    payload = {
        "patient_id": "PT-001",
        "diagnosis": "chest pain",
        "location": "Austin, TX",
        "insurance_plan": "Aetna",
        "max_results": 3,
    }

    response = client.post("/api/v1/recommend-specialists", json=payload)
    assert response.status_code == 503
    assert "MCP dependency unavailable" in response.json()["detail"]


def test_jsonrpc_agents_cards_endpoint() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "cards-1",
        "method": "agents.cards",
        "params": {},
    }

    response = client.post("/api/v1/capability-router", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "cards-1"
    assert "result" in body
    assert len(body["result"]["agent_cards"]) >= 1


def test_jsonrpc_route_to_specialist_agent(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CALL_TRANSPORT", "http")

    def _mock_http_invoke(capability, payload):
        assert capability == "specialist_recommendation"
        return {
            "request_id": "REQ-1",
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

    monkeypatch.setattr("app.agents.capability_entrypoint._invoke_agent_http", _mock_http_invoke)

    payload = {
        "jsonrpc": "2.0",
        "id": "route-1",
        "method": "capability.route",
        "params": {
            "capability": "specialist_recommendation",
            "payload": {
                "diagnosis": "chest pain",
                "location": "Austin, TX",
                "insurance_plan": "Aetna",
                "max_results": 3,
            },
        },
    }

    response = client.post("/api/v1/capability-router", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["selected_capability"] == "specialist_recommendation"
    assert body["result"]["selected_agent_card"]["rbac_role"] == "specialist_recommendation"
    assert body["result"]["agent_result"]["request_id"] == "REQ-1"


def test_http_agent_invoke_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("USE_MCP_TOOLS", "false")
    monkeypatch.setattr(
        "app.agents.provider_discovery_agent.retrieve_candidate_providers",
        lambda diagnosis, location, max_candidates=5: [{"provider_id": "P-1", "provider_name": "Dr. Demo"}],
    )

    payload = {
        "diagnosis": "chest pain",
        "location": "Austin, TX",
        "max_results": 1,
    }

    response = agent_runtime_client.post("/api/v1/agents/provider_discovery/invoke", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "providers" in body
    assert len(body["providers"]) == 1


def test_provider_discovery_with_specialty_and_filters(monkeypatch) -> None:
    monkeypatch.setenv("USE_MCP_TOOLS", "false")

    providers_fixture = [
        {
            "provider_id": "P-100",
            "provider_name": "Dr. Cardio One",
            "specialty": "Cardiology",
            "location": "Dallas, TX",
            "insurance_networks": ["Aetna", "Cigna"],
            "next_available_date": "2026-08-07",
        },
        {
            "provider_id": "P-101",
            "provider_name": "Dr. GI Two",
            "specialty": "Gastroenterology",
            "location": "Dallas, TX",
            "insurance_networks": ["Aetna"],
            "next_available_date": "2026-08-06",
        },
        {
            "provider_id": "P-102",
            "provider_name": "Dr. Cardio Three",
            "specialty": "Cardiology",
            "location": "Dallas, TX",
            "insurance_networks": ["BlueCross"],
            "next_available_date": "2026-08-05",
        },
        {
            "provider_id": "P-103",
            "provider_name": "Dr. GI Four",
            "specialty": "Gastroenterology",
            "location": "Austin, TX",
            "insurance_networks": ["Aetna"],
            "next_available_date": "2026-08-05",
        },
    ]

    monkeypatch.setattr(
        "app.agents.provider_discovery_agent.load_json",
        lambda _path: providers_fixture,
    )

    payload = {
        "specialty": "Cardiology or Gastroenterology",
        "location": "Dallas",
        "insurance_plan": "Aetna",
        "preferred_window_days": 7,
        "max_results": 5,
    }

    response = agent_runtime_client.post("/api/v1/agents/provider_discovery/invoke", json=payload)
    assert response.status_code == 200

    body = response.json()
    assert [item["provider_id"] for item in body["providers"]] == ["P-101", "P-100"]


def test_http_mcp_call_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("MCP_INTERNAL_KEY", "test-key")

    payload = {
        "tool_name": "diagnosis_to_specialty",
        "arguments": {
            "diagnosis": "chest pain",
            "caller_role": "specialist_recommendation",
            "internal_key": "test-key",
        },
    }

    response = mcp_gateway_client.post("/api/v1/mcp/call", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "result" in body
    assert isinstance(body["result"], list)
    assert "Cardiology" in body["result"]


def test_insurance_validation_patient_plan_lookup_by_patient_id(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agents.insurance_validation_agent.run_insurance_validation_flow",
        lambda **kwargs: {
            "mode": "patient_insurance_profile",
            "patient_id": "PT-001",
            "patient_name": "Aisha Patel",
            "insurance_plan": "Aetna",
            "eligible": True,
            "eligibility_records": [],
            "missing_information": [],
            "decision_trace": {
                "capability": "insurance_validation",
                "caller_role": "insurance_validation",
                "mcp_enabled": True,
                "tools_invoked": ["patient_insurance_profile"],
                "human_review_required": False,
            },
        },
    )

    payload = {
        "patient_id": "PT-001",
    }

    response = agent_runtime_client.post("/api/v1/agents/insurance_validation/invoke", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["patient_id"] == "PT-001"
    assert body["insurance_plan"] == "Aetna"


def test_insurance_validation_patient_plan_lookup_by_patient_name(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.agents.insurance_validation_agent.run_insurance_validation_flow",
        lambda **kwargs: {
            "mode": "patient_insurance_profile",
            "patient_id": "PT-001",
            "patient_name": "Aisha Patel",
            "insurance_plan": "Aetna",
            "eligible": True,
            "eligibility_records": [],
            "missing_information": [],
            "decision_trace": {
                "capability": "insurance_validation",
                "caller_role": "insurance_validation",
                "mcp_enabled": True,
                "tools_invoked": ["patient_insurance_profile"],
                "human_review_required": False,
            },
        },
    )

    payload = {
        "patient_name": "Aviroop Basu",
    }

    response = agent_runtime_client.post("/api/v1/agents/insurance_validation/invoke", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["patient_id"] == "PT-001"
    assert body["insurance_plan"] == "Aetna"


def test_insurance_validation_extracts_patient_id_from_question(monkeypatch) -> None:
    captured: dict[str, str] = {}

    def _mock_flow(**kwargs):
        captured.update(kwargs)
        return {
            "mode": "patient_insurance_profile",
            "patient_id": kwargs.get("patient_id"),
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

    monkeypatch.setattr("app.agents.insurance_validation_agent.run_insurance_validation_flow", _mock_flow)

    payload = {
        "question": "PT-001 is registered under which insurance plan?",
        "user_role": "care_agent",
    }

    response = agent_runtime_client.post("/api/v1/agents/insurance_validation/invoke", json=payload)
    assert response.status_code == 200
    assert captured.get("patient_id") == "PT-001"


def test_jsonrpc_invalid_version_returns_error() -> None:
    payload = {
        "jsonrpc": "1.0",
        "id": "bad-1",
        "method": "agents.cards",
        "params": {},
    }

    response = client.post("/api/v1/capability-router", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == -32600


def test_jsonrpc_route_fails_when_non_http_transport_requested(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_CALL_TRANSPORT", "inproc")

    payload = {
        "jsonrpc": "2.0",
        "id": "route-bad-transport",
        "method": "capability.route",
        "params": {
            "capability": "specialist_recommendation",
            "payload": {
                "diagnosis": "chest pain",
                "location": "Austin, TX",
                "insurance_plan": "Aetna",
                "max_results": 3,
            },
        },
    }

    response = client.post("/api/v1/capability-router", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == -32000
