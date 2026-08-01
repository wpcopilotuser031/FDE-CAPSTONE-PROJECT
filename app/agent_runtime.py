from typing import Any

from fastapi import FastAPI, HTTPException

from app.agents.use_case_agents import (
    alternative_provider_agent,
    insurance_validation_agent,
    provider_discovery_agent,
    referral_triage_agent,
    specialist_recommendation_agent,
)

app = FastAPI(
    title="Referral Agent Runtime",
    version="0.1.0",
    description="Dedicated runtime for use-case agent invocation over HTTP.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


_AGENT_ENDPOINT_HANDLERS = {
    "specialist_recommendation": specialist_recommendation_agent,
    "referral_triage": referral_triage_agent,
    "provider_discovery": provider_discovery_agent,
    "insurance_validation": insurance_validation_agent,
    "alternative_provider_suggestion": alternative_provider_agent,
}


@app.post("/api/v1/agents/{capability}/invoke")
def invoke_agent(capability: str, payload: dict[str, Any]) -> dict[str, Any]:
    normalized = capability.strip().lower()
    handler = _AGENT_ENDPOINT_HANDLERS.get(normalized)
    if not handler:
        raise HTTPException(status_code=404, detail=f"Unknown capability '{capability}'.")
    return handler(payload)
