from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agents.capability_entrypoint import handle_jsonrpc_request
from app.agents.llm_gateway import LLMGatewayError
from app.mcp_clients.specialist_recommendation_client import MCPClientError
from app.agents.specialist_recommendation_graph import run_specialist_recommendation_flow
from app.config import DATA_DIR
from app.data_loader import load_json
from app.rag.provider_index import ProviderIndex
from app.schemas.jsonrpc import JsonRpcRequest
from app.schemas.specialist_recommendation import RecommendationRequest, RecommendationResponse

UI_PATH = Path(__file__).resolve().parent.parent / "ui"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Build local Chroma index from static provider data.
    ProviderIndex().rebuild()
    yield


app = FastAPI(
    title="Intelligent Care Coordination & Referral Management Platform",
    version="0.1.0",
    description="AI-assisted referral management with MCP-enabled provider, payer, and scheduling workflows.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080", "http://127.0.0.1:8093", "http://localhost:8093"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=UI_PATH), name="static")


def _build_platform_data() -> dict[str, Any]:
    patients = load_json(DATA_DIR / "patients.json")
    referrals = load_json(DATA_DIR / "referrals.json")
    eligibility = load_json(DATA_DIR / "eligibility.json")
    appointments = load_json(DATA_DIR / "appointments.json")
    notifications = load_json(DATA_DIR / "notifications.json")
    documents = load_json(DATA_DIR / "documents.json")
    care_team = load_json(DATA_DIR / "care_team.json")
    providers = load_json(DATA_DIR / "providers.json")
    diagnosis_specialties = load_json(DATA_DIR / "diagnosis_specialties.json")
    insurance_networks = load_json(DATA_DIR / "insurance_networks.json")

    data_sources = []
    for path in sorted(DATA_DIR.glob("*.json")):
        payload = load_json(path)
        data_sources.append(
            {
                "filename": path.name,
                "records": len(payload) if isinstance(payload, list) else 1,
            }
        )

    return {
        "patients": patients,
        "referrals": referrals,
        "eligibility": eligibility,
        "appointments": appointments,
        "notifications": notifications,
        "documents": documents,
        "care_team": care_team,
        "providers": providers,
        "diagnosis_specialties": diagnosis_specialties,
        "insurance_networks": insurance_networks,
        "data_sources": data_sources,
        "platform_summary": {
            "active_patients": len(patients),
            "open_referrals": len(referrals),
            "eligible_cases": sum(1 for item in eligibility if item.get("eligible")),
            "pending_documents": sum(1 for item in referrals if item.get("documents_missing")),
            "appointments_booked": len([item for item in appointments if item.get("status") == "Confirmed"]),
        },
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def frontend() -> dict[str, str]:
    return {"message": "Visit /static/index.html to open the Referral Command Center frontend."}


@app.get("/api/v1/platform-data")
def platform_data() -> dict[str, Any]:
    return _build_platform_data()


@app.post("/api/v1/recommend-specialists", response_model=RecommendationResponse)
def recommend_specialists(request: RecommendationRequest) -> RecommendationResponse:
    try:
        result = run_specialist_recommendation_flow(
            diagnosis=request.diagnosis,
            location=request.location,
            insurance_plan=request.insurance_plan,
            max_results=request.max_results,
            urgency=request.urgency,
            preferred_window_days=request.preferred_window_days,
        )
    except LLMGatewayError as exc:
        raise HTTPException(status_code=503, detail=f"LLM dependency unavailable: {exc}") from exc
    except MCPClientError as exc:
        raise HTTPException(status_code=503, detail=f"MCP dependency unavailable: {exc}") from exc
    return RecommendationResponse(**result)


@app.post("/api/v1/capability-router")
def capability_router(request: JsonRpcRequest) -> dict:
    return handle_jsonrpc_request(request.model_dump())
