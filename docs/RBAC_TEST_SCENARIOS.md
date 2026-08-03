# RBAC Test Scenarios - User Role Enforcement

After the dual-layer RBAC implementation, these scenarios demonstrate how user roles are now enforced at the MCP level.

---

## ✅ SCENARIOS THAT NOW WORK (Layer 1 + Layer 2 Pass)

### Patient Role ✓

**Scenario 1: Patient asks for specialist recommendation**
```
Patient: "I have broken ankle, find me orthopedists in Dallas"

Flow:
1. Query routed to: specialist_recommendation capability
2. User role check: patient allowed for specialist_recommendation? ✅ YES
3. MCP calls:
   - diagnosis_to_specialty("broken ankle")
     * Layer 1: patient can use? ✅ YES
     * Layer 2: specialist_recommendation can use? ✅ YES
     → ALLOWED
   
   - provider_candidates("broken ankle", "Dallas")
     * Layer 1: patient can use? ✅ YES
     * Layer 2: specialist_recommendation can use? ✅ YES
     → ALLOWED
   
   - insurance_eligibility(provider_id, "Aetna")
     * Layer 1: patient can use? ❌ NO ← FAILS HERE
     → BLOCKED
```

**What happens:**
- ❌ Full recommendation FAILS because insurance_eligibility is blocked at Layer 1
- Patient gets error: "User role 'patient' is not permitted to access tool 'insurance_eligibility'"
- This is **correct behavior** - patient shouldn't see coverage details

---

**Scenario 2: Patient discovers providers by specialty name (no diagnosis)**
```
Patient: "Show me cardiologists in Austin"

Flow:
1. Query routed to: provider_discovery capability
2. User role check: patient allowed for provider_discovery? ✅ YES
3. MCP calls:
   - provider_candidates("cardiology", "Austin")
     * Layer 1: patient can use? ✅ YES
     * Layer 2: provider_discovery can use? ✅ YES
     → ALLOWED

Result: ✅ Returns cardiologist list without insurance eligibility
```

---

**Scenario 3: Patient asks about triage (priority level)**
```
Patient: "How urgent is chest pain?"

Flow:
1. Query routed to: referral_triage capability
2. User role check: patient allowed for referral_triage? ✅ YES
3. MCP calls:
   - diagnosis_to_specialty("chest pain")
     * Layer 1: patient can use? ✅ YES
     * Layer 2: referral_triage can use? ✅ YES
     → ALLOWED

Result: ✅ Returns priority assessment (high/medium/low)
```

---

### Provider Role ✓

**Scenario 4: Provider checks if specialist accepts their insurance**
```
Provider: "Is Dr. Johnson (P1001) in BlueCross network?"

Flow:
1. Query routed to: insurance_validation capability
2. User role check: provider allowed for insurance_validation? ✅ YES
3. MCP calls:
   - insurance_eligibility("P1001", "BlueCross")
     * Layer 1: provider can use? ✅ YES
     * Layer 2: insurance_validation can use? ✅ YES
     → ALLOWED

Result: ✅ Returns true/false
```

---

**Scenario 5: Provider recommends specialists with full info**
```
Provider: "Find cardiologists for my patient with heart failure, check Aetna coverage"

Flow:
1. Query routed to: specialist_recommendation capability
2. User role check: provider allowed for specialist_recommendation? ✅ YES
3. MCP calls:
   - diagnosis_to_specialty("heart failure") → ✅ ALLOWED (Layer 1 & 2)
   - provider_candidates(...) → ✅ ALLOWED (Layer 1 & 2)
   - insurance_eligibility(...) → ✅ ALLOWED (Layer 1 & 2)

Result: ✅ Full recommendation with all details
```

---

## ❌ SCENARIOS THAT NOW FAIL (Layer 1 Blocks)

### Patient Role - Blocked at Layer 1

**Scenario 1: Patient tries to check insurance eligibility directly**
```
Patient: "Is Dr. Johnson covered under my Aetna plan?"

Flow:
1. Query routed to: insurance_validation capability
2. User role check: patient allowed for insurance_validation? ✅ YES (capability level)
3. MCP calls:
   - insurance_eligibility("P1001", "Aetna")
     * Layer 1: patient can use? ❌ NO
     * Error: "User role 'patient' is not permitted to access tool 'insurance_eligibility'"

Result: ❌ BLOCKED - Patient cannot check eligibility
```

**Error response:**
```json
{
  "error": {
    "code": -32000,
    "message": "Server error: User role 'patient' is not permitted to access tool 'insurance_eligibility'. This user can only access: diagnosis_to_specialty, provider_candidates"
  }
}
```

---

**Scenario 2: Patient asks for full specialist recommendation but routing detects insurance check**
```
Patient: "Find orthopedists in Dallas that accept my Aetna plan"

Flow:
1. Query interpretation detects: specialist_recommendation capability ✅
2. User role check: patient allowed? ✅ YES (capability level)
3. MCP calls begin:
   - diagnosis_to_specialty("broken ankle") → ✅ ALLOWED
   - provider_candidates(...) → ✅ ALLOWED
   - insurance_eligibility(...) 
     * Layer 1: patient can use? ❌ NO
     * Error: "User role 'patient' is not permitted to access tool 'insurance_eligibility'"

Result: ⚠️  PARTIALLY BLOCKED
- Diagnosis mapped ✅
- Candidates found ✅
- But recommendation fails ❌ because insurance eligibility can't be checked
- Patient gets error instead of result
```

