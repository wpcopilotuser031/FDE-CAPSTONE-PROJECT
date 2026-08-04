# Intelligent Care Coordination & Referral Management Platform

AI-powered referral management platform with multi-agent workflows, MCP-enabled tool integration, document code extraction, and a conversational chat interface for patients, providers, and care agents.

---

## Implemented AI Capabilities

| # | Capability | Agent | MCP Tool |
|---|---|---|---|
| 1 | Specialist Recommendation | `specialist_recommendation_agent` | `diagnosis_to_specialty`, `provider_candidates`, `insurance_eligibility` |
| 2 | Referral Triage & Priority | `referral_triage_agent` | `diagnosis_to_specialty`, `provider_candidates` |
| 3 | Insurance Eligibility Validation | `insurance_validation_agent` | `insurance_eligibility` |
| 4 | Provider Discovery | `provider_discovery_agent` | `provider_candidates` |
| 5 | Alternative Provider Suggestion | `alternative_provider_agent` | `diagnosis_to_specialty`, `provider_candidates`, `insurance_eligibility` |
| 6 | Conversational Assistant | `conversational_assistant_agent` | _(context-grounded LLM, no tools)_ |
| 7 | **Document Code Extraction** _(new)_ | `document_extraction_agent` | `extract_codes` |

---

## Project Structure

```
app/
  main.py                          — FastAPI entrypoint, all HTTP routes
  agent_runtime.py                 — Dedicated agent HTTP invocation runtime
  mcp_gateway.py                   — MCP HTTP gateway (port 8092)
  agents/
    capability_entrypoint.py       — JSON-RPC router, session context, RBAC map
    capability_router.py           — Intent → capability heuristic + LLM routing
    document_extraction_agent.py   — ICD-10 / CPT extraction (LLM + regex fallback)
    specialist_recommendation_agent.py
    referral_triage_agent.py
    insurance_validation_agent.py
    provider_discovery_agent.py
    alternative_provider_agent.py
    conversational_assistant_agent.py
    llm_gateway.py                 — Anthropic-compatible LLM client
  mcp_server/
    server.py                      — MCP tool registry + dual-layer RBAC
    tools.py                       — Shared tool logic (including extract_diagnosis_and_procedure_codes)
    http_gateway.py                — HTTP bridge for MCP tool calls
  mcp_clients/
    specialist_recommendation_client.py — MCP HTTP client (all tools)
  rag/
    provider_index.py              — ChromaDB provider search index
  schemas/
    document_extraction.py         — Pydantic models for code extraction
    specialist_recommendation.py
    jsonrpc.py
data/
  providers.json                   — Mocked provider directory
  diagnosis_specialties.json       — Diagnosis → specialty mapping
  insurance_networks.json          — Payer → provider network mapping
  icd10_codes.json                 — ICD-10 reference descriptions
  cpt_codes.json                   — CPT reference descriptions
  referral_docs/
    ref_doc_001.txt                — Cardiology referral (ICD-10 + CPT codes)
    ref_doc_002.txt                — Lumbar MRI / Orthopedic referral
    ref_doc_003.txt                — Bilateral knee arthroplasty referral
tests/
  test_document_extraction.py      — 16 unit tests for extraction agent + MCP tool
  test_tools.py
  test_capability_router.py
  test_mcp_server_auth.py
  test_api.py
  test_platform_data.py
ui/
  index.html  app.js  styles.css   — Browser frontend (Chat + Document Analyzer tabs)
```

---

## Environment Setup

### 1. Create `.env` in the project root

```env
# LLM Gateway (Anthropic-compatible endpoint)
LLM_MODEL=global.anthropic.claude-sonnet-4-6
LLM_API_KEY=<your-api-key>
LLM_BASE_URL=https://llmgw-wp.tekstac.com

# MCP internal auth key (any secret string, same across all services)
MCP_INTERNAL_KEY=my-secret-key-change-me

# Optional transport flags
USE_MCP_TOOLS=true
AGENT_CALL_TRANSPORT=http
MCP_TRANSPORT=http
AGENT_RUNTIME_BASE_URL=http://127.0.0.1:8091
MCP_HTTP_BASE_URL=http://127.0.0.1:8092
```

> Without `LLM_MODEL`, `LLM_API_KEY`, and `LLM_BASE_URL` the LLM-assisted paths return errors, but the regex-based fallbacks in the Document Extraction agent still work.

---

## Run Locally (Three-Service Architecture)

### Option A — Helper script (recommended)

```bash
./scripts/start_services.sh        # starts all three services
./scripts/stop_services.sh         # stops them cleanly
./scripts/run_ui.sh                # serves UI on port 8080
```

### Option B — Manual (three terminals)

