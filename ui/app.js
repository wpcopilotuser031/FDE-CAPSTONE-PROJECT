const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8090';
const BACKEND_BASE_URL = `${DEFAULT_BACKEND_URL}/api/v1`;

const state = {
  patientId: '',
  diagnosis: '',
  location: '',
  insurancePlan: 'Aetna',
  urgency: 'Routine',
  preferredWindow: 'Within 7 days',
  maxResults: 5,
  query: '',
  maxChatResults: 3,
  lastResult: null,
  lastNonRecommendationResult: null,
  lastAgentCard: null,
  lastSelectedCapability: null,
  overrideLog: [],
  workspaceLiveSteps: [],
  agentCards: null,
  dashboardData: null,
  isBusy: false,
};

function uuid() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `id-${Math.random().toString(16).slice(2)}-${Date.now()}`;
}

function hydrateStateFromDom() {
  document.getElementById('patientId').value = state.patientId;
  document.getElementById('diagnosis').value = state.diagnosis;
  document.getElementById('location').value = state.location;
  document.getElementById('insurancePlan').value = state.insurancePlan;
  document.getElementById('urgency').value = state.urgency;
  document.getElementById('preferredWindow').value = state.preferredWindow;
  document.getElementById('maxResults').value = state.maxResults;
  document.getElementById('maxResultsLabel').textContent = state.maxResults;
  document.getElementById('queryInput').value = state.query;
  document.getElementById('maxChatResults').value = state.maxChatResults;
  document.getElementById('maxChatResultsLabel').textContent = state.maxChatResults;
  document.getElementById('backendBaseUrl').value = DEFAULT_BACKEND_URL;
}

function renderToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 3000);
}

function renderIntakeChecks() {
  const checkMap = {
    'Diagnosis captured': Boolean(state.diagnosis.trim()),
    'Location captured': Boolean(state.location.trim()),
    'Insurance selected': Boolean(state.insurancePlan.trim()),
    'Patient ID created': Boolean(state.patientId.trim()),
  };
  const list = document.getElementById('intakeChecks');
  list.innerHTML = Object.entries(checkMap)
    .map(([label, complete]) => `<li>${complete ? '✅' : '⚠️'} ${label}</li>`)
    .join('');

  const caption = document.getElementById('intakeCaption');
  caption.textContent = `Urgency: ${state.urgency} | Preferred window: ${state.preferredWindow}`;
}

function renderProgress() {
  const progress = document.getElementById('workspaceLiveSteps');
  progress.innerHTML = state.workspaceLiveSteps.length
    ? `<div class="panel-subtitle">Live workflow progress</div><ul>${state.workspaceLiveSteps.map(step => `<li>${step}</li>`).join('')}</ul>`
    : '';
}

function renderRecommendationWorkspace() {
  const container = document.getElementById('recommendationContent');
  const status = document.getElementById('workspaceStatus');

  if (state.isBusy) {
    status.textContent = 'Running agentic workflow...';
  } else if (!state.lastResult && !state.lastNonRecommendationResult) {
    status.textContent = 'Submit intake details or ask in chat to trigger agentic routing and populate this workspace.';
  } else {
    status.textContent = '';
  }

  renderProgress();

  if (state.lastResult) {
    const recs = state.lastResult.recommendations || [];
    if (!recs.length) {
      container.innerHTML = '<div class="info-box">No recommendations returned for this case.</div>';
      return;
    }

    const topScores = recs.map(item => Number(item.score || 0));
    const avgScore = topScores.reduce((sum, value) => sum + value, 0) / Math.max(topScores.length, 1);
    const inNetworkCount = recs.filter(item => item.accepts_insurance).length;

    const metrics = `
      <div class="stats-grid" style="margin-bottom: 12px; grid-template-columns: repeat(3, minmax(0, 1fr));">
        <div class="stat-card"><strong>${recs.length}</strong>Top candidates</div>
        <div class="stat-card"><strong>${avgScore.toFixed(2)}</strong>Average match score</div>
        <div class="stat-card"><strong>${inNetworkCount}</strong>In-network matches</div>
      </div>
    `;

    const recommendationCards = recs.map((rec, index) => {
      const badge = rec.accepts_insurance ? 'In-Network' : 'Out-of-Network';
      const waitBadge = rec.exceeded_wait_window ? '<span class="badge-warn">⚠ Exceeds preferred window</span>' : '';
      return `
        <div class="dashboard-card">
          <div class="card-title">#${index + 1} ${rec.provider_name || 'Unknown Provider'}</div>
          ${waitBadge}
          <p>${rec.specialty || 'Unknown specialty'} | ${rec.location || 'Unknown location'}</p>
          <p><strong>Score:</strong> ${rec.score ?? '-'}<br>
          <strong>Next availability:</strong> ${rec.next_available_date || '-'}</p>
          <p>${rec.rationale || ''}</p>
          <details><summary>Score breakdown</summary><pre class="json-box">${JSON.stringify(rec.score_breakdown || {}, null, 2)}</pre></details>
        </div>
      `;
    }).join('');

    container.innerHTML = `
      ${metrics}
      <div class="panel-title">Recommendation Workbench</div>
      <div class="dashboard-grid">${recommendationCards}</div>
    `;
    return;
  }

  if (state.lastNonRecommendationResult) {
    const selected = state.lastSelectedCapability || 'unknown capability';
    container.innerHTML = `
      <div class="info-box">Last routed capability was '<strong>${selected}</strong>'. Showing raw agent output.</div>
      <pre class="json-box">${JSON.stringify(state.lastNonRecommendationResult, null, 2)}</pre>
    `;
    return;
  }

  container.innerHTML = '';
}