**This is correct behavior:** Patient shouldn't see insurance eligibility directly. Instead, the response should just show available specialists without filtering by insurance.

---

**Scenario 3: Patient tries alternative provider with insurance check**
```
Patient: "Dr. Lee's appointment is too far, find me alternatives accepting Aetna"

Flow:
1. Query routed to: alternative_provider_suggestion capability
2. User role check: patient allowed? ✅ YES (at capability level)
3. MCP calls:
   - diagnosis_to_specialty("broken ankle") → ✅ ALLOWED
   - provider_candidates(...) → ✅ ALLOWED
   - insurance_eligibility(...)
     * Layer 1: patient can use? ❌ NO
     → ❌ BLOCKED

Result: ❌ Full flow fails because insurance_eligibility is layer 1 denied
```

---

## 🔄 SCENARIOS BLOCKED AT LAYER 2 (Capability Mismatch)

These fail because the narrower capability doesn't have the tool, even though user role does.

### Scenario 1: Insurance validation trying to find providers
```
Caller: insurance_validation agent trying to call provider_candidates

Flow:
- Layer 1: provider role can use provider_candidates? ✅ YES
- Layer 2: insurance_validation capability allowed to use? ❌ NO
  * insurance_validation only has: insurance_eligibility
  * Does NOT have: provider_candidates

Error: "Capability 'insurance_validation' is not allowed for tool 'provider_candidates'. This capability can only invoke: insurance_eligibility"
```

---

### Scenario 2: Provider discovery trying to check insurance
```
Caller: provider_discovery agent trying to call insurance_eligibility

Flow:
- Layer 1: provider role can use insurance_eligibility? ✅ YES
- Layer 2: provider_discovery capability allowed to use? ❌ NO
  * provider_discovery only has: provider_candidates
  * Does NOT have: insurance_eligibility

Error: "Capability 'provider_discovery' is not allowed for tool 'insurance_eligibility'. This capability can only invoke: provider_candidates"
```

---

## RBAC Permission Matrix

| User Role | diagnosis_to_specialty | provider_candidates | insurance_eligibility |
|-----------|:---:|:---:|:---:|
| **patient** | ✅ YES | ✅ YES | ❌ NO |
| **provider** | ✅ YES | ✅ YES | ✅ YES |
| **care_agent** | ✅ YES | ✅ YES | ✅ YES |

| Capability | diagnosis_to_specialty | provider_candidates | insurance_eligibility |
|-----------|:---:|:---:|:---:|
| **specialist_recommendation** | ✅ YES | ✅ YES | ✅ YES |
| **referral_triage** | ✅ YES | ✅ YES | ❌ NO |
| **insurance_validation** | ❌ NO | ❌ NO | ✅ YES |
| **provider_discovery** | ❌ NO | ✅ YES | ❌ NO |
| **alternative_provider_suggestion** | ✅ YES | ✅ YES | ✅ YES |
| **conversational_assistant** | ❌ NO | ❌ NO | ❌ NO |

**Auth Success = User role ✅ AND Capability ✅**

---

## Testing These Scenarios

### Via cURL with User Role

```bash
# Test 1: Patient can map diagnosis
curl -X POST http://localhost:8092/api/v1/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "diagnosis_to_specialty",
    "arguments": {
      "diagnosis": "broken ankle",
      "caller_role": "specialist_recommendation",
      "user_role": "patient",
      "internal_key": "your_key"
    }
  }'
# Expected: ✅ SUCCESS (both layers pass)

# Test 2: Patient cannot check insurance
curl -X POST http://localhost:8092/api/v1/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "insurance_eligibility",
    "arguments": {
      "provider_id": "P1001",
      "insurance_plan": "Aetna",
      "caller_role": "specialist_recommendation",
      "user_role": "patient",
      "internal_key": "your_key"
    }
  }'
# Expected: ❌ ERROR - "User role 'patient' is not permitted to access tool 'insurance_eligibility'"

# Test 3: Provider can check insurance
curl -X POST http://localhost:8092/api/v1/mcp/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool_name": "insurance_eligibility",
    "arguments": {
      "provider_id": "P1001",
      "insurance_plan": "Aetna",
      "caller_role": "insurance_validation",
      "user_role": "provider",
      "internal_key": "your_key"
    }
  }'
# Expected: ✅ SUCCESS (both layers pass)
```

---

## Key Takeaways

1. **Dual-layer check is mandatory:** Both user role AND capability role must allow the tool
2. **Patient cannot access insurance_eligibility:** This is intentional - sensitive data protection
3. **Errors are now explicit:** Users know exactly why they're blocked instead of getting confused
4. **Conversational assistant cannot make decisions:** It has NO MCP tool access, must route properly
5. **No fallback answers:** Layer 1 failures are hard-stops, not suggestions for workarounds

---

## Troubleshooting

### Q: Patient query returns "not permitted" but should work?
**A:** Check if the query needs `insurance_eligibility`. Patients can't use it. Route to specialist_recommendation without insurance filtering.

### Q: Provider query fails even though provider role can do everything?
**A:** Check the **capability** role (Layer 2). Even if provider role allows it, the narrow capability might not. Use specialist_recommendation for complex queries.

### Q: Conversational assistant is still trying to route?
**A:** Conversational assistant has zero MCP tools. It MUST pass questions to other capabilities. It cannot invoke any tools directly.

### Q: How do I allow patients to see insurance info?
**A:** Remove `insurance_eligibility` blocking from `USER_ROLE_TOOL_MAP["patient"]`. But this may be a policy decision worth discussing first.