**Terminal 1 — Backend API (port 8090)**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8090
```

**Terminal 2 — Agent Runtime (port 8091)**
```bash
uvicorn app.agent_runtime:app --reload --host 0.0.0.0 --port 8091
```

**Terminal 3 — MCP HTTP Gateway (port 8092)**
```bash
uvicorn app.mcp_gateway:app --reload --host 0.0.0.0 --port 8092
```

**Terminal 4 — UI static server (port 8080)**
```bash
./scripts/run_ui.sh
```

Then open: **http://127.0.0.1:8080**

---

## Docker

```bash
./scripts/docker_build_and_run.sh
```

Services:

| Service | URL |
|---|---|
| Backend API | http://127.0.0.1:8090 |
| Agent Runtime | http://127.0.0.1:8091 |
| MCP Gateway | http://127.0.0.1:8092 |
| UI (nginx) | http://127.0.0.1:8093 |

Manual Docker run (backend only):
```bash
docker build -t referral-platform:latest .
docker run --rm -p 8090:8090 --env-file .env referral-platform:latest
```

---

## API Reference

### Authentication

```
POST /api/v1/auth/login
{ "username": "provider1", "password": "Provider@123" }
→ { "token": "...", "role": "provider", "display_name": "Dr. Lee" }
```

All other API calls require header: `X-Session-Token: <token>`

### Demo credentials

| Role | Username | Password |
|---|---|---|
| Patient | `patient1` | `Patient@123` |
| Provider | `provider1` | `Provider@123` |
| Care Agent | `careagent1` | `CareAgent@123` |

### Key endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/capability-router` | JSON-RPC agent routing (chat, triage, recommend, etc.) |
| `POST` | `/api/v1/recommend-specialists` | Direct specialist recommendation |
| `POST` | `/api/v1/documents/extract-codes` | **Extract ICD-10 + CPT codes from document text** |
| `GET` | `/api/v1/documents/sample-docs` | List sample referral documents |
| `GET` | `/api/v1/platform-data` | Full platform dashboard data |
| `GET` | `/health` | Health check |
| `GET` | `/docs` | Swagger UI |

### Document Code Extraction — request/response

```json
POST /api/v1/documents/extract-codes
Headers: X-Session-Token: <provider or care_agent token>

{
  "document_text": "Patient diagnosis: essential hypertension — ICD-10: I10\nECG ordered — CPT: 93000",
  "document_id": "DOC-001"
}

→ {
  "document_id": "DOC-001",
  "diagnosis_codes": [{ "code": "I10", "description": "Essential (primary) hypertension" }],
  "procedure_codes": [{ "code": "93000", "description": "Electrocardiogram, routine ECG with at least 12 leads" }],
  "clinical_summary": "Patient with hypertension referred for cardiac evaluation.",
  "total_diagnosis_codes": 1,
  "total_procedure_codes": 1,
  "extraction_method": "llm",
  "extracted_at": "2026-08-04T10:00:00+00:00",
  "decision_trace": { ... }
}
```

---

## MCP Tool Reference

| Tool | Allowed Roles |
|---|---|
| `diagnosis_to_specialty` | specialist_recommendation, referral_triage, alternative_provider_suggestion, admin_console |
| `provider_candidates` | specialist_recommendation, referral_triage, provider_discovery, alternative_provider_suggestion, admin_console |
| `insurance_eligibility` | specialist_recommendation, insurance_validation, alternative_provider_suggestion, admin_console |
| `extract_codes` | **document_code_extraction**, admin_console |

User-role RBAC on MCP tools:

| Tool | patient | provider | care_agent |
|---|---|---|---|
| `diagnosis_to_specialty` | ✓ | ✓ | ✓ |
| `provider_candidates` | ✓ | ✓ | ✓ |
| `insurance_eligibility` | ✗ | ✓ | ✓ |
| `extract_codes` | ✗ | ✓ | ✓ |

---

## Run Tests

```bash
pytest -q                                      # all tests
pytest tests/test_document_extraction.py -v   # document extraction only
pytest tests/test_mcp_server_auth.py -v       # RBAC / auth tests
pytest tests/test_capability_router.py -v     # intent routing tests
```

---

## UI Testing Guide — Step by Step

### Prerequisites
- All three services running (ports 8090, 8091, 8092).
- `.env` configured with valid `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL`, and `MCP_INTERNAL_KEY`.
- UI open at **http://127.0.0.1:8080** (or port 8093 in Docker).

---

### Step 1 — Verify services are live

Open a browser and check:
- http://127.0.0.1:8090/health → `{"status":"ok"}`
- http://127.0.0.1:8091/health → `{"status":"ok"}`
- http://127.0.0.1:8092/health → `{"status":"ok"}`

---

### Step 2 — Sign in and test as each role

