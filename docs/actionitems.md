# Action Items: Implementing Additional AI Use Cases

## Team Member Guide — FDE Capstone Intelligent Care Coordination Platform

This document provides detailed guidance for team members to implement the remaining AI use cases while adhering to the established solution architecture.

---

## Table of Contents

1. [What's Already Implemented](#whats-already-implemented)
2. [Available Use Cases to Implement](#available-use-cases-to-implement)
3. [Solution Architecture Overview](#solution-architecture-overview)
4. [End-to-End Request Flow](#end-to-end-request-flow)
5. [Code Structure Reference](#code-structure-reference)
6. [Step-by-Step Implementation Guide](#step-by-step-implementation-guide)
7. [Detailed Implementation Examples](#detailed-implementation-examples)
8. [Testing Your Implementation](#testing-your-implementation)
9. [Checklist Before PR](#checklist-before-pr)

---

## What's Already Implemented

### ✅ Completed Use Cases

| # | Use Case | Agent | Graph File |
|---|----------|-------|------------|
| 1 | **Recommend specialists** based on diagnosis, location, and insurance network | `specialist_recommendation_agent` | `specialist_recommendation_graph.py` |
| 2 | **Suggest alternative providers** if appointments exceed target wait times | `alternative_provider_agent` | `alternative_provider_graph.py` |

---

## Available Use Cases to Implement

**Each team member picks ONE of the following (pick any 3 total):**

| # | Use Case | Suggested Capability Name | Complexity |
|---|----------|---------------------------|------------|
| 1 | Extract diagnosis & procedure codes from uploaded referral documents | `document_extraction` | High |
| 2 | Summarise referral history for specialists before consultation | `referral_summary` | Medium |
| 3 | Identify missing documents before referral submission | `document_gap_detection` | Medium |
| 4 | Predict referral delays and recommend escalation | `delay_prediction` | Medium |
| 5 | Answer patient queries through a conversational assistant | `conversational_assistant` | Medium |

---

## Solution Architecture Overview

### Three-Service Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                    │
│  ┌─────────────────┐    ┌─────────────────────────────────────────────────┐ │
│  │   Browser UI    │    │  External Systems (Postman, EHR, etc.)          │ │
│  │ (ui/index.html) │    │                                                 │ │
│  └────────┬────────┘    └───────────────────────┬─────────────────────────┘ │
└───────────┼─────────────────────────────────────┼───────────────────────────┘
            │ HTTP                                │ HTTP
            ▼                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER (FastAPI)                              │
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  MAIN API — Port 8090 (app/main.py)                                   │   │
│  │  • /api/v1/recommend-specialists (direct endpoint)                    │   │
│  │  • /api/v1/capability-router (JSON-RPC 2.0 gateway)                   │   │
│  │  • /static/* (serves UI)                                              │   │
│  └────────────────────────────────┬─────────────────────────────────────┘   │
│                                   │                                          │
│                                   │ HTTP (internal)                          │
│                                   ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  AGENT RUNTIME — Port 8091 (app/agent_runtime.py)                     │   │
│  │  • POST /api/v1/agents/{capability}/invoke                            │   │
│  │  • Dispatches to use_case_agents.py functions                         │   │
│  └────────────────────────────────┬─────────────────────────────────────┘   │
│                                   │                                          │
│                                   │ HTTP (internal)                          │
│                                   ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  MCP GATEWAY — Port 8092 (app/mcp_gateway.py)                         │   │
│  │  • POST /api/v1/mcp/call                                              │   │
│  │  • RBAC enforcement per caller_role                                   │   │
│  │  • Tools: diagnosis_to_specialty, provider_candidates,                │   │
│  │           insurance_eligibility, (+ your new tools)                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Design Patterns

| Pattern | Implementation | Why |
|---------|----------------|-----|
| **Agent Card Discovery** | `capability_entrypoint.py` | Self-describing agents with input contracts, RBAC roles, and tool dependencies |
| **JSON-RPC 2.0 Gateway** | `capability_router.py` | Standard RPC protocol for capability routing with LLM intent extraction |
| **LangGraph Pipelines** | `*_graph.py` files | Stateful, traceable, composable multi-step AI workflows |
| **MCP Tool Governance** | `mcp_server/server.py` | RBAC-enforced tool access — each agent role has whitelisted tools |
| **RAG with ChromaDB** | `rag/provider_index.py` | Semantic search over provider data |
| **Decision Trace** | Every response | Audit trail: capability, role, tools invoked, human_review_required |

---

## End-to-End Request Flow

### Flow Diagram (UI → Backend → Response)

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│             │     │                 │     │                 │     │                 │
│  Browser UI │────▶│  Main API       │────▶│  Agent Runtime  │────▶│  LangGraph      │
│             │     │  :8090          │     │  :8091          │     │  Pipeline       │
│             │     │                 │     │                 │     │                 │
└─────────────┘     └─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                                             │
                    ┌─────────────────┐     ┌─────────────────┐              │
                    │                 │     │                 │              │
                    │  ChromaDB RAG   │◀────│  MCP Gateway    │◀─────────────┘
                    │  (local)        │     │  :8092          │
                    │                 │     │                 │
                    └─────────────────┘     └─────────────────┘
                                                   │
                                                   ▼
                                           ┌─────────────────┐
                                           │  Anthropic LLM  │
                                           │  (external)     │
                                           └─────────────────┘
```

### Detailed Step-by-Step (Example: Specialist Recommendation)

1. **UI** (`ui/app.js`) — User fills intake form, clicks "Generate Recommendations"
   ```javascript
   payload: {
     diagnosis: "chest pain",
     location: "Austin, TX",
     insurance_plan: "Aetna",
     max_results: 5,
     urgency: "Priority",
     preferred_window_days: 7
   }
   ```

2. **Main API** (`app/main.py`) — Receives JSON-RPC request at `/api/v1/capability-router`
   ```json
   {
     "jsonrpc": "2.0",
     "id": "req-001",
     "method": "capability.route",
     "params": {
       "capability": "specialist_recommendation",
       "payload": { ... }
     }
   }
   ```

3. **Capability Entrypoint** (`app/agents/capability_entrypoint.py`)
   - Looks up the AgentCard for `specialist_recommendation`
   - Forwards to Agent Runtime via HTTP

4. **Agent Runtime** (`app/agent_runtime.py`)
   - Routes to `specialist_recommendation_agent()` in `use_case_agents.py`
   - Calls `run_specialist_recommendation_flow()` from the graph

5. **LangGraph Pipeline** (`app/agents/specialist_recommendation_graph.py`)
   - **Node 1: `infer_specialties`** — LLM maps diagnosis → canonical specialty names
   - **Node 2: `fetch_candidates`** — RAG query or MCP tool call for providers
   - **Node 3: `rank_recommendations`** — Score, filter, generate LLM rationales

6. **MCP Gateway** (`app/mcp_gateway.py` → `app/mcp_server/`)
   - Receives tool calls (e.g., `provider_candidates`, `insurance_eligibility`)
   - Validates `caller_role` + `internal_key` against `USE_CASE_TOOL_MAP`
   - Executes tool and returns result

7. **Response** — Flows back up the chain with `decision_trace`:
   ```json
   {
     "request_id": "...",
     "recommendations": [...],
     "decision_trace": {
       "capability": "specialist_recommendation",
       "caller_role": "specialist_recommendation",
       "mcp_enabled": true,
       "tools_invoked": ["provider_candidates", "insurance_eligibility"],
       "human_review_required": false
     }
   }
   ```

---

## Code Structure Reference

```
app/
├── main.py                      # Main API (port 8090)
├── agent_runtime.py             # Agent Runtime (port 8091)
├── mcp_gateway.py               # MCP Gateway (port 8092)
├── config.py                    # Paths, constants
├── data_loader.py               # JSON file loading utility
│
├── agents/
│   ├── capability_entrypoint.py # AgentCard registry + JSON-RPC handler
│   ├── capability_router.py     # LLM intent extraction + heuristic routing
│   ├── use_case_agents.py       # Agent functions (one per capability)
│   ├── llm_gateway.py           # Anthropic LLM client
│   ├── specialist_recommendation_graph.py   # ✅ LangGraph pipeline
│   ├── alternative_provider_graph.py        # ✅ LangGraph pipeline
│   └── <your_use_case>_graph.py             # 🆕 YOUR NEW GRAPH
│
├── mcp_server/
│   ├── server.py                # MCP tool definitions + RBAC map
│   ├── http_gateway.py          # HTTP adapter for MCP tools
│   └── tools.py                 # Actual tool implementations
│
├── mcp_clients/
│   └── specialist_recommendation_client.py  # HTTP client for MCP calls
│
├── rag/
│   ├── provider_index.py        # ChromaDB index builder + query
│   └── embeddings.py            # Hash-based embedding function
│
└── schemas/
    ├── jsonrpc.py               # JSON-RPC request/response models
    └── specialist_recommendation.py  # Pydantic schemas
```

---

## Step-by-Step Implementation Guide

### 🔴 Step 1: Create Your LangGraph Pipeline

**File:** `app/agents/<your_capability>_graph.py`

Use this template:

```python
"""
LangGraph pipeline for <Your Use Case Name>.

<Brief description of what this pipeline does>
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from typing import Any, Callable, TypedDict
from uuid import uuid4

from langgraph.graph import END, StateGraph

from app.mcp_clients.specialist_recommendation_client import (
    MCPClientError,
    SpecialistRecommendationMCPClient,
)
from app.mcp_server.tools import (
    # Import the tools you need
)

YOUR_CAPABILITY_ROLE = "<your_capability_name>"  # Must match RBAC role


class YourCapabilityState(TypedDict):
    # Define all state fields your pipeline needs
    input_field_1: str
    input_field_2: str
    # ... intermediate state
    results: list[dict[str, Any]]
    missing_information: list[str]
    llm_used: bool
    mcp_client: SpecialistRecommendationMCPClient | None
    mcp_enabled: bool
    tools_invoked: list[str]
    progress_callback: Callable[[str], None] | None


# ---------------------------------------------------------------------------
# Graph nodes (one function per step)
# ---------------------------------------------------------------------------

def step_one(state: YourCapabilityState) -> YourCapabilityState:
    """First processing step."""
    progress = state.get("progress_callback")
    if progress:
        progress("Running step one...")
    
    # Your logic here
    # Update state fields
    
    return state


def step_two(state: YourCapabilityState) -> YourCapabilityState:
    """Second processing step."""
    progress = state.get("progress_callback")
    if progress:
        progress("Running step two...")
    
    # Your logic here
    # If using MCP tools:
    if "your_tool_name" not in state["tools_invoked"]:
        state["tools_invoked"].append("your_tool_name")
    
    return state


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_your_capability_graph() -> Any:
    builder = StateGraph(YourCapabilityState)
    builder.add_node("step_one", step_one)
    builder.add_node("step_two", step_two)

    builder.set_entry_point("step_one")
    builder.add_edge("step_one", "step_two")
    builder.add_edge("step_two", END)

    return builder.compile()


def run_your_capability_flow(
    input_field_1: str,
    input_field_2: str,
    # ... other params
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    graph = build_your_capability_graph()
    use_mcp = os.getenv("USE_MCP_TOOLS", "true").strip().lower() in {"true", "1", "yes", "on"}

    base_state: dict[str, Any] = {
        "input_field_1": input_field_1,
        "input_field_2": input_field_2,
        "results": [],
        "missing_information": [],
        "llm_used": False,
        "mcp_enabled": use_mcp,
        "tools_invoked": [],
        "progress_callback": progress_callback,
    }

    try:
        if use_mcp:
            with SpecialistRecommendationMCPClient(
                caller_role=YOUR_CAPABILITY_ROLE
            ) as mcp_client:
                base_state["mcp_client"] = mcp_client
                final_state = graph.invoke(base_state)
        else:
            base_state["mcp_client"] = None
            final_state = graph.invoke(base_state)
    except MCPClientError:
        raise

    # Determine if human review is required based on your business rules
    human_review_required = False  # Your logic here

    return {
        "request_id": str(uuid4()),
        "generated_at": datetime.now(UTC).isoformat(),
        "results": final_state["results"],
        "missing_information": final_state["missing_information"],
        "llm_used": final_state["llm_used"],
        "decision_trace": {
            "capability": "<your_capability_name>",
            "caller_role": YOUR_CAPABILITY_ROLE,
            "mcp_enabled": final_state["mcp_enabled"],
            "tools_invoked": final_state["tools_invoked"],
            "human_review_required": human_review_required,
        },
    }
```

---

### 🟠 Step 2: Add RBAC Role to MCP Server

**File:** `app/mcp_server/server.py`

Add your role to `USE_CASE_TOOL_MAP`:

```python
USE_CASE_TOOL_MAP: dict[str, set[str]] = {
    "specialist_recommendation": {...},
    "referral_triage": {...},
    "insurance_validation": {...},
    "provider_discovery": {...},
    "alternative_provider_suggestion": {...},
    
    # 🆕 ADD YOUR ROLE HERE
    "<your_capability_name>": {
        "tool_1",
        "tool_2",
        # List the MCP tools your capability needs
    },
    
    "admin_console": {...},
}
```

**If you need NEW MCP tools**, add them in:
1. `app/mcp_server/tools.py` — Implement the tool function
2. `app/mcp_server/server.py` — Register with `@mcp.tool()` decorator
3. `app/mcp_server/http_gateway.py` — Add HTTP route handling

---

### 🟡 Step 3: Add Agent Card

**File:** `app/agents/capability_entrypoint.py`

Add a new `AgentCard` to the `_AGENT_CARDS` list:

```python
AgentCard(
    agent_id="agent.<your_capability_name>.v1",
    capability="<your_capability_name>",
    display_name="<Your Display Name> Agent",
    description="<What this agent does in one sentence>",
    input_contract={
        "required": ["field_1", "field_2"],
        "optional": ["field_3", "field_4"],
    },
    rbac_role="<your_capability_name>",
    mcp_tools=["tool_1", "tool_2"],  # List MCP tools used
),
```

---

### 🟢 Step 4: Add Use-Case Agent Function

**File:** `app/agents/use_case_agents.py`

1. Import your graph:
   ```python
   from app.agents.<your_capability>_graph import run_<your_capability>_flow
   ```

2. Add your agent function:
   ```python
   def <your_capability>_agent(payload: dict[str, Any]) -> dict[str, Any]:
       field_1 = str(payload.get("field_1", "")).strip()
       field_2 = str(payload.get("field_2", "")).strip()

       if not field_1 or not field_2:
           return {
               "results": [],
               "missing_information": ["field_1 and field_2 are required"],
               "decision_trace": {
                   "capability": "<your_capability_name>",
                   "caller_role": "<your_capability_name>",
                   "mcp_enabled": _use_mcp_tools(),
                   "tools_invoked": [],
                   "human_review_required": False,
               },
           }

       return run_<your_capability>_flow(
           field_1=field_1,
           field_2=field_2,
           # ... other params from payload
       )
   ```

---

### 🔵 Step 5: Register in Agent Runtime

**File:** `app/agent_runtime.py`

1. Import:
   ```python
   from app.agents.use_case_agents import (
       ...,
       <your_capability>_agent,
   )
   ```

2. Add to handler map:
   ```python
   _AGENT_ENDPOINT_HANDLERS = {
       ...,
       "<your_capability_name>": <your_capability>_agent,
   }
   ```

---

### 🟣 Step 6: (Optional) Add Pydantic Schemas

**File:** `app/schemas/<your_capability>.py`

```python
from pydantic import BaseModel, Field


class YourCapabilityRequest(BaseModel):
    field_1: str = Field(..., description="Description")
    field_2: str = Field(..., description="Description")


class YourCapabilityResponse(BaseModel):
    request_id: str
    generated_at: str | None = None
    results: list[dict]
    # ...
```

---

### ⚪ Step 7: (Optional) Add Direct REST Endpoint

**File:** `app/main.py`

If you want a direct endpoint (in addition to JSON-RPC routing):

```python
@app.post("/api/v1/<your-capability>", response_model=YourCapabilityResponse)
def your_capability_endpoint(request: YourCapabilityRequest) -> YourCapabilityResponse:
    result = run_<your_capability>_flow(
        field_1=request.field_1,
        field_2=request.field_2,
    )
    return YourCapabilityResponse(**result)
```

---

## Detailed Implementation Examples

### Example A: Document Gap Detection (`document_gap_detection`)

**Goal:** Identify missing documents before referral submission.

**Suggested Graph Nodes:**
1. `extract_required_docs` — LLM analyzes diagnosis to determine required documents
2. `check_submitted_docs` — Compare required vs. submitted documents
3. `generate_gap_report` — List missing documents with explanations

**Sample MCP Tools:**
- `get_required_documents(diagnosis: str) -> list[str]`
- `get_submitted_documents(referral_id: str) -> list[str]`

**Human Review Required When:**
- Critical documents missing (e.g., lab results for urgent cases)
- Unable to determine required documents from diagnosis

---

### Example B: Referral Summary (`referral_summary`)

**Goal:** Summarise referral history for specialists before consultation.

**Suggested Graph Nodes:**
1. `fetch_referral_history` — Retrieve past referrals for patient
2. `extract_key_points` — LLM extracts diagnoses, treatments, outcomes
3. `generate_summary` — LLM creates concise clinical summary

**Sample MCP Tools:**
- `get_patient_referrals(patient_id: str) -> list[dict]`
- `get_clinical_notes(referral_id: str) -> str`

**Human Review Required When:**
- Conflicting information in history
- High-risk conditions detected

---

### Example C: Conversational Assistant (`conversational_assistant`)

**Goal:** Answer patient queries about referrals using natural language.

**Suggested Graph Nodes:**
1. `classify_intent` — LLM determines query type (status, scheduling, eligibility, etc.)
2. `gather_context` — Fetch relevant data based on intent
3. `generate_response` — LLM generates natural language answer

**Sample MCP Tools:**
- Reuse existing tools based on query intent
- `get_referral_status(referral_id: str) -> dict`

**Human Review Required When:**
- Query involves PHI disclosure
- Unable to answer with high confidence

---

## Testing Your Implementation

### 1. Unit Tests

Create `tests/test_<your_capability>.py`:

```python
def test_<your_capability>_basic():
    from app.agents.<your_capability>_graph import run_<your_capability>_flow
    
    result = run_<your_capability>_flow(
        field_1="test_value",
        field_2="test_value",
    )
    
    assert "request_id" in result
    assert "decision_trace" in result
    assert result["decision_trace"]["capability"] == "<your_capability_name>"


def test_<your_capability>_missing_input():
    from app.agents.use_case_agents import <your_capability>_agent
    
    result = <your_capability>_agent({})
    
    assert "missing_information" in result
    assert len(result["missing_information"]) > 0
```

### 2. Integration Test via Postman/curl

```bash
curl -X POST http://localhost:8090/api/v1/capability-router \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-001",
    "method": "capability.route",
    "params": {
      "capability": "<your_capability_name>",
      "payload": {
        "field_1": "value",
        "field_2": "value"
      }
    }
  }'
```

### 3. Run All Tests

```bash
pytest tests/ -v
```

---

## Checklist Before PR

- [ ] **Graph file** created in `app/agents/<capability>_graph.py`
- [ ] **RBAC role** added to `USE_CASE_TOOL_MAP` in `app/mcp_server/server.py`
- [ ] **AgentCard** added to `_AGENT_CARDS` in `app/agents/capability_entrypoint.py`
- [ ] **Agent function** added to `app/agents/use_case_agents.py`
- [ ] **Handler registered** in `_AGENT_ENDPOINT_HANDLERS` in `app/agent_runtime.py`
- [ ] **Unit tests** added in `tests/test_<capability>.py`
- [ ] **No Pylance errors** in modified files
- [ ] **decision_trace** includes all required fields:
  - `capability`
  - `caller_role`
  - `mcp_enabled`
  - `tools_invoked`
  - `human_review_required`
- [ ] **human_review_required** has meaningful business logic
- [ ] Tested via JSON-RPC endpoint

---

## Environment Setup

### Local Development

```bash
# Create .env file with:
LLM_API_KEY=your_anthropic_key
LLM_BASE_URL=https://api.anthropic.com
LLM_MODEL=claude-3-5-sonnet-20241022
MCP_INTERNAL_KEY=some-secret-key
MCP_TRANSPORT=http
MCP_HTTP_BASE_URL=http://127.0.0.1:8092
AGENT_RUNTIME_BASE_URL=http://127.0.0.1:8091
USE_MCP_TOOLS=true

# Start all services (3 terminals):
uvicorn app.main:app --port 8090 --reload
uvicorn app.agent_runtime:app --port 8091 --reload
uvicorn app.mcp_gateway:app --port 8092 --reload
```

### Docker

```bash
docker build -t fde-capstone .
docker run --env-file .env -p 8090:8090 -p 8091:8091 -p 8092:8092 fde-capstone
```

---

## Questions?

Reach out to the Tech Lead for:
- Architecture decisions
- MCP tool additions
- Integration patterns
- Code review

**Remember:** Follow the existing patterns — consistency across all use cases is key for maintainability and evaluation.
