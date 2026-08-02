# Solution Architecture — Specialist Recommendation & Alternative Provider Suggestion

## Intelligent Care Coordination & Referral Management Platform

This document describes the complete solution architecture for the two implemented use cases:
1. **Recommend specialists based on diagnosis, location, and insurance network**
2. **Suggest alternative providers if appointments exceed target wait times**

---

## Table of Contents

1. [High-Level Design (HLD)](#1-high-level-design-hld)
2. [Low-Level Design (LLD)](#2-low-level-design-lld)
3. [End-to-End Sequence Diagram](#3-end-to-end-sequence-diagram)
4. [Component Responsibilities](#4-component-responsibilities)
5. [Data Model & Contracts](#5-data-model--contracts)
6. [Scoring Algorithm Detail](#6-scoring-algorithm-detail)
7. [Security & Governance](#7-security--governance)
8. [Deployment View](#8-deployment-view)

---

## 1. High-Level Design (HLD)

### 1.1 System Context Diagram

```mermaid
graph TB
    Patient((Patient / Care<br/>Coordinator))
    UI[Referral Command Center UI]
    Platform[Care Coordination Platform]
    LLM[(Anthropic LLM API)]
    Chroma[(ChromaDB Vector Store)]
    DataFiles[(Static Data:<br/>providers.json,<br/>diagnosis_specialties.json,<br/>insurance_networks.json)]

    Patient -->|Fills intake form /<br/>asks NL query| UI
    UI -->|HTTPS/JSON| Platform
    Platform -->|LLM reasoning:<br/>specialty inference,<br/>rationale generation| LLM
    Platform -->|Semantic provider search| Chroma
    Platform -->|Reads reference data| DataFiles
    Platform -->|Recommendations +<br/>audit trace| UI
```

### 1.2 High-Level Component View

```mermaid
graph TB
    subgraph Client
        UI["Browser UI<br/>(ui/index.html + app.js)"]
    end

    subgraph "Care Coordination Platform (Dockerized)"
        MainAPI["Main API Service<br/>Port 8090<br/>(app/main.py)"]
        AgentRuntime["Agent Runtime Service<br/>Port 8091<br/>(app/agent_runtime.py)"]
        MCPGateway["MCP Gateway Service<br/>Port 8092<br/>(app/mcp_gateway.py)"]
        VectorDB[("ChromaDB<br/>Persistent Store")]
    end

    subgraph "External Dependencies"
        LLMAPI[("Anthropic Claude API")]
    end

    UI -->|"POST /api/v1/capability-router<br/>(JSON-RPC 2.0)"| MainAPI
    MainAPI -->|"POST /api/v1/agents/{capability}/invoke"| AgentRuntime
    AgentRuntime -->|"POST /api/v1/mcp/call<br/>(RBAC enforced)"| MCPGateway
    MCPGateway -->|"query/rebuild"| VectorDB
    AgentRuntime -->|"call_llm_json()"| LLMAPI
```

### 1.3 Business Capability Mapping

| Business Capability | Technical Component | AI Technique |
|---|---|---|
| Diagnosis-to-specialty mapping | `infer_specialties` node | LLM (Claude) with JSON-constrained output, validated against known specialty taxonomy |
| Provider discovery | `fetch_candidates` node | RAG (ChromaDB semantic search over hashed embeddings) |
| Insurance eligibility check | `check_provider_in_network` | Deterministic lookup (payer network JSON) |
| Multi-factor ranking | `score_provider_with_breakdown` | Weighted scoring, urgency-adaptive |
| Rationale generation | `build_recommendation_rationale_llm_assisted` | LLM natural-language generation |
| Alternative suggestion | `alternative_provider_graph.py` | Same pipeline, re-ranked with window filter |
| Governance / audit | `decision_trace` in every response | Rule-based escalation flags |

---

## 2. Low-Level Design (LLD)

### 2.1 Full Component & Data Flow Diagram

```mermaid
flowchart TD
    subgraph UI["UI Layer — ui/"]
        Form["Intake Form\n(diagnosis, location, insurance,\nurgency, preferred window)"]
        Chat["Conversational Query Box"]
        Cards["Recommendation Workbench\n(cards, badges, audit panel)"]
    end

    Form -->|"generateBtn click"| BuildPayload["updateRequestContext()\n+ windowMap lookup"]
    Chat -->|"askBtn click"| BuildPayload
    BuildPayload --> JsonRpc["sendJsonRpc('capability.route', params)"]

    JsonRpc -->|"HTTP POST\n/api/v1/capability-router"| MainAPI

    subgraph MainAPI["app/main.py — Port 8090"]
        Endpoint1["/api/v1/recommend-specialists\n(direct REST)"]
        Endpoint2["/api/v1/capability-router\n(JSON-RPC dispatcher)"]
    end

    Endpoint2 --> Entrypoint

    subgraph Entrypoint["app/agents/capability_entrypoint.py"]
        Handle["handle_jsonrpc_request()"]
        Select["_select_capability()\nexplicit param OR\nLLM/heuristic query routing"]
        Cards2["_AGENT_CARDS registry\n(AgentCard dataclass:\nid, capability, contract,\nrbac_role, mcp_tools)"]
        Invoke["_invoke_agent_http()"]
        Handle --> Select --> Cards2 --> Invoke
    end

    Invoke -->|"HTTP POST\n/api/v1/agents/{capability}/invoke"| AgentRuntime

    subgraph AgentRuntime["app/agent_runtime.py — Port 8091"]
        Router["_AGENT_ENDPOINT_HANDLERS\ncapability → function map"]
    end

    Router --> UseCaseAgents

    subgraph UseCaseAgents["app/agents/use_case_agents.py"]
        SRA["specialist_recommendation_agent()"]
        APA["alternative_provider_agent()"]
    end

    SRA --> Graph1
    APA --> Graph2

    subgraph Graph1["specialist_recommendation_graph.py — LangGraph StateGraph"]
        direction TB
        N1["Node: infer_specialties\n→ infer_specialties_llm_assisted()"]
        N2["Node: fetch_candidates\n→ retrieve_candidate_providers()"]
        N3["Node: rank_recommendations\n→ score + insurance check\n+ exceeded_wait_window flag\n+ LLM rationale"]
        N1 --> N2 --> N3
    end

    subgraph Graph2["alternative_provider_graph.py — LangGraph StateGraph"]
        direction TB
        M1["Node: infer_specialties"]
        M2["Node: fetch_alternatives\n(excludes original provider_id)"]
        M3["Node: rank_alternatives\n(sort: in-window first, then score)"]
        M1 --> M2 --> M3
    end

    N1 -.->|LLM call| LLMGateway
    N3 -.->|LLM call| LLMGateway
    M1 -.->|LLM call| LLMGateway
    M3 -.->|LLM call| LLMGateway

    subgraph LLMGateway["app/agents/llm_gateway.py"]
        CallLLM["call_llm_json()\nAnthropic Messages API\nstrict JSON parsing"]
    end

    N2 -->|"MCP client call"| MCPClient
    N3 -->|"MCP client call"| MCPClient
    M2 -->|"MCP client call"| MCPClient
    M3 -->|"MCP client call"| MCPClient

    subgraph MCPClient["app/mcp_clients/specialist_recommendation_client.py"]
        ClientCall["_call_tool_http()\nadds caller_role +\ninternal_key to payload"]
    end

    ClientCall -->|"HTTP POST\n/api/v1/mcp/call"| MCPGateway

    subgraph MCPGateway["app/mcp_gateway.py + mcp_server/ — Port 8092"]
        HttpGw["http_gateway.py\ncall_tool_http()"]
        Auth["server.py\n_authorize_tool_call()\nRBAC via USE_CASE_TOOL_MAP"]
        Tools["tools.py\ndiagnosis_to_specialty()\nprovider_candidates()\ninsurance_eligibility()"]
        HttpGw --> Auth --> Tools
    end

    Tools -->|"query()"| RAG

    subgraph RAG["app/rag/provider_index.py"]
        ChromaQuery["ChromaDB.query()\nHashEmbeddingFunction"]
    end

    Tools -->|"load_json()"| StaticData

    subgraph StaticData["data/"]
        D1["providers.json"]
        D2["diagnosis_specialties.json"]
        D3["insurance_networks.json"]
    end

    N3 --> Response["Aggregated Response:\nrecommendations[]\ndecision_trace{}"]
    M3 --> Response2["Aggregated Response:\nalternatives[]\ndecision_trace{}"]

    Response --> Cards
    Response2 --> Cards
```

### 2.2 Class / Module Structure

```mermaid
classDiagram
    class AgentCard {
        +agent_id: str
        +capability: str
        +display_name: str
        +description: str
        +input_contract: dict
        +rbac_role: str
        +mcp_tools: list~str~
    }

    class SpecialistRecommendationState {
        <<TypedDict>>
        +diagnosis: str
        +location: str
        +insurance_plan: str
        +urgency: str
        +preferred_window_days: int
        +inferred_specialties: list
        +candidates: list
        +recommendations: list
        +tools_invoked: list
        +mcp_client: SpecialistRecommendationMCPClient
    }

    class AlternativeProviderState {
        <<TypedDict>>
        +excluded_provider_id: str
        +preferred_window_days: int
        +urgency: str
        +alternatives: list
        +tools_invoked: list
    }

    class SpecialistRecommendationMCPClient {
        -caller_role: str
        -internal_key: str
        -http_base_url: str
        +diagnosis_to_specialty(diagnosis) list
        +provider_candidates(diagnosis, location) list
        +insurance_eligibility(provider_id, plan) bool
        -_call_tool_http(name, payload) Any
    }

    class ProviderIndex {
        -client: chromadb.PersistentClient
        -collection: Collection
        +rebuild() void
        +query(text, top_k) list
    }

    AgentCard --> SpecialistRecommendationState : routes to
    SpecialistRecommendationState --> SpecialistRecommendationMCPClient : uses
    AlternativeProviderState --> SpecialistRecommendationMCPClient : uses
    SpecialistRecommendationMCPClient --> ProviderIndex : queries via MCP tool
```

---

## 3. End-to-End Sequence Diagram

### 3.1 Primary Flow: Specialist Recommendation

```mermaid
sequenceDiagram
    autonumber
    participant U as User (Browser)
    participant UI as ui/app.js
    participant API as Main API :8090
    participant CE as capability_entrypoint.py
    participant AR as agent_runtime.py :8091
    participant UC as use_case_agents.py
    participant LG as LangGraph Pipeline
    participant LLM as Anthropic LLM
    participant MC as MCP Client
    participant MG as MCP Gateway :8092
    participant RAG as ChromaDB

    U->>UI: Fill intake form, click "Generate"
    UI->>UI: updateRequestContext()\nmap preferredWindow → days
    UI->>API: POST /api/v1/capability-router\n{capability, payload}
    API->>CE: handle_jsonrpc_request(request)
    CE->>CE: _select_capability()\n(explicit capability provided)
    CE->>AR: HTTP POST /api/v1/agents/\nspecialist_recommendation/invoke
    AR->>UC: specialist_recommendation_agent(payload)
    UC->>LG: run_specialist_recommendation_flow(...)

    LG->>LG: Node 1: infer_specialties
    LG->>LLM: call_llm_json(diagnosis)
    LLM-->>LG: {"specialties": ["Cardiology"]}

    LG->>LG: Node 2: fetch_candidates
    LG->>MC: retrieve_candidate_providers()
    MC->>MG: POST /api/v1/mcp/call\n{tool: provider_candidates, caller_role, internal_key}
    MG->>MG: _authorize_tool_call()\n(RBAC check)
    MG->>RAG: collection.query(text)
    RAG-->>MG: matching providers
    MG-->>MC: {"result": [providers]}
    MC-->>LG: candidates list

    LG->>LG: Node 3: rank_recommendations
    loop for each candidate
        LG->>MC: check_provider_in_network()
        MC->>MG: POST /api/v1/mcp/call\n{tool: insurance_eligibility}
        MG-->>MC: true/false
        LG->>LG: score_provider_with_breakdown()\n(urgency-weighted)
        LG->>LG: exceeded_wait_window check
        LG->>LLM: build_recommendation_rationale_llm_assisted()
        LLM-->>LG: rationale text
    end

    LG-->>UC: {recommendations, decision_trace}
    UC-->>AR: result dict
    AR-->>CE: JSON response
    CE-->>API: {selected_capability, agent_result}
    API-->>UI: JSON-RPC response
    UI->>UI: renderRecommendationWorkspace()\nrenderAuditPanel()
    UI-->>U: Display ranked cards + audit trace
```

### 3.2 Secondary Flow: Alternative Provider Suggestion

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant UI as ui/app.js
    participant API as Main API :8090
    participant AR as Agent Runtime :8091
    participant LG as alternative_provider_graph.py
    participant MG as MCP Gateway :8092

    Note over U,UI: Triggered when a recommended provider\nexceeds preferred_window_days
    U->>UI: Request alternatives for excluded_provider_id
    UI->>API: capability.route\n{capability: alternative_provider_suggestion}
    API->>AR: invoke alternative_provider_agent
    AR->>LG: run_alternative_provider_flow(...)
    LG->>LG: infer_specialties
    LG->>LG: fetch_alternatives\n(exclude original provider)
    LG->>MG: provider_candidates, insurance_eligibility
    LG->>LG: rank_alternatives\nsort: within_window first, then score
    LG-->>AR: {alternatives[], in_window_count, decision_trace}
    AR-->>API: result
    API-->>UI: response
    UI-->>U: Show alternatives with\n"within window" vs "exceeds window" badges
```

---

## 4. Component Responsibilities

| Layer | File | Responsibility |
|---|---|---|
| **Presentation** | `ui/index.html`, `ui/app.js`, `ui/styles.css` | Intake form, chat box, recommendation workbench, audit/override panels |
| **API Gateway** | `app/main.py` | FastAPI app; exposes REST + JSON-RPC endpoints; serves static UI; CORS |
| **Capability Routing** | `app/agents/capability_entrypoint.py` | Agent card registry (self-describing capabilities); JSON-RPC 2.0 handler; HTTP forwarding to Agent Runtime |
| **Intent Inference** | `app/agents/capability_router.py` | LLM-based (`infer_query_with_llm`) + keyword heuristic fallback for free-text routing |
| **Agent Runtime** | `app/agent_runtime.py` | Standalone FastAPI service; dispatches `{capability}` to registered handler function |
| **Use-Case Agents** | `app/agents/use_case_agents.py` | Thin validation + adapter layer between HTTP payload and LangGraph flow functions |
| **Orchestration** | `app/agents/specialist_recommendation_graph.py`, `alternative_provider_graph.py` | LangGraph `StateGraph` — typed state, sequential nodes, deterministic edges |
| **LLM Gateway** | `app/agents/llm_gateway.py` | Wraps Anthropic Messages API; strict JSON extraction; env-driven config |
| **MCP Client** | `app/mcp_clients/specialist_recommendation_client.py` | Blocking HTTP client; injects `caller_role` + `internal_key`; raises `MCPClientError` |
| **MCP Gateway** | `app/mcp_gateway.py`, `app/mcp_server/http_gateway.py` | Single HTTP entrypoint `/api/v1/mcp/call`; delegates to `server.py` authorization + `tools.py` execution |
| **RBAC Enforcement** | `app/mcp_server/server.py` (`_authorize_tool_call`, `USE_CASE_TOOL_MAP`) | Validates `internal_key` secret + role-to-tool whitelist before any tool executes |
| **Tool Implementations** | `app/mcp_server/tools.py` | `map_diagnosis_to_specialties`, `retrieve_candidate_providers`, `check_provider_in_network`, `score_provider_with_breakdown`, rationale generators |
| **RAG Index** | `app/rag/provider_index.py`, `app/rag/embeddings.py` | ChromaDB persistent collection; rebuilt from `providers.json` at startup; hash-based embedding function (no external embedding API dependency) |
| **Static Data** | `data/*.json` | Mocked EHR/payer/provider-directory data acting as system-of-record stand-ins |

---

## 5. Data Model & Contracts

### 5.1 Request Contract — Specialist Recommendation

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "capability.route",
  "params": {
    "capability": "specialist_recommendation",
    "payload": {
      "diagnosis": "chest pain",
      "location": "Austin, TX",
      "insurance_plan": "Aetna",
      "max_results": 5,
      "urgency": "Priority",
      "preferred_window_days": 7
    }
  }
}
```

### 5.2 Response Contract

```json
{
  "result": {
    "selected_capability": "specialist_recommendation",
    "selected_agent_card": { "agent_id": "agent.specialist_recommendation.v1", "...": "..." },
    "agent_transport": "http",
    "agent_result": {
      "request_id": "uuid",
      "generated_at": "2026-08-02T10:00:00Z",
      "inferred_specialties": ["Cardiology"],
      "recommendations": [
        {
          "provider_id": "P001",
          "provider_name": "Dr. Jane Doe",
          "specialty": "Cardiology",
          "location": "Austin, TX",
          "accepts_insurance": true,
          "next_available_date": "2026-08-05",
          "score": 0.87,
          "score_breakdown": {
            "specialty_component": 0.40,
            "location_component": 0.20,
            "insurance_component": 0.20,
            "wait_time_component": 0.17,
            "urgency": "Priority"
          },
          "rationale": "Specialty match, in-network, earliest availability.",
          "exceeded_wait_window": false
        }
      ],
      "missing_information": [],
      "llm_used": true,
      "decision_trace": {
        "capability": "specialist_recommendation",
        "caller_role": "specialist_recommendation",
        "mcp_enabled": true,
        "tools_invoked": ["provider_candidates", "insurance_eligibility"],
        "human_review_required": false
      }
    }
  }
}
```

### 5.3 MCP Tool Call Contract (internal)

```json
{
  "tool_name": "provider_candidates",
  "arguments": {
    "diagnosis": "chest pain",
    "location": "Austin, TX",
    "max_candidates": 12,
    "caller_role": "specialist_recommendation",
    "internal_key": "***"
  }
}
```

---

## 6. Scoring Algorithm Detail

### 6.1 Urgency-Adjusted Weight Table

| Urgency | Specialty Match | Location Match | Insurance Match | Wait-Time (max) | Wait Decay/day |
|---|---|---|---|---|---|
| Routine | 45% | 25% | 20% | 10% | 0.010 |
| Priority | 40% | 20% | 20% | 20% | 0.020 |
| Urgent | 35% | 15% | 15% | 35% | 0.035 |

**Formula:**

```
score = (w_specialty  if specialty matches      else 0)
      + (w_location   if location matches        else 0)
      + (w_insurance   if provider is in-network   else 0)
      + max(0, w_wait - d * decay)
```

where `d` = days until next available appointment, and the `w_*` / `decay` values come from the table above based on the case's urgency.

### 6.2 Human Review Escalation Rules

```mermaid
flowchart TD
    Start([Recommendations Ranked]) --> Q1{Urgency == Urgent?}
    Q1 -->|Yes| Escalate[human_review_required = true]
    Q1 -->|No| Q2{Any score < 0.65?}
    Q2 -->|Yes| Escalate
    Q2 -->|No| Q3{Urgency in Priority/Urgent\nAND all exceed window?}
    Q3 -->|Yes| Escalate
    Q3 -->|No| NoReview[human_review_required = false]
```

---

## 7. Security & Governance

| Control | Mechanism |
|---|---|
| **MCP Authentication** | Shared secret `MCP_INTERNAL_KEY` validated on every tool call in `_authorize_tool_call()` |
| **RBAC** | `USE_CASE_TOOL_MAP` — each `caller_role` whitelisted to specific tool names only |
| **Least Privilege** | `specialist_recommendation` role cannot invoke tools outside its declared `mcp_tools` list on its `AgentCard` |
| **Auditability** | Every response carries `decision_trace` (capability, role, tools invoked, escalation flag) |
| **Human-in-the-loop** | `human_review_required` flag surfaced in UI's Governance & Audit panel; override reason captured in `overrideLog` |
| **Secrets Management** | `.env` file (gitignored) holds `LLM_API_KEY`, `MCP_INTERNAL_KEY`; never hardcoded |
| **CORS** | Restricted to configured frontend origins in `app/main.py` |

---

## 8. Deployment View

```mermaid
graph TB
    subgraph Docker Host
        subgraph Container1["Container: main-api"]
            M["uvicorn app.main:app\n:8090"]
        end
        subgraph Container2["Container: agent-runtime"]
            A["uvicorn app.agent_runtime:app\n:8091"]
        end
        subgraph Container3["Container: mcp-gateway"]
            G["uvicorn app.mcp_gateway:app\n:8092"]
        end
        Vol[("Volume: chroma_data/")]
    end

    Browser["Browser"] -->|":8090"| M
    M -->|"internal DNS: agent-runtime:8091"| A
    A -->|"internal DNS: mcp-gateway:8092"| G
    G --> Vol
    A -.->|"HTTPS"| Anthropic[("Anthropic API")]
```

All three containers run on the same Docker host and share the `chroma_data/` volume mounted into the `mcp-gateway` container.

**Environment variables required (per service, via `.env` or `docker compose env_file`):**
```
LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
MCP_INTERNAL_KEY, MCP_TRANSPORT, MCP_HTTP_BASE_URL
AGENT_RUNTIME_BASE_URL
USE_MCP_TOOLS
```

> Inside Docker, `MCP_HTTP_BASE_URL` and `AGENT_RUNTIME_BASE_URL` must use **service names** (e.g. `http://mcp-gateway:8092`), not `127.0.0.1`.

---

## Summary

The solution follows a **3-tier microservice architecture** (Main API → Agent Runtime → MCP Gateway) with a **LangGraph-orchestrated agentic core** for reasoning, a **RAG layer** (ChromaDB) for semantic provider search, and an **LLM gateway** for diagnosis inference and natural-language rationale generation. Governance is enforced via **RBAC-gated MCP tool access** and every transaction produces an **auditable decision trace** with rule-based **human-in-the-loop escalation**.