Click **Quick demo sign-in** buttons on the login screen.

---

### Step 3 — Test Chat capabilities (💬 Chat tab)

Sign in as any role and type these prompts in the chat box:

#### Specialist Recommendation (sign in as **Patient** or **Care Agent**)
```
Recommend a specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna
```
```
I need a cardiologist in Austin for a patient with heart failure. Insurance is BlueCross.
```
**Expected:** Ranked list of specialist providers with scores, wait times, and in-network status.

#### Referral Triage (any role)
```
What is the triage priority for a patient with stroke symptoms and worsening condition?
```
```
Assess urgency for diagnosis: uncontrolled hypertension
```
**Expected:** Priority label (high/medium/low), priority score, recommended specialties.

#### Insurance Validation (sign in as **Provider** or **Care Agent**)
```
Check if provider PROV-001 is in-network for Aetna insurance
```
```
Is provider PROV-005 covered under BlueCross plan?
```
**Expected:** In-network: Yes/No with provider ID and plan name.

#### Provider Discovery (any role)
```
Find cardiologists near Austin, TX
```
```
Discover providers for knee pain near Houston
```
**Expected:** List of matching providers with specialty and location.

#### Alternative Provider (sign in as **Patient** or **Care Agent**)
```
Find alternative providers for chest pain in Austin, TX, insurance: Aetna, excluding provider PROV-001, within 14 days
```
**Expected:** Alternative ranked providers, excluding the specified one, within the window.

#### Conversational Follow-up (any role — after a recommendation)
```
Which of those providers accepts Aetna?
```
```
What is the wait time for the top recommendation?
```
**Expected:** Context-aware answer grounded in the previous agent result.

---

### Step 4 — Test Document Code Extraction (📄 Document Analyzer tab)

> **Access:** Only available to **Provider** and **Care Agent** roles. Patients will see a 403 error.

**Sign in as Provider (`provider1 / Provider@123`) or Care Agent (`careagent1 / CareAgent@123`).**

1. Click the **📄 Document Analyzer** tab in the top-right header.
2. You will see the Document Code Extractor panel.

#### Test A — Using a sample document
1. Click one of the sample buttons (e.g., **DOC-REF-001**).
2. The referral document text loads into the text area.
3. Click **🔍 Extract Codes**.
4. **Expected result (LLM path):**
   - ICD-10 table: `I10`, `E11.9`, `E78.5`, `I48.0`
   - CPT table: `93000`, `80053`, `83036`, `93306`
   - Clinical summary sentence
   - Method badge: `llm`
5. **Expected result (regex fallback, if LLM unavailable):**
   - Same codes extracted via pattern matching
   - Method badge: `regex`

#### Test B — Upload a `.txt` file
1. Click **browse** in the drop zone, or drag a `.txt` file onto it.
2. The file content appears in the text area.
3. Click **🔍 Extract Codes**.
4. Observe the ICD-10 and CPT code tables populate.

#### Test C — Paste raw text
Paste this into the text area and click **🔍 Extract Codes**:
```
REFERRAL NOTE
Patient: Jane Smith
Diagnosis: Type 2 diabetes mellitus without complications — ICD-10: E11.9
Co-morbidity: Essential hypertension — ICD-10: I10
Procedure: Hemoglobin A1C test ordered — CPT: 83036
Procedure: Comprehensive metabolic panel — CPT: 80053
Please refer to Endocrinology for diabetes management.
```
**Expected:** 2 diagnosis codes (E11.9, I10), 2 procedure codes (83036, 80053).

#### Test D — Inject codes into chat
1. After a successful extraction, click **💬 Ask about these codes**.
2. The **Chat** tab opens with a pre-filled question referencing the extracted ICD-10 and CPT codes.
3. Press **Send**.
4. **Expected:** The conversational assistant recommends a specialist based on the extracted diagnosis codes.

#### Test E — Patient role is blocked
1. Sign out. Sign in as **Patient (`patient1 / Patient@123`)**.
2. Click **📄 Document Analyzer**.
3. Paste any text and click **🔍 Extract Codes**.
4. **Expected:** "Access denied. Document extraction is only available to providers and care agents."

---

### Step 5 — Verify LLM is active

After sending a chat message that routes to an agent, the response JSON includes `"llm_used": true`. You can verify in browser DevTools → Network → `capability-router` request → Response JSON:

```json
"agent_result": {
  "llm_used": true,
  ...
}
```

For document extraction, the `extraction_method` field in the API response shows `"llm"` when the LLM is active, or `"regex"` when it falls back.

---

### Step 6 — Test RBAC enforcement

