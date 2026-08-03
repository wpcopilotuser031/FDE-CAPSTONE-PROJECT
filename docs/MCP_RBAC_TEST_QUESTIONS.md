# MCP RBAC Test Questions - What Works vs What Fails

This document lists test questions to validate MCP RBAC enforcement across different capabilities.

---

## ✅ QUESTIONS THAT WILL WORK

### Category 1: Specialist Recommendation (Full MCP Access)
**Capability has:** `diagnosis_to_specialty`, `provider_candidates`, `insurance_eligibility`

| # | Question | MCP Tools Used | Status |
|---|----------|---|--------|
| 1 | "I have chest pain, find me cardiologists in Dallas with Aetna" | All 3 tools | ✅ WORKS |
| 2 | "Recommend orthopedic specialists in Houston accepting BlueCross for my broken ankle" | All 3 tools | ✅ WORKS |
| 3 | "I have diabetes and need endocrinologists in Austin, check my Humana coverage" | All 3 tools | ✅ WORKS |

### Category 2: Alternative Provider Suggestion (Full MCP Access)
**Capability has:** `diagnosis_to_specialty`, `provider_candidates`, `insurance_eligibility`

| # | Question | MCP Tools Used | Status |
|---|----------|---|--------|
| 4 | "Dr. Lee's appointment is 60 days away, find me alternative orthopedists with Aetna in Dallas" | All 3 tools | ✅ WORKS |
| 5 | "Suggest other cardiologists for chest pain if my preferred doctor exceeds 2 weeks" | All 3 tools | ✅ WORKS |

### Category 3: Referral Triage (Limited - No Insurance Tool)
**Capability has:** `diagnosis_to_specialty`, `provider_candidates` | **Missing:** `insurance_eligibility`

| # | Question | MCP Tools Used | Status |
|---|----------|---|--------|
| 6 | "What's the priority level of my chest pain?" | diagnosis_to_specialty only | ✅ WORKS |
| 7 | "Assess urgency of my broken ankle and suggest specialist types" | diagnosis_to_specialty only | ✅ WORKS |

### Category 4: Insurance Validation (Limited - Only Insurance Tool)
**Capability has:** `insurance_eligibility` | **Missing:** `diagnosis_to_specialty`, `provider_candidates`

| # | Question | MCP Tools Used | Status |
|---|----------|---|--------|
| 8 | "Is Dr. Johnson (P1001) covered under my Aetna plan?" | insurance_eligibility only | ✅ WORKS |
| 9 | "Check if provider P1180 accepts BlueCross" | insurance_eligibility only | ✅ WORKS |

### Category 5: Provider Discovery (Limited - No Specialty Mapping)
**Capability has:** `provider_candidates` | **Missing:** `diagnosis_to_specialty`, `insurance_eligibility`

| # | Question | MCP Tools Used | Status |
|---|----------|---|--------|
| 10 | "Show me all orthopedic specialists in Dallas" | provider_candidates only | ✅ WORKS |

---

## ❌ QUESTIONS THAT WILL FAIL (MCP RBAC Violations)

### Category 1: Referral Triage - Missing `insurance_eligibility`
**Capability has:** `diagnosis_to_specialty`, `provider_candidates` | **Missing:** `insurance_eligibility`

| # | Question | Needs Tool | Error | Status |
|---|----------|---|--------|--------|
| 1 | "Triage my chest pain and check which cardiologists accept my Aetna plan" | `insurance_eligibility` | "Role 'referral_triage' is not allowed for tool 'insurance_eligibility'" | ❌ FAILS |
| 2 | "What's the urgency of my broken ankle and which in-network orthopedists can I see?" | `insurance_eligibility` | "Role 'referral_triage' is not allowed for tool 'insurance_eligibility'" | ❌ FAILS |

### Category 2: Insurance Validation - Missing `provider_candidates` & `diagnosis_to_specialty`
**Capability has:** `insurance_eligibility` | **Missing:** `diagnosis_to_specialty`, `provider_candidates`

| # | Question | Needs Tool | Error | Status |
|---|----------|---|--------|--------|
| 3 | "Are there any cardiologists in Dallas with my BlueCross plan?" | `provider_candidates` | "Role 'insurance_validation' is not allowed for tool 'provider_candidates'" | ❌ FAILS |
| 4 | "Find me orthopedic providers and check if they accept Aetna" | `provider_candidates` | "Role 'insurance_validation' is not allowed for tool 'provider_candidates'" | ❌ FAILS |
| 5 | "What specialists treat chest pain and which are in my network?" | `diagnosis_to_specialty` | "Role 'insurance_validation' is not allowed for tool 'diagnosis_to_specialty'" | ❌ FAILS |

### Category 3: Provider Discovery - Missing `diagnosis_to_specialty` & `insurance_eligibility`
**Capability has:** `provider_candidates` | **Missing:** `diagnosis_to_specialty`, `insurance_eligibility`