function renderAuditPanel() {
  const target = document.getElementById('auditPanel');
  if (!state.lastResult) {
    target.innerHTML = '';
    return;
  }

  const trace = state.lastResult.decision_trace || {};
  target.innerHTML = `
    <div class="panel-section">
      <div class="panel-title">Governance & Audit</div>
      <div class="dashboard-card">
        <div><strong>Request ID:</strong> ${state.lastResult.request_id || '-'}</div>
        <div><strong>Generated At:</strong> ${state.lastResult.generated_at || '-'}</div>
        <div><strong>Capability:</strong> ${trace.capability || '-'}</div>
        <div><strong>Caller Role:</strong> ${trace.caller_role || '-'}</div>
        <div><strong>MCP Enabled:</strong> ${trace.mcp_enabled ?? false}</div>
        <div><strong>Tools Invoked:</strong> ${trace.tools_invoked?.join(', ') || '-'}</div>
        <div><strong>Human Review Required:</strong> ${trace.human_review_required ?? false}</div>
      </div>
    </div>
  `;
}

function renderOverridePanel() {
  const target = document.getElementById('overridePanel');
  const history = state.overrideLog.map(entry => `
    <details>
      <summary>${entry.time} — Request ${entry.request_id || '-'}</summary>
      <div><strong>Reason:</strong> ${entry.reason}</div>
    </details>
  `).join('');

  target.innerHTML = `
    <div class="panel-section">
      <div class="panel-title">Human Override</div>
      <div class="field-row">
        <label for="overrideReason">Override reason</label>
        <textarea id="overrideReason" rows="4" placeholder="Explain why coordinator overrides AI recommendation."></textarea>
      </div>
      <button id="approveOverrideBtn" class="action-button secondary">Approve Override</button>
      ${history ? `<div class="panel-section"><div class="panel-subtitle">Override history</div>${history}</div>` : ''}
    </div>
  `;

  document.getElementById('approveOverrideBtn').addEventListener('click', () => {
    const reason = document.getElementById('overrideReason').value.trim();
    if (!reason) {
      renderToast('Provide an override reason before approval.');
      return;
    }

    state.overrideLog.push({
      time: new Date().toISOString(),
      reason,
      request_id: state.lastResult?.request_id || '-',
    });
    renderToast('Override logged for audit trail.');
    renderOverridePanel();
  });
}

function renderAgentCards() {
  const target = document.getElementById('agentCards');
  if (state.agentCards === null) {
    target.textContent = 'Loading agent cards...';
    return;
  }
  target.textContent = JSON.stringify(state.agentCards, null, 2);
}