| Test | Role | Expected |
|---|---|---|
| Specialist recommendation | Patient | ✓ Works |
| Specialist recommendation | Provider | ✗ Blocked (not in provider capability map) |
| Insurance validation | Patient | ✗ Blocked |
| Insurance validation | Provider | ✓ Works |
| Document extraction | Patient | ✗ 403 Forbidden |
| Document extraction | Provider | ✓ Works |
| Document extraction | Care Agent | ✓ Works |

---

### Step 7 — Direct API test (curl)

```bash
# 1. Login
curl -s -X POST http://127.0.0.1:8090/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"provider1","password":"Provider@123"}' | python -m json.tool

# 2. Extract codes (replace TOKEN with value from step 1)
curl -s -X POST http://127.0.0.1:8090/api/v1/documents/extract-codes \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: TOKEN" \
  -d '{
    "document_text": "Diagnosis: chest pain ICD-10: R07.9\nProcedure: ECG CPT: 93000",
    "document_id": "DOC-TEST"
  }' | python -m json.tool

# 3. Chat capability routing
curl -s -X POST http://127.0.0.1:8090/api/v1/capability-router \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "capability.route",
    "params": {
      "capability": "conversational_assistant",
      "payload": {
        "question": "Recommend a specialist for chest pain in Austin with Aetna insurance",
        "asker_role": "Provider"
      }
    }
  }' | python -m json.tool
```

---

### Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `LLM dependency unavailable (503)` | Missing or invalid LLM env vars | Check `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` in `.env` |
| `MCP dependency unavailable (503)` | MCP gateway not running on 8092 | Start `uvicorn app.mcp_gateway:app --port 8092` |
| `Unauthorized MCP caller` | Wrong `MCP_INTERNAL_KEY` | Ensure same key in `.env` across all services |
| `HTTP agent call failed` | Agent runtime not on 8091 | Start `uvicorn app.agent_runtime:app --port 8091` |
| `extraction_method: regex` instead of `llm` | LLM unavailable (fallback active) | Check LLM config; regex extraction still works |
| Document Analyzer tab missing | Signed in as patient | Log out and sign in as provider or care_agent |
| Chat returns generic error | Session expired | Log out and sign in again |

---

## Postman / curl collections

- Postman collection: `collections/FDE-Capstone-Agentic-HTTP.postman_collection.json`
- Postman environment: `collections/FDE-Capstone-Local.postman_environment.json`
- curl suite: `scripts/curl_collection.sh`

```bash
chmod +x scripts/curl_collection.sh
./scripts/curl_collection.sh
```


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
- Browser-based HTML/JavaScript frontend served from FastAPI

## Project Structure

- app/main.py: FastAPI service entrypoint
- ui/index.html: Browser UI entrypoint
- ui/app.js: Browser client logic for capability routing and workflow
- ui/styles.css: Browser UI styles
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

## Run Web Interface

The API backend should run on port `8090`. The browser UI can be hosted independently on a separate port.

- Start the backend API:
  ```bash
  uvicorn app.main:app --reload --host 0.0.0.0 --port 8090
  ```
- Start the UI server from the repo root:
  ```bash
  ./scripts/run_ui.sh
  ```
- Open the browser UI at:
  ```bash
  http://127.0.0.1:8080
  ```

If you want to customize the backend base URL from the UI, enter:
```bash
http://127.0.0.1:8090
```

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

Use `docker-compose` to build and run all services (backend, agent runtime, MCP gateway, and UI):

```bash
./scripts/docker_build_and_run.sh
```

This will build the image and start the following services:

- Backend API: http://127.0.0.1:8090
- Agent runtime: http://127.0.0.1:8091
- MCP gateway: http://127.0.0.1:8092
- UI (nginx): http://127.0.0.1:8093

If you prefer to run only the backend container directly, build the reusable image and pass runtime environment values from `.env`:

```bash
docker build -t referral-platform:phase1 .
docker run --rm -p 8090:8090 --env-file .env referral-platform:phase1
```

This lets you run the backend image from another machine while keeping secrets and runtime URLs out of the image.

Open the standalone UI at:

```bash
http://127.0.0.1:8093
```

## Notes

- External systems (EHR, payer, scheduling) are mocked through static JSON and integration contracts.
- The codebase is intentionally modular to add the next 3 AI capabilities without disrupting current APIs and flow.


chmod +x scripts/start_services.sh scripts/stop_services.sh
./scripts/start_services.sh

./scripts/stop_services.sh

If you are not in project root, use:
bash /home/ubuntu/Desktop/FDE\ Capstone\ Submission\ -\ Aviroop\ Basu/FDE-CAPSTONE-PROJECT/scripts/start_services.sh
bash /home/ubuntu/Desktop/FDE\ Capstone\ Submission\ -\ Aviroop\ Basu/FDE-CAPSTONE-PROJECT/scripts/stop_services.sh
