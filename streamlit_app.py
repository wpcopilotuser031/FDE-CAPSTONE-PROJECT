from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from uuid import uuid4
from urllib import error, request as urlrequest

import streamlit as st

from app.agents.llm_gateway import LLMGatewayError
from app.mcp_clients.specialist_recommendation_client import MCPClientError

st.set_page_config(page_title="Referral Command Center", page_icon="HC", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');

:root {
  --ink: #16212e;
  --slate: #4e5d70;
  --surface: #f7f5f0;
  --panel: #ffffff;
  --line: #d8d6cb;
  --accent: #005f73;
  --accent-soft: #e0f0f3;
  --success: #2f6f4e;
  --warn: #8c4a0f;
}

html, body, [class*="css"] {
  font-family: 'IBM Plex Sans', sans-serif;
  color: var(--ink);
}

.stApp {
  background:
    radial-gradient(circle at 10% 10%, #e8f4f6 0%, transparent 45%),
    radial-gradient(circle at 90% 20%, #f0ece2 0%, transparent 40%),
    var(--surface);
}

.hero {
  border: 1px solid var(--line);
  background: linear-gradient(130deg, #ffffff 0%, #f3f1ea 100%);
  border-radius: 16px;
  padding: 16px 20px;
  margin-bottom: 14px;
}

.hero h1 {
  margin: 0;
  font-family: 'Space Grotesk', sans-serif;
  font-size: 1.6rem;
  letter-spacing: 0.2px;
}

.hero p {
  margin: 6px 0 0;
  color: var(--slate);
}

.panel-title {
  font-family: 'Space Grotesk', sans-serif;
  font-size: 1.05rem;
  margin-bottom: 8px;
}

.metric-chip {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px;
  background: var(--panel);
}

.workbench-card {
  border: 1px solid var(--line);
  border-left: 5px solid var(--accent);
  border-radius: 12px;
  background: var(--panel);
  padding: 12px;
  margin-bottom: 10px;
}

.audit-box {
  border: 1px dashed var(--line);
  border-radius: 12px;
  background: #fff;
  padding: 10px;
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="hero">
  <h1>Intelligent Care Coordination Referral Command Center</h1>
  <p>AI-assisted specialist recommendation with MCP tool governance, audit traceability, and human-in-the-loop controls.</p>
</div>
""",
    unsafe_allow_html=True,
)

def _jsonrpc(method: str, params: dict) -> dict:
    backend_base_url = os.getenv("BACKEND_BASE_URL", "http://127.0.0.1:8090").rstrip("/")
    endpoint = f"{backend_base_url}/api/v1/capability-router"
    request = {
        "jsonrpc": "2.0",
        "id": str(uuid4()),
        "method": method,
        "params": params,
    }
    body = json.dumps(request).encode("utf-8")
    req = urlrequest.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Backend HTTP error: {detail or exc}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Backend HTTP connection failed: {exc}") from exc

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Backend returned non-JSON response for JSON-RPC request.") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("Backend returned invalid JSON-RPC payload.")
    return parsed


if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "override_log" not in st.session_state:
    st.session_state.override_log = []
if "workspace_live_steps" not in st.session_state:
    st.session_state.workspace_live_steps = []
if "last_agent_card" not in st.session_state:
    st.session_state.last_agent_card = None
if "last_selected_capability" not in st.session_state:
    st.session_state.last_selected_capability = None
if "last_non_recommendation_result" not in st.session_state:
    st.session_state.last_non_recommendation_result = None


def _render_workbench(result: dict) -> None:
    recommendations = result.get("recommendations", [])
    if not recommendations:
        st.warning("No recommendations returned for this case.")
        return

    top_scores = [rec.get("score", 0.0) for rec in recommendations]
    avg_score = sum(top_scores) / max(len(top_scores), 1)
    in_network = sum(1 for rec in recommendations if rec.get("accepts_insurance"))

    m1, m2, m3 = st.columns(3)
    m1.markdown(f"<div class='metric-chip'><b>Top Candidates</b><br>{len(recommendations)}</div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='metric-chip'><b>Avg Match Score</b><br>{avg_score:.2f}</div>", unsafe_allow_html=True)
    m3.markdown(f"<div class='metric-chip'><b>In-Network Count</b><br>{in_network}</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-title'>Recommendation Workbench</div>", unsafe_allow_html=True)
    for index, rec in enumerate(recommendations, start=1):
        badge = "In-Network" if rec.get("accepts_insurance") else "Out-of-Network"
        st.markdown(
            (
                f"<div class='workbench-card'><b>#{index} {rec.get('provider_name')}</b>"
                f"<br>{rec.get('specialty')} | {rec.get('location')}"
                f"<br><b>Score:</b> {rec.get('score')} | <b>Status:</b> {badge}"
                f"<br><b>Next Availability:</b> {rec.get('next_available_date')}"
                f"<br><b>Rationale:</b> {rec.get('rationale')}</div>"
            ),
            unsafe_allow_html=True,
        )

        with st.expander(f"Score breakdown #{index}"):
            st.json(rec.get("score_breakdown", {}))

    st.markdown("<div class='panel-title'>Compare Top 3</div>", unsafe_allow_html=True)
    compare = recommendations[:3]
    compare_cols = st.columns(len(compare))
    for idx, rec in enumerate(compare):
        with compare_cols[idx]:
            st.markdown(f"**{rec.get('provider_name')}**")
            st.caption(f"{rec.get('specialty')} | {rec.get('location')}")
            st.write(f"Score: {rec.get('score')}")
            st.write(f"Network: {'Yes' if rec.get('accepts_insurance') else 'No'}")
            st.write(f"Slot: {rec.get('next_available_date')}")


def _render_audit(result: dict) -> None:
    trace = result.get("decision_trace") or {}
    st.markdown("<div class='panel-title'>Governance & Audit</div>", unsafe_allow_html=True)
    st.markdown("<div class='audit-box'>", unsafe_allow_html=True)
    st.write(f"Request ID: {result.get('request_id', '-')}")
    st.write(f"Generated At: {result.get('generated_at', '-')}")
    st.write(f"Capability: {trace.get('capability', '-')}")
    st.write(f"Caller Role: {trace.get('caller_role', '-')}")
    st.write(f"MCP Enabled: {trace.get('mcp_enabled', False)}")
    st.write(f"Tools Invoked: {', '.join(trace.get('tools_invoked', [])) or '-'}")
    st.write(f"Human Review Required: {trace.get('human_review_required', False)}")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='panel-title'>Human Override</div>", unsafe_allow_html=True)
    override_reason = st.text_area("Override reason", placeholder="Explain why coordinator overrides AI recommendation.")
    if st.button("Approve Override"):
        if not override_reason.strip():
            st.warning("Provide an override reason before approval.")
        else:
            st.session_state.override_log.append(
                {
                    "time": datetime.now(UTC).isoformat(),
                    "reason": override_reason.strip(),
                    "request_id": result.get("request_id"),
                }
            )
            st.success("Override logged for audit trail.")

    if st.session_state.override_log:
        with st.expander("Override history"):
            st.json(st.session_state.override_log)


def _run_recommendation(
    capability: str,
    query: str,
    payload: dict,
    workspace_live_placeholder,
) -> None:
    status = st.status("Running agentic workflow...", expanded=True)
    st.session_state.workspace_live_steps = []

    def _progress(step: str) -> None:
        status.write(f"- {step}")
        st.session_state.workspace_live_steps.append(step)
        workspace_live_placeholder.info(
            "Live workflow progress:\n- " + "\n- ".join(st.session_state.workspace_live_steps)
        )

    try:
        _progress("Step 1/5: Creating JSON-RPC request")
        _progress("Step 2/5: Calling Capability Router entrypoint")
        response = _jsonrpc(
            method="capability.route",
            params={
                "capability": capability,
                "query": query,
                "payload": payload,
            },
        )

        if "error" in response:
            raise ValueError(response["error"].get("message", "JSON-RPC routing error"))

        result_payload = response.get("result", {})
        selected_capability = result_payload.get("selected_capability")
        selected_card = result_payload.get("selected_agent_card")
        agent_result = result_payload.get("agent_result", {})

        _progress(f"Step 3/5: Selected capability '{selected_capability}'")
        _progress(
            "Step 4/5: Loaded agent card '"
            + str((selected_card or {}).get("display_name", "Unknown Agent"))
            + "'"
        )
        _progress("Step 5/5: Executing selected agent and backend tools")
    except (LLMGatewayError, MCPClientError, RuntimeError) as exc:
        status.update(label="Workflow failed", state="error", expanded=True)
        st.error(f"Required dependency unavailable or invalid output returned: {exc}")
        return
    except ValueError as exc:
        status.update(label="Workflow failed", state="error", expanded=True)
        st.error(f"Routing error: {exc}")
        return

    status.update(label="Workflow completed", state="complete", expanded=False)
    workspace_live_placeholder.empty()
    st.session_state.last_selected_capability = selected_capability
    st.session_state.last_agent_card = selected_card

    if selected_capability == "specialist_recommendation":
        st.session_state.last_result = agent_result
        st.session_state.last_non_recommendation_result = None
        st.success("Agentic recommendation workflow completed.")
    else:
        st.session_state.last_result = None
        st.session_state.last_non_recommendation_result = agent_result
        st.success(f"Agentic workflow completed for capability: {selected_capability}")

    st.rerun()


left, middle, right = st.columns([1.0, 1.35, 1.0])

with middle:
    st.markdown("<div class='panel-title'>Recommendation Workspace</div>", unsafe_allow_html=True)
    workspace_live_placeholder = st.empty()
    if st.session_state.last_result:
        _render_workbench(st.session_state.last_result)
    elif st.session_state.last_non_recommendation_result:
        st.info(
            "Last routed capability was '"
            + str(st.session_state.last_selected_capability)
            + "'. Showing raw agent output."
        )
        st.json(st.session_state.last_non_recommendation_result)
    else:
        st.info("Submit intake details or ask in chat to trigger agentic routing and populate this workspace.")

with left:
    st.markdown("<div class='panel-title'>Referral Intake</div>", unsafe_allow_html=True)
    patient_id = st.text_input("Patient ID", value=f"PT-{str(uuid4())[:8]}")
    diagnosis = st.text_input("Diagnosis", placeholder="e.g., chest pain")
    location = st.text_input("Preferred Location", placeholder="e.g., Austin, TX")
    insurance_plan = st.selectbox(
        "Insurance Plan",
        options=["Aetna", "BlueCross", "Cigna", "UnitedHealthcare"],
        index=0,
    )
    urgency = st.selectbox("Clinical Urgency", options=["Routine", "Priority", "Urgent"], index=0)
    preferred_window = st.selectbox("Preferred Appointment Window", options=["Within 7 days", "Within 14 days", "Within 30 days"])
    max_results = st.slider("Max Recommendations", min_value=1, max_value=10, value=5)

    st.markdown("<div class='panel-title'>Intake Completeness</div>", unsafe_allow_html=True)
    checks = {
        "Diagnosis captured": bool(diagnosis.strip()),
        "Location captured": bool(location.strip()),
        "Insurance selected": bool(insurance_plan.strip()),
        "Patient ID created": bool(patient_id.strip()),
    }
    for label, status in checks.items():
        st.write(f"{'OK' if status else 'Missing'}  {label}")

    if st.button("Generate Recommendations", type="primary"):
        if not diagnosis or not location:
            st.error("Diagnosis and location are required.")
        else:
            _run_recommendation(
                capability="specialist_recommendation",
                query=(
                    f"Recommend specialist for diagnosis: {diagnosis}, "
                    f"location: {location}, insurance: {insurance_plan}"
                ),
                payload={
                    "diagnosis": diagnosis,
                    "location": location,
                    "insurance_plan": insurance_plan,
                    "max_results": max_results,
                },
                workspace_live_placeholder,
            )

    st.caption(f"Urgency: {urgency} | Preferred window: {preferred_window}")

with right:
    st.markdown("<div class='panel-title'>Conversational Assistant</div>", unsafe_allow_html=True)
    st.write(
        "Ask in natural language. The assistant infers the capability and routes the request. "
        "The capability router selects an agent card and invokes the backend agent."
    )
    st.code(
        "Recommend specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna",
        language="text",
    )

    query = st.text_area("Your query", height=130, placeholder="Type your referral question...")
    max_chat_results = st.slider("Chat Result Limit", min_value=1, max_value=10, value=3)

    if st.button("Ask Assistant"):
        if not query.strip():
            st.error("Please enter a query.")
        else:
            _run_recommendation(
                capability="",
                query=query,
                payload={"max_results": max_chat_results},
                workspace_live_placeholder=workspace_live_placeholder,
            )

    with st.expander("Registered Agent Cards"):
        cards_response = _jsonrpc("agents.cards", {})
        if "error" in cards_response:
            st.error(cards_response["error"].get("message", "Unable to load agent cards"))
        else:
            st.json(cards_response.get("result", {}))

    if st.session_state.last_result:
        _render_audit(st.session_state.last_result)
    elif st.session_state.last_agent_card:
        st.markdown("<div class='panel-title'>Last Routed Agent</div>", unsafe_allow_html=True)
        st.json(st.session_state.last_agent_card)

st.divider()
st.subheader("Capability Roadmap")
roadmap_col1, roadmap_col2, roadmap_col3, roadmap_col4 = st.columns(4)
roadmap_col1.metric("Now Live", "Specialist Recommendation")
roadmap_col2.metric("Next", "Document Gap Detection")
roadmap_col3.metric("Next", "Referral History Summary")
roadmap_col4.metric("Next", "Delay Prediction and Escalation")

st.subheader("Raw Contract Preview")
st.write("The JSON-RPC payload shape used by the capability router:")
st.code(
    json.dumps(
        {
            "jsonrpc": "2.0",
            "id": "req-001",
            "method": "capability.route",
            "params": {
                "query": "Recommend specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna",
                "payload": {
                    "max_results": 3,
                },
            },
        },
        indent=2,
    ),
    language="json",
)