function renderDashboard() {
  const metrics = document.getElementById('dashboardMetrics');
  const patientSnapshot = document.getElementById('patientSnapshot');
  const eligibilitySnapshot = document.getElementById('eligibilitySnapshot');
  const documentsSnapshot = document.getElementById('documentsSnapshot');
  const careTeamSnapshot = document.getElementById('careTeamSnapshot');
  const dataSources = document.getElementById('dataSources');

  if (!state.dashboardData) {
    metrics.innerHTML = '<div class="stat-card"><strong>–</strong>Waiting for platform data</div>';
    return;
  }

  const { platform_summary, patients, referrals, eligibility, appointments, notifications, documents, care_team, data_sources } = state.dashboardData;

  metrics.innerHTML = `
    <div class="stat-card"><strong>${platform_summary.active_patients}</strong>Active patients</div>
    <div class="stat-card"><strong>${platform_summary.open_referrals}</strong>Open referrals</div>
    <div class="stat-card"><strong>${platform_summary.eligible_cases}</strong>Eligible cases</div>
    <div class="stat-card"><strong>${platform_summary.appointments_booked}</strong>Appointments booked</div>
  `;

  patientSnapshot.innerHTML = `
    <ul>
      ${patients.slice(0, 3).map((patient) => `<li><strong>${patient.name}</strong> • ${patient.insurance_plan} • ${patient.priority}</li>`).join('')}
    </ul>
    <p><strong>Latest referrals:</strong></p>
    <ul>
      ${referrals.slice(0, 3).map((referral) => `<li>${referral.referral_id} • ${referral.status} • ${referral.diagnosis}</li>`).join('')}
    </ul>
  `;

  eligibilitySnapshot.innerHTML = `
    <ul>
      ${eligibility.map((item) => `<li>${item.referral_id} • ${item.insurance_plan} • ${item.eligible ? 'Eligible' : 'Needs review'}</li>`).join('')}
    </ul>
    <p><strong>Appointments:</strong></p>
    <ul>
      ${appointments.map((appointment) => `<li>${appointment.provider_name} • ${appointment.status} • ${appointment.slot}</li>`).join('')}
    </ul>
  `;

  documentsSnapshot.innerHTML = `
    <ul>
      ${documents.map((document) => `<li>${document.type} • ${document.status} • ${document.owner}</li>`).join('')}
    </ul>
    <p><strong>Notifications:</strong></p>
    <ul>
      ${notifications.map((notification) => `<li>${notification.channel} • ${notification.message}</li>`).join('')}
    </ul>
  `;

  careTeamSnapshot.innerHTML = `
    <ul>
      ${care_team.map((person) => `<li><strong>${person.name}</strong> • ${person.role} • ${person.contact}</li>`).join('')}
    </ul>
    <p><strong>Care coordination focus:</strong></p>
    <ul>
      <li>Resolve missing documents before specialist handoff.</li>
      <li>Escalate cases that exceed target wait times.</li>
      <li>Monitor payer authorization and appointment confirmation.</li>
    </ul>
  `;

  dataSources.innerHTML = data_sources.map((source) => `
    <div class="source-pill"><strong>${source.filename}</strong><br>${source.records} records</div>
  `).join('');
}

function renderRawContract() {
  const target = document.getElementById('rawContract');
  target.textContent = JSON.stringify({
    jsonrpc: '2.0',
    id: 'req-001',
    method: 'capability.route',
    params: {
      query: 'Recommend specialist for diagnosis: chest pain, location: Austin, TX, insurance: Aetna',
      payload: {
        max_results: 3,
      },
    },
  }, null, 2);
}

function setBusy(isBusy) {
  state.isBusy = isBusy;
  const generateBtn = document.getElementById('generateBtn');
  const askBtn = document.getElementById('askBtn');
  generateBtn.disabled = isBusy;
  askBtn.disabled = isBusy;
  if (isBusy) {
    generateBtn.textContent = 'Running workflow...';
    askBtn.textContent = 'Running workflow...';
  } else {
    generateBtn.textContent = 'Generate Recommendations';
    askBtn.textContent = 'Ask Assistant';
  }
}

function updateRequestContext() {
  state.diagnosis = document.getElementById('diagnosis').value;
  state.location = document.getElementById('location').value;
  state.insurancePlan = document.getElementById('insurancePlan').value;
  state.urgency = document.getElementById('urgency').value;
  state.preferredWindow = document.getElementById('preferredWindow').value;
  state.maxResults = Number(document.getElementById('maxResults').value);
  state.query = document.getElementById('queryInput').value;
  state.maxChatResults = Number(document.getElementById('maxChatResults').value);
}

