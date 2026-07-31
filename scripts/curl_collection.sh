#!/usr/bin/env bash
set -euo pipefail

BACKEND_BASE_URL="${BACKEND_BASE_URL:-http://127.0.0.1:8090}"
AGENT_BASE_URL="${AGENT_BASE_URL:-http://127.0.0.1:8091}"
MCP_BASE_URL="${MCP_BASE_URL:-http://127.0.0.1:8092}"
MCP_INTERNAL_KEY="${MCP_INTERNAL_KEY:-capstone-internal-key}"

PASS_COUNT=0
FAIL_COUNT=0

print_header() {
  echo
  echo "==== $1 ===="
}

request_json() {
  local method="$1"
  local url="$2"
  local body="$3"
  local expected_status="$4"
  local label="$5"

  local tmp_file
  tmp_file="$(mktemp)"

  local status
  status=$(curl -sS -o "$tmp_file" -w "%{http_code}" -X "$method" "$url" \
    -H "Content-Type: application/json" \
    -d "$body") || status="000"

  if [[ "$status" == "$expected_status" ]]; then
    echo "PASS [$label] status=$status"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "FAIL [$label] expected=$expected_status actual=$status"
    echo "Response:"
    cat "$tmp_file"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi

  rm -f "$tmp_file"
}

print_header "Health Checks"
request_json "GET" "$BACKEND_BASE_URL/health" "{}" "200" "backend health"
request_json "GET" "$AGENT_BASE_URL/health" "{}" "200" "agent runtime health"
request_json "GET" "$MCP_BASE_URL/health" "{}" "200" "mcp gateway health"

print_header "JSON-RPC Entry"
request_json "POST" "$BACKEND_BASE_URL/api/v1/capability-router" '{"jsonrpc":"2.0","id":"cards-1","method":"agents.cards","params":{}}' "200" "agents.cards"
request_json "POST" "$BACKEND_BASE_URL/api/v1/capability-router" '{"jsonrpc":"2.0","id":"route-1","method":"capability.route","params":{"query":"Recommend specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna","payload":{"max_results":3}}}' "200" "rpc route query"
request_json "POST" "$BACKEND_BASE_URL/api/v1/capability-router" '{"jsonrpc":"1.0","id":"bad-1","method":"agents.cards","params":{}}' "200" "rpc invalid version"

print_header "Agent Runtime Direct"
request_json "POST" "$AGENT_BASE_URL/api/v1/agents/specialist_recommendation/invoke" '{"diagnosis":"chest pain","location":"Austin, TX","insurance_plan":"Aetna","max_results":3}' "200" "agent specialist_recommendation"
request_json "POST" "$AGENT_BASE_URL/api/v1/agents/referral_triage/invoke" '{"diagnosis":"persistent chest pain"}' "200" "agent referral_triage"
request_json "POST" "$AGENT_BASE_URL/api/v1/agents/provider_discovery/invoke" '{"diagnosis":"chest pain","location":"Austin, TX","max_results":3}' "200" "agent provider_discovery"
request_json "POST" "$AGENT_BASE_URL/api/v1/agents/insurance_validation/invoke" '{"provider_id":"P-100","insurance_plan":"Aetna"}' "200" "agent insurance_validation"

print_header "MCP Gateway + RBAC"
request_json "POST" "$MCP_BASE_URL/api/v1/mcp/call" '{"tool_name":"diagnosis_to_specialty","arguments":{"diagnosis":"chest pain","caller_role":"specialist_recommendation","internal_key":"'"$MCP_INTERNAL_KEY"'"}}' "200" "rbac allow diagnosis_to_specialty"
request_json "POST" "$MCP_BASE_URL/api/v1/mcp/call" '{"tool_name":"provider_candidates","arguments":{"diagnosis":"chest pain","location":"Austin, TX","max_candidates":3,"caller_role":"provider_discovery","internal_key":"'"$MCP_INTERNAL_KEY"'"}}' "200" "rbac allow provider_candidates"
request_json "POST" "$MCP_BASE_URL/api/v1/mcp/call" '{"tool_name":"insurance_eligibility","arguments":{"provider_id":"P-100","insurance_plan":"Aetna","caller_role":"insurance_validation","internal_key":"'"$MCP_INTERNAL_KEY"'"}}' "200" "rbac allow insurance_eligibility"
request_json "POST" "$MCP_BASE_URL/api/v1/mcp/call" '{"tool_name":"diagnosis_to_specialty","arguments":{"diagnosis":"chest pain","caller_role":"specialist_recommendation","internal_key":"wrong-key"}}' "403" "rbac deny wrong key"
request_json "POST" "$MCP_BASE_URL/api/v1/mcp/call" '{"tool_name":"diagnosis_to_specialty","arguments":{"diagnosis":"chest pain","caller_role":"insurance_validation","internal_key":"'"$MCP_INTERNAL_KEY"'"}}' "403" "rbac deny disallowed role"

echo
printf "Completed. PASS=%d FAIL=%d\n" "$PASS_COUNT" "$FAIL_COUNT"
if [[ "$FAIL_COUNT" -gt 0 ]]; then
  exit 1
fi
