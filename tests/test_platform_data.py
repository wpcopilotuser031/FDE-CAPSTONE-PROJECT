from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_platform_data_endpoint_returns_dashboard_payload() -> None:
    response = client.get("/api/v1/platform-data")
    assert response.status_code == 200

    body = response.json()
    assert "patients" in body
    assert "referrals" in body
    assert "eligibility" in body
    assert "appointments" in body
    assert "notifications" in body
    assert "documents" in body
    assert "care_team" in body
    assert "ai_opportunities" in body
    assert len(body["patients"]) > 0
    assert len(body["referrals"]) > 0
