from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agents.capability_entrypoint import handle_jsonrpc_request
from app.agents.llm_gateway import LLMGatewayError
from app.mcp_clients.specialist_recommendation_client import MCPClientError
from app.agents.specialist_recommendation_graph import run_specialist_recommendation_flow
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
    description="Phase 1: Specialist recommendation by diagnosis, location, and insurance network.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8093", "http://localhost:8093"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=UI_PATH), name="static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def frontend() -> dict[str, str]:
    return {"message": "Visit /static/index.html to open the Referral Command Center frontend."}


@app.post("/api/v1/recommend-specialists", response_model=RecommendationResponse)
def recommend_specialists(request: RecommendationRequest) -> RecommendationResponse:
    try:
        result = run_specialist_recommendation_flow(
            diagnosis=request.diagnosis,
            location=request.location,
            insurance_plan=request.insurance_plan,
            max_results=request.max_results,
        )
    except LLMGatewayError as exc:
        raise HTTPException(status_code=503, detail=f"LLM dependency unavailable: {exc}") from exc
    except MCPClientError as exc:
        raise HTTPException(status_code=503, detail=f"MCP dependency unavailable: {exc}") from exc
    return RecommendationResponse(**result)


@app.post("/api/v1/capability-router")
def capability_router(request: JsonRpcRequest) -> dict:
    return handle_jsonrpc_request(request.model_dump())