| # | Question | Needs Tool | Error | Status |
|---|----------|---|--------|--------|
| 6 | "Find me specialists for my broken ankle in Austin" | `diagnosis_to_specialty` | "Role 'provider_discovery' is not allowed for tool 'diagnosis_to_specialty'" | ❌ FAILS |
| 7 | "Search for cardiologists in Dallas and check Aetna coverage" | `insurance_eligibility` | "Role 'provider_discovery' is not allowed for tool 'insurance_eligibility'" | ❌ FAILS |
| 8 | "Find neurologists for my migraine in Houston that accept my plan" | `insurance_eligibility` | "Role 'provider_discovery' is not allowed for tool 'insurance_eligibility'" | ❌ FAILS |

### Category 4: Conversational Assistant - No MCP Tools Allowed
**Capability has:** (NOTHING) | **Missing:** all tools

| # | Question | Needs Tool | Error | Status |
|---|----------|---|--------|--------|
| 9 | "What specialists should I see for chest pain?" | `diagnosis_to_specialty` | "Role 'conversational_assistant' is not allowed for tool 'diagnosis_to_specialty'" | ❌ FAILS |
| 10 | "Find me orthopedic doctors in Dallas" | `provider_candidates` | "Role 'conversational_assistant' is not allowed for tool 'provider_candidates'" | ❌ FAILS |
| 11 | "Is Dr. Smith in my insurance network?" | `insurance_eligibility` | "Role 'conversational_assistant' is not allowed for tool 'insurance_eligibility'" | ❌ FAILS |

---

## Pattern Analysis

### What Works ✅
- **Specialist Recommendation** - Always works (has all 3 tools)
- **Alternative Provider Suggestion** - Always works (has all 3 tools)
- **Single-purpose queries** that match the capability's exact tool set
  - Triage + diagnosis questions
  - Insurance validation + provider ID checks
  - Provider discovery + specialty name queries

### What Fails ❌
- **Referral Triage** trying to check insurance eligibility
- **Insurance Validation** trying to find providers or map diagnoses
- **Provider Discovery** trying to map diagnoses or validate insurance
- **Conversational Assistant** trying to use ANY MCP tool

---

## Current MCP RBAC Configuration

```python
USE_CASE_TOOL_MAP: dict[str, set[str]] = {
    "specialist_recommendation": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
    "referral_triage": {
        "diagnosis_to_specialty",
        "provider_candidates",
        # MISSING: "insurance_eligibility"
    },
    "insurance_validation": {
        "insurance_eligibility",
        # MISSING: "diagnosis_to_specialty", "provider_candidates"
    },
    "provider_discovery": {
        "provider_candidates",
        # MISSING: "diagnosis_to_specialty", "insurance_eligibility"
    },
    "alternative_provider_suggestion": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
    "admin_console": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
    "conversational_assistant": set(),
    # MISSING: all tools
}
```

---

## How to Test These Questions

### Via UI (Recommended)
1. Log in as a user
2. Go to chat mode
3. Copy-paste each question
4. Observe success or failure

### Via API (cURL)
```bash
curl -X POST http://localhost:8090/api/v1/capability-router \
  -H "Content-Type: application/json" \
  -H "X-Session-Token: YOUR_TOKEN" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "capability.route",
    "params": {
      "query": "QUESTION_HERE"
    }
  }'
```

### Expected Success Response
```json
{
  "selected_capability": "specialist_recommendation",
  "routed_capability": "specialist_recommendation",
  "agent_result": {
    "recommendations": [...],
    "llm_used": true,
    "decision_trace": {
      "capability": "specialist_recommendation",
      "mcp_enabled": true,
      "tools_invoked": ["diagnosis_to_specialty", "provider_candidates", "insurance_eligibility"],
      "human_review_required": false
    }
  }
}
```

### Expected Failure Response (MCP RBAC)
```json
{
  "error": {
    "code": -32000,
    "message": "Server error: Role 'referral_triage' is not allowed for tool 'insurance_eligibility'"
  }
}
```

---

## Recommendations for Production

### Option 1: Expand MCP RBAC Permissions
Give more capabilities the tools they logically need:
```python
"referral_triage": {
    "diagnosis_to_specialty",
    "provider_candidates",
    "insurance_eligibility",  # ADD THIS
},
```

### Option 2: Smart Routing
Route complex queries automatically to `specialist_recommendation` when they need multiple tools:
```python
if needs_multiple_tools(query):
    capability = "specialist_recommendation"  # Always has all tools
else:
    capability = infer_narrow_capability(query)
```

### Option 3: Allow Conversational Assistant to Call Specialists
Let conversational_assistant delegate to specialist_recommendation for complex queries:
```python
if query_needs_tools and role_allows(caller_role, "specialist_recommendation"):
    invoke_specialist_recommendation()
```

---

## File Location
- **Original Config:** `app/mcp_server/server.py` (lines with `USE_CASE_TOOL_MAP`)
- **Capability Routing:** `app/agents/capability_entrypoint.py`
- **MCP Authorization:** `app/mcp_server/server.py` (function `_authorize_tool_call`)
