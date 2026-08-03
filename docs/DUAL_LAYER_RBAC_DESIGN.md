# Dual-Layer RBAC Architecture

## Problem Statement

**Before Fix:** The conversational assistant was making decisions and suggesting actions (like "call Aetna") instead of just routing queries. This happened because:

1. RBAC was only checked at the **capability level** (e.g., "specialist_recommendation can use these 3 tools")
2. But **end-user permissions were ignored** (e.g., "this patient shouldn't access insurance_eligibility")
3. The conversational assistant could fall back on its own LLM reasoning instead of routing

**Result:** Questions that shouldn't work for a user role would appear to work (but without real data), creating false confidence and confusion.

---

## Solution: Dual-Layer RBAC

All MCP tool calls now pass through **TWO authorization layers**:

```
User Query
    ↓
Capability Routing (capability_entrypoint.py)
    - Checks: Can this END-USER role use this capability?
    - Uses: ROLE_CAPABILITY_MAP (already existed)
    ↓
Agent/Capability Invocation
    - Passes: user_role from session
    ↓
MCP Tool Call
    - Layer 1: Can this USER_ROLE access this TOOL? ✅ NEW
    - Layer 2: Can this CAPABILITY access this TOOL? (existing)
    - BOTH must pass
```

---

## Layer 1: USER_ROLE_TOOL_MAP (New)

Defines what each **end-user role** can access via MCP:

```python
USER_ROLE_TOOL_MAP: dict[str, set[str]] = {
    "patient": {
        "diagnosis_to_specialty",      # Can ask "what specialists for broken ankle?"
        "provider_candidates",          # Can search for providers
        # EXCLUDED: "insurance_eligibility" - patients can't see coverage details
    },
    "provider": {
        "diagnosis_to_specialty",       # Can assess patient conditions
        "provider_candidates",          # Can search for specialists to refer to
        "insurance_eligibility",        # Can check if specialists are in-network
    },
    "care_agent": {
        "diagnosis_to_specialty",
        "provider_candidates",
        "insurance_eligibility",
    },
}
```

## Layer 2: USE_CASE_TOOL_MAP (Existing)

Defines what each **capability/service** can invoke:

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
        # Missing: insurance_eligibility
    },
    # ... other capabilities
}
```

---

## Authorization Flow

When a **patient** asks: "Find me orthopedists in Dallas with Aetna"

```
1. Capability Routing:
   - Query detected as "specialist_recommendation"
   - Check: patient role allowed for specialist_recommendation? ✅ YES

2. Agent Invocation:
   - run_specialist_recommendation_flow(user_role="patient")
   - Creates MCP client with user_role="patient"

3. MCP Tool Calls:

   diagnosis_to_specialty("broken ankle"):
   - Layer 1: patient role allowed? ✅ YES (in USER_ROLE_TOOL_MAP)
   - Layer 2: specialist_recommendation allowed? ✅ YES (in USE_CASE_TOOL_MAP)
   - Result: ✅ ALLOWED

   provider_candidates(...):
   - Layer 1: patient role allowed? ✅ YES
   - Layer 2: specialist_recommendation allowed? ✅ YES
   - Result: ✅ ALLOWED

   insurance_eligibility(...):
   - Layer 1: patient role allowed? ❌ NO (NOT in USER_ROLE_TOOL_MAP)
   - Result: ❌ REJECTED - "User role 'patient' is not permitted to access tool 'insurance_eligibility'"
```

---

## When Layer 1 Violations Happen

### Scenario 1: Patient asks for insurance eligibility
```
Patient: "Is Dr. Johnson in my Aetna network?"
→ Routes to: insurance_validation
→ Tries insurance_eligibility(provider_id="P1001", insurance_plan="Aetna")
→ Layer 1 check: patient role allowed? ❌ NO
→ Error: "User role 'patient' is not permitted to access tool 'insurance_eligibility'"
```

### Scenario 2: Patient tries to use provider discovery with insurance check
```
Patient: "Find orthopedists in Dallas that accept Aetna"
→ Routes to: provider_discovery (narrower capability)
→ Specialist recommendation would work, but provider_discovery is chosen
→ Tries provider_candidates(...) then insurance_eligibility(...)
→ Layer 2 check: provider_discovery allowed for insurance_eligibility? ❌ NO
→ Error: "Capability 'provider_discovery' is not allowed for tool 'insurance_eligibility'"
```

---

## Code Changes

### 1. MCP Server (app/mcp_server/server.py)

**Added USER_ROLE_TOOL_MAP:**
```python
USER_ROLE_TOOL_MAP: dict[str, set[str]] = {
    "patient": {...},
    "provider": {...},
    "care_agent": {...},
}
```

**Updated _authorize_tool_call():**
```python
def _authorize_tool_call(
    tool_name: str,
    caller_role: str,        # capability role (specialist_recommendation, etc.)
    internal_key: str,
    user_role: str | None = None,  # NEW: end-user role (patient, provider, etc.)
) -> None:
    # Layer 1: Check user role (if provided)
    if user_role:
        if tool_name not in USER_ROLE_TOOL_MAP[user_role]:
            raise PermissionError(f"User role '{user_role}' not permitted for '{tool_name}'")

    # Layer 2: Check capability role (always)
    if tool_name not in USE_CASE_TOOL_MAP[caller_role]:
        raise PermissionError(f"Capability '{caller_role}' not allowed for '{tool_name}'")