async function sendJsonRpc(method, params) {
  const baseUrl = document.getElementById('backendBaseUrl').value.trim() || 'http://127.0.0.1:8090';
  const endpoint = `${baseUrl.replace(/\/$/, '')}/api/v1/capability-router`;
  const payload = {
    jsonrpc: '2.0',
    id: uuid(),
    method,
    params,
  };

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Backend HTTP error: ${response.status} ${body}`);
  }

  const data = await response.json();
  if (typeof data !== 'object' || data === null) {
    throw new Error('Backend returned invalid JSON-RPC payload.');
  }

  return data;
}

async function loadPlatformData() {
  try {
    const baseUrl = document.getElementById('backendBaseUrl').value.trim() || DEFAULT_BACKEND_URL;
    const endpoint = `${baseUrl.replace(/\/$/, '')}/api/v1/platform-data`;
    const response = await fetch(endpoint);
    if (!response.ok) {
      throw new Error(`Platform data unavailable: ${response.status}`);
    }
    state.dashboardData = await response.json();
  } catch (error) {
    state.dashboardData = null;
    renderToast(error.message);
  }
  renderDashboard();
}

async function loadAgentCards() {
  try {
    const response = await sendJsonRpc('agents.cards', {});
    if (response.error) {
      state.agentCards = { error: response.error };
    } else {
      state.agentCards = response.result;
    }
  } catch (error) {
    state.agentCards = { error: error.message };
  }
  renderAgentCards();
}

function addWorkflowStep(step) {
  state.workspaceLiveSteps.push(step);
  renderProgress();
}

async function runRecommendation({ capability, query, payload }) {
  if (state.isBusy) return;
  updateRequestContext();
  state.lastResult = null;
  state.lastNonRecommendationResult = null;
  state.lastAgentCard = null;
  state.lastSelectedCapability = null;
  state.workspaceLiveSteps = [];
  setBusy(true);
  renderRecommendationWorkspace();

  try {
    addWorkflowStep('Step 1/5: Creating JSON-RPC request');
    addWorkflowStep('Step 2/5: Calling Capability Router entrypoint');

    const response = await sendJsonRpc('capability.route', {
      capability,
      query,
      payload,
    });

    if (response.error) {
      throw new Error(response.error.message || 'JSON-RPC routing error');
    }

    const resultPayload = response.result || {};
    const selectedCapability = resultPayload.selected_capability;
    const selectedCard = resultPayload.selected_agent_card;
    const agentResult = resultPayload.agent_result || {};

    addWorkflowStep(`Step 3/5: Selected capability '${selectedCapability || 'unknown'}'`);
    addWorkflowStep(`Step 4/5: Loaded agent card '${selectedCard?.display_name || 'Unknown Agent'}'`);
    addWorkflowStep('Step 5/5: Executing selected agent and backend tools');

    state.lastSelectedCapability = selectedCapability;
    state.lastAgentCard = selectedCard;

    if (selectedCapability === 'specialist_recommendation') {
      state.lastResult = agentResult;
      state.lastNonRecommendationResult = null;
    } else {
      state.lastResult = null;
      state.lastNonRecommendationResult = agentResult;
    }

    renderToast('Agentic workflow completed.');
  } catch (error) {
    renderToast(error.message);
    state.lastResult = null;
    state.lastNonRecommendationResult = null;
    state.workspaceLiveSteps = [];
  } finally {
    setBusy(false);
    renderRecommendationWorkspace();
    renderAuditPanel();
    renderOverridePanel();
  }
}

function wireEvents() {
  document.getElementById('maxResults').addEventListener('input', (event) => {
    state.maxResults = Number(event.target.value);
    document.getElementById('maxResultsLabel').textContent = state.maxResults;
  });

  document.getElementById('maxChatResults').addEventListener('input', (event) => {
    state.maxChatResults = Number(event.target.value);
    document.getElementById('maxChatResultsLabel').textContent = state.maxChatResults;
  });

  document.getElementById('diagnosis').addEventListener('input', (event) => {
    state.diagnosis = event.target.value;
    renderIntakeChecks();
  });
  document.getElementById('location').addEventListener('input', (event) => {
    state.location = event.target.value;
    renderIntakeChecks();
  });
  document.getElementById('insurancePlan').addEventListener('change', (event) => {
    state.insurancePlan = event.target.value;
    renderIntakeChecks();
  });
  document.getElementById('urgency').addEventListener('change', (event) => {
    state.urgency = event.target.value;
    renderIntakeChecks();
  });
  document.getElementById('preferredWindow').addEventListener('change', (event) => {
    state.preferredWindow = event.target.value;
    renderIntakeChecks();
  });

  document.getElementById('generateBtn').addEventListener('click', async () => {
    updateRequestContext();
    if (!state.diagnosis.trim() || !state.location.trim()) {
      renderToast('Diagnosis and location are required.');
      return;
    }
    const windowMap = { 'Within 7 days': 7, 'Within 14 days': 14, 'Within 30 days': 30 };
    const preferredWindowDays = windowMap[state.preferredWindow] ?? 7;
    await runRecommendation({
      capability: 'specialist_recommendation',
      query: `Recommend specialist for diagnosis: ${state.diagnosis}, location: ${state.location}, insurance: ${state.insurancePlan}`,
      payload: {
        diagnosis: state.diagnosis,
        location: state.location,
        insurance_plan: state.insurancePlan,
        max_results: state.maxResults,
        urgency: state.urgency,
        preferred_window_days: preferredWindowDays,
      },
    });
  });

  document.getElementById('askBtn').addEventListener('click', async () => {
    updateRequestContext();
    if (!state.query.trim()) {
      renderToast('Please enter a query.');
      return;
    }
    await runRecommendation({
      capability: '',
      query: state.query,
      payload: { max_results: state.maxChatResults },
    });
  });
}

function init() {
  state.patientId = `PT-${Math.random().toString(16).slice(2, 10)}`;
  hydrateStateFromDom();
  renderIntakeChecks();
  renderRecommendationWorkspace();
  renderAuditPanel();
  renderOverridePanel();
  renderAgentCards();
  renderDashboard();
  renderRawContract();
  wireEvents();
  loadPlatformData();
  loadAgentCards();
}

window.addEventListener('DOMContentLoaded', init);
