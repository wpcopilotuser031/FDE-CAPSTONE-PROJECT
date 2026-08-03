from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.capability_entrypoint import handle_jsonrpc_request
from app.agents.llm_gateway import LLMGatewayError
from app.auth import authenticate, end_session, get_session
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
    # Also allow the UI when it's reached via a VM/host IP or DNS name rather than
    # localhost (e.g., the dockerized nginx UI on port 8093 or 8080 accessed remotely).
    allow_origin_regex=r"https?://[^/]+:(8080|8093)$",
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


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    role: str
    display_name: str
    scope: str | None = None


@app.post("/api/v1/auth/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    session = authenticate(request.username, request.password)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return LoginResponse(
        token=session.token,
        role=session.role,
        display_name=session.display_name,
        scope=session.scope,
    )


@app.post("/api/v1/auth/logout")
def logout(x_session_token: str | None = Header(default=None, alias="X-Session-Token")) -> dict[str, bool]:
    end_session(x_session_token)
    return {"ok": True}


@app.get("/api/v1/auth/me", response_model=LoginResponse)
def whoami(x_session_token: str | None = Header(default=None, alias="X-Session-Token")) -> LoginResponse:
    session = get_session(x_session_token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session.")
    return LoginResponse(
        token=session.token,
        role=session.role,
        display_name=session.display_name,
        scope=session.scope,
    )


@app.get("/api/v1/platform-data")
def platform_data() -> dict[str, Any]:
    return _build_platform_data()


@app.post("/api/v1/recommend-specialists", response_model=RecommendationResponse)
def recommend_specialists(
    request: RecommendationRequest,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> RecommendationResponse:
    session = get_session(x_session_token)
    user_role = session.role if session else None

    try:
        result = run_specialist_recommendation_flow(
            diagnosis=request.diagnosis,
            location=request.location,
            insurance_plan=request.insurance_plan,
            max_results=request.max_results,
            urgency=request.urgency,
            preferred_window_days=request.preferred_window_days,
            user_role=user_role,
        )
    except LLMGatewayError as exc:
        raise HTTPException(status_code=503, detail=f"LLM dependency unavailable: {exc}") from exc
    except MCPClientError as exc:
        raise HTTPException(status_code=503, detail=f"MCP dependency unavailable: {exc}") from exc
    return RecommendationResponse(**result)


@app.post("/api/v1/capability-router")
def capability_router(
    request: JsonRpcRequest,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> dict:
    session = get_session(x_session_token)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")
    return handle_jsonrpc_request(request.model_dump(), caller_role=session.role)