```

**Updated tool signatures:**
```python
@mcp.tool()
def diagnosis_to_specialty(
    diagnosis: str,
    internal_key: str,
    caller_role: str,
    user_role: str | None = None,  # NEW: optional user role
) -> list[str]:
    _authorize_tool_call("diagnosis_to_specialty", caller_role, internal_key, user_role=user_role)
    return map_diagnosis_to_specialties(diagnosis)
```

### 2. MCP Client (app/mcp_clients/specialist_recommendation_client.py)

**Updated constructor:**
```python
def __init__(self, caller_role: str, user_role: str | None = None) -> None:
    self._caller_role = caller_role
    self._user_role = user_role  # NEW
```

**Updated _call_tool():**
```python
def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
    payload = {
        **arguments,
        "caller_role": self._caller_role,
        "internal_key": self._internal_key,
    }
    if self._user_role:  # NEW: pass user role to MCP server
        payload["user_role"] = self._user_role
    return self._call_tool_http(name, payload)
```

### 3. Specialist Recommendation Graph (app/agents/specialist_recommendation_graph.py)

**Added user_role parameter:**
```python
def run_specialist_recommendation_flow(
    diagnosis: str,
    location: str,
    insurance_plan: str,
    max_results: int,
    urgency: str = "Routine",
    preferred_window_days: int = 7,
    progress_callback: Callable[[str], None] | None = None,
    user_role: str | None = None,  # NEW: end-user role for RBAC
) -> dict[str, Any]:
    # Pass user_role to MCP client
    with SpecialistRecommendationMCPClient(
        caller_role=SPECIALIST_RECOMMENDATION_ROLE,
        user_role=user_role,  # NEW
    ) as mcp_client:
        ...
```

### 4. API Endpoint (app/main.py)

**Extract user role from session:**
```python
@app.post("/api/v1/recommend-specialists", response_model=RecommendationResponse)
def recommend_specialists(
    request: RecommendationRequest,
    x_session_token: str | None = Header(default=None, alias="X-Session-Token"),
) -> RecommendationResponse:
    session = get_session(x_session_token)
    user_role = session.role if session else None  # NEW: extract from token

    result = run_specialist_recommendation_flow(
        diagnosis=request.diagnosis,
        location=request.location,
        insurance_plan=request.insurance_plan,
        max_results=request.max_results,
        urgency=request.urgency,
        preferred_window_days=request.preferred_window_days,
        user_role=user_role,  # NEW: pass to flow
    )
```

---

## Testing

### Patients CAN do:
```
✅ "Find orthopedic specialists in Dallas for my broken ankle"
   - Uses: diagnosis_to_specialty, provider_candidates
   - Does NOT use: insurance_eligibility

✅ "Recommend cardiologists in Austin"
   - Uses: diagnosis_to_specialty, provider_candidates

✅ "Show me available providers in Houston"
   - Uses: provider_candidates
```

### Patients CANNOT do:
```
❌ "Is Dr. Smith in my Aetna network?"
   - Needs: insurance_eligibility
   - Layer 1 blocks: "User role 'patient' not permitted"

❌ "Find orthopedists with Aetna coverage"
   - Needs: insurance_eligibility
   - Query routes to specialist_recommendation
   - But insurance_eligibility layer 1 check fails
```

### Providers CAN do everything:
```
✅ "Find orthopedists with Aetna coverage"
   - Uses all 3 tools
   - Both layers pass
```

---

## Benefits

1. **Clear separation of concerns:** User permissions ≠ capability permissions
2. **Enforced at tool level:** Can't be bypassed by clever routing or LLM tricks
3. **Deterministic failures:** Users get explicit "not permitted" instead of silent failures or made-up answers
4. **Role-based access:** Each user type has appropriate permissions
5. **Audit trail:** Violations logged with exact role and tool name

---

## Migration Notes

### For API Clients

The `/api/v1/recommend-specialists` endpoint now **requires** the `X-Session-Token` header:

```bash
# Before (worked for unauthenticated):
curl -X POST http://localhost:8090/api/v1/recommend-specialists \
  -d '{"diagnosis": "broken ankle", "location": "Dallas", ...}'

# After (requires authentication):
curl -X POST http://localhost:8090/api/v1/recommend-specialists \
  -H "X-Session-Token: $TOKEN" \
  -d '{"diagnosis": "broken ankle", "location": "Dallas", ...}'
```

### For Custom MCP Clients

If you build custom MCP clients, pass `user_role` to enable user-level RBAC:

```python
# Before:
with SpecialistRecommendationMCPClient(caller_role="specialist_recommendation") as client:
    client.diagnosis_to_specialty("broken ankle")

# After (with user RBAC):
with SpecialistRecommendationMCPClient(
    caller_role="specialist_recommendation",
    user_role="patient"  # NOW: pass end-user role
) as client:
    client.diagnosis_to_specialty("broken ankle")
```

---

## Future Work

1. **Add user_role to other agents:** Insurance validation, referral triage, etc.
2. **Log authorization violations:** Track failed access attempts
3. **Role-based response filtering:** Show different details based on user role
4. **Granular permissions:** More fine-grained than tool-level (e.g., "can only see in-network providers")
5. **Admin console:** Dashboard showing user permissions and violations
