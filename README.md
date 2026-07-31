# Intelligent Care Coordination & Referral Management Platform

Phase 1 implementation of the capstone use case.

Implemented AI capability:
- Recommend specialists based on diagnosis, location, and insurance network.

LLM assistance in workflow:
- LangGraph uses strict LLM-based specialty inference (no heuristic answer fallback).
- Recommendation rationale is strict LLM-generated (no heuristic answer fallback).

MCP integration in runtime flow:
- LangGraph now executes provider retrieval and insurance eligibility through MCP protocol calls.
- MCP tools are invoked using a per-request stdio MCP client session.
- USE_MCP_TOOLS=true (default) enables true MCP path; set to false to use direct local functions for debugging.

Technology stack:
- FastAPI for service APIs
- LangGraph for multi-step agent workflow
- ChromaDB for RAG-style provider retrieval over static JSON data
- MCP Server (Python MCP SDK) for tool exposure and future agent integrations
- Streamlit for guided and chat-style referral UI

## Project Structure

- app/main.py: FastAPI service entrypoint
- streamlit_app.py: Streamlit UI (guided form + capability-inferred chat)
- app/agents/specialist_recommendation_graph.py: LangGraph workflow for specialist recommendation
- app/agents/referral_graph.py: Backward-compatible import shim
- app/agents/capability_router.py: Intent-to-capability routing for chat queries
- app/mcp_server/tools.py: Shared tool implementations used by MCP server and use-case graphs
- app/agents/tools.py: Backward-compatible import shim
- app/mcp_clients/specialist_recommendation_client.py: MCP client for specialist recommendation use case
- app/mcp_server/server.py: Shared MCP tool server
- app/rag/provider_index.py: ChromaDB persistent index and querying
- data/providers.json: Provider directory (mocked external source)
- data/diagnosis_specialties.json: Diagnosis to specialty mapping
- data/insurance_networks.json: Payer-provider network mapping
- tests/: Unit and integration tests
- docs/phase-1-architecture.md: Capstone architecture deliverables for this phase

## Run Locally

1. Create and activate Python 3.11 virtual environment.
2. Install dependencies:
   pip install -r requirements.txt
3. Start API:
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8090
4. API docs:
   http://localhost:8090/docs

For separated services architecture:
- Backend API (capability router):
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8090
- Agent runtime:
   uvicorn app.agent_runtime:app --reload --host 0.0.0.0 --port 8091
- MCP HTTP gateway:
   uvicorn app.mcp_gateway:app --reload --host 0.0.0.0 --port 8092

Or use helper scripts:
- Start all services (8090/8091/8092):
   ./scripts/start_services.sh
- Stop all services (graceful stop + port cleanup):
   ./scripts/stop_services.sh

## Run Streamlit Interface

- streamlit run streamlit_app.py

Environment variables used by chat capability routing:
- LLM_MODEL
- LLM_API_KEY
- LLM_BASE_URL

Environment variables used by MCP tool auth/RBAC:
- MCP_INTERNAL_KEY
- Caller use case is sent by the client at runtime (not loaded from .env).

Example:
- LLM_MODEL=global.anthropic.claude-sonnet-4-6
- LLM_API_KEY=<your-rotated-key>
- LLM_BASE_URL=https://llmgw-wp.tekstac.com

UI modes:
- Guided workflow mode: form-based referral recommendation (safer for healthcare data capture)
- Chat-style mode: natural language query, capability inferred by LLM router, then executed

Fallback behavior:
- If LLM config is missing or the gateway call fails, answer generation is blocked and the app returns an explicit error.

Example chat query:
- Recommend specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna

## Sample API Request

POST /api/v1/recommend-specialists

{
  "patient_id": "PT-001",
  "diagnosis": "chest pain",
  "location": "Austin, TX",
  "insurance_plan": "Aetna",
  "max_results": 3
}

## Run MCP Tool Server

python -m app.mcp_server.server

Exposed tools:
- diagnosis_to_specialty
- provider_candidates
- insurance_eligibility

MCP RBAC policy:
- specialist_recommendation: diagnosis_to_specialty, provider_candidates, insurance_eligibility
- referral_triage: diagnosis_to_specialty, provider_candidates
- insurance_validation: insurance_eligibility
- provider_discovery: provider_candidates
- admin_console: diagnosis_to_specialty, provider_candidates, insurance_eligibility

MCP auth behavior:
- Every MCP tool call must include internal key + caller role.
- Server validates MCP_INTERNAL_KEY and role permissions for each tool call.

Current caller role in this chain:
- Specialist recommendation graph sends caller_role=specialist_recommendation from client code.

## Run Tests

pytest -q

## API Collections (Postman + curl)

Artifacts prepared for end-to-end validation (entrypoint RPC -> agents -> MCP -> RBAC):
- Postman collection: `collections/FDE-Capstone-Agentic-HTTP.postman_collection.json`
- Postman environment: `collections/FDE-Capstone-Local.postman_environment.json`
- curl suite: `scripts/curl_collection.sh`

Run curl suite:
- chmod +x scripts/curl_collection.sh
- ./scripts/curl_collection.sh

Optional overrides:
- BACKEND_BASE_URL=http://127.0.0.1:8090 AGENT_BASE_URL=http://127.0.0.1:8091 MCP_BASE_URL=http://127.0.0.1:8092 MCP_INTERNAL_KEY=<your_key> ./scripts/curl_collection.sh

## Docker

Build:
- docker build -t referral-platform:phase1 .

Run:
- docker run --rm -p 8000:8000 referral-platform:phase1
- docker run --rm -p 8090:8090 referral-platform:phase1

## Notes

- External systems (EHR, payer, scheduling) are mocked through static JSON and integration contracts.
- The codebase is intentionally modular to add the next 3 AI capabilities without disrupting current APIs and flow.


chmod +x scripts/start_services.sh scripts/stop_services.sh
./scripts/start_services.sh

./scripts/stop_services.sh

If you are not in project root, use:
bash /home/ubuntu/Desktop/FDE\ Capstone\ Submission\ -\ Aviroop\ Basu/FDE-CAPSTONE-PROJECT/scripts/start_services.sh
bash /home/ubuntu/Desktop/FDE\ Capstone\ Submission\ -\ Aviroop\ Basu/FDE-CAPSTONE-PROJECT/scripts/stop_services.sh
