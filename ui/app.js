// Derive the backend URL from whatever host/IP the UI itself was loaded from,
// so this works both locally (127.0.0.1/localhost) and when the UI is served
// from a Docker container reached via a VM IP or hostname.
const DEFAULT_BACKEND_URL = `${window.location.protocol}//${window.location.hostname}:8090`;
const SESSION_STORAGE_KEY = 'care_coordination_session';

const state = {
  token: null,
  role: null,
  displayName: null,
  scope: null,
  chatMessages: [],
  chatBusy: false,
  lastRoutedContext: {},
};

function uuid() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `id-${Math.random().toString(16).slice(2)}-${Date.now()}`;
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderToast(message) {
  const toast = document.getElementById('toast');
  toast.textContent = message;
  toast.classList.remove('hidden');
  setTimeout(() => toast.classList.add('hidden'), 3000);
}

function roleLabel(role) {
  const labels = {
    patient: 'Patient',
    provider: 'Provider',
    care_agent: 'Care Agent',
  };
  return labels[role] || role;
}

function persistSession() {
  sessionStorage.setItem(
    SESSION_STORAGE_KEY,
    JSON.stringify({
      token: state.token,
      role: state.role,
      displayName: state.displayName,
      scope: state.scope,
    }),
  );
}

function clearPersistedSession() {
  sessionStorage.removeItem(SESSION_STORAGE_KEY);
}

function showLoginScreen() {
  document.getElementById('loginScreen').classList.remove('hidden');
  document.getElementById('chatScreen').classList.add('hidden');
}

function showChatScreen() {
  document.getElementById('loginScreen').classList.add('hidden');
  document.getElementById('chatScreen').classList.remove('hidden');
  document.getElementById('roleBadge').textContent = `Signed in as ${state.displayName} \u00b7 ${roleLabel(state.role)}`;

  if (!state.chatMessages.length) {
    state.chatMessages.push({
      role: 'system',
      text: `Hi ${state.displayName}! I can answer questions about referrals, specialists, insurance, and alternative providers, scoped to what a ${roleLabel(state.role)} is permitted to see.`,
    });
    renderChatMessages();
  }
  document.getElementById('chatInput').focus();
}

async function login(username, password) {
  const errorEl = document.getElementById('loginError');
  errorEl.classList.add('hidden');

  try {
    const response = await fetch(`${DEFAULT_BACKEND_URL}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || 'Invalid username or password.');
    }

    const session = await response.json();
    state.token = session.token;
    state.role = session.role;
    state.displayName = session.display_name;
    state.scope = session.scope;
    persistSession();
    showChatScreen();
  } catch (error) {
    errorEl.textContent = error.message;
    errorEl.classList.remove('hidden');
  }
}

async function restoreSession() {
  const raw = sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) {
    showLoginScreen();
    return;
  }

  try {
    const saved = JSON.parse(raw);
    const response = await fetch(`${DEFAULT_BACKEND_URL}/api/v1/auth/me`, {
      headers: { 'X-Session-Token': saved.token || '' },
    });
    if (!response.ok) {
      throw new Error('Session expired.');
    }
    const session = await response.json();
    state.token = session.token;
    state.role = session.role;
    state.displayName = session.display_name;
    state.scope = session.scope;
    showChatScreen();
  } catch {
    clearPersistedSession();
    showLoginScreen();
  }
}

function logout() {
  const token = state.token;
  state.token = null;
  state.role = null;
  state.displayName = null;
  state.scope = null;
  state.chatMessages = [];
  state.lastRoutedContext = {};
  clearPersistedSession();
  showLoginScreen();

  if (token) {
    fetch(`${DEFAULT_BACKEND_URL}/api/v1/auth/logout`, {
      method: 'POST',
      headers: { 'X-Session-Token': token },
    }).catch(() => {});
  }
}

async function sendJsonRpc(method, params) {
  const endpoint = `${DEFAULT_BACKEND_URL}/api/v1/capability-router`;
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
      'X-Session-Token': state.token || '',
    },
    body: JSON.stringify(payload),
  });

  if (response.status === 401) {
    logout();
    throw new Error('Your session expired. Please sign in again.');
  }

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

function renderRoutedSummary(routed) {
  if (!routed || !routed.capability || !routed.result) return '';
  const { capability, result } = routed;

  if (capability === 'specialist_recommendation' || capability === 'alternative_provider_suggestion') {
    const items = capability === 'specialist_recommendation' ? (result.recommendations || []) : (result.alternatives || []);
    if (!items.length) return '';
    const rows = items.slice(0, 3).map((item) => `
      <li><strong>${escapeHtml(item.provider_name || 'Unknown')}</strong> \u2014 ${escapeHtml(item.specialty || '-')}, ${item.wait_days ?? '-'}d wait, score ${item.score ?? '-'}</li>
    `).join('');
    return `<div class="chat-routed-card"><div class="chat-routed-title">Live agent result: ${capability.replace(/_/g, ' ')}</div><ul>${rows}</ul></div>`;
  }

  if (capability === 'referral_triage') {
    return `<div class="chat-routed-card"><div class="chat-routed-title">Live agent result: referral triage</div>
      <p>Priority: <strong>${escapeHtml(result.priority || '-')}</strong> | Specialties: ${escapeHtml((result.suggested_specialties || []).join(', ') || '-')}</p></div>`;
  }

  if (capability === 'insurance_validation') {
    return `<div class="chat-routed-card"><div class="chat-routed-title">Live agent result: insurance validation</div>
      <p>In-network: <strong>${result.in_network ? 'Yes' : 'No'}</strong></p></div>`;
  }

  if (capability === 'provider_discovery') {
    const items = result.providers || result.candidates || [];
    if (!items.length) return '';
    const rows = items.slice(0, 3).map((item) => `<li><strong>${escapeHtml(item.provider_name || 'Unknown')}</strong> \u2014 ${escapeHtml(item.specialty || '-')}, ${escapeHtml(item.location || '-')}</li>`).join('');
    return `<div class="chat-routed-card"><div class="chat-routed-title">Live agent result: provider discovery</div><ul>${rows}</ul></div>`;
  }

  return '';
}

function renderDocResultCard(msg) {
  const r = msg.docResult;
  if (!r) return '';
  const method = r.extraction_method || 'unknown';
  const dxRows = (r.diagnosis_codes || []).map(c =>
    `<tr><td><span class="code-tag">${escapeHtml(c.code)}</span></td><td>${escapeHtml(c.description)}</td></tr>`
  ).join('');
  const pxRows = (r.procedure_codes || []).map(c =>
    `<tr><td><span class="code-tag">${escapeHtml(c.code)}</span></td><td>${escapeHtml(c.description)}</td></tr>`
  ).join('');
  const summary = r.clinical_summary ? `<div class="chat-doc-summary">${escapeHtml(r.clinical_summary)}</div>` : '';
  const methodBadge = `<span class="method-badge method-${method.replace(/\+/g,'-').replace(/_/g,'-')}">${escapeHtml(method)}</span>`;
  return `
    <div class="chat-doc-card">
      <div class="chat-doc-card-header">📄 ${escapeHtml(msg.filename || 'document')} &nbsp;${methodBadge}</div>
      ${summary}
      <div class="chat-doc-tables">
        ${ dxRows ? `<div><div class="chat-doc-table-title">🩺 ICD-10 Diagnosis</div><table class="code-table"><tbody>${dxRows}</tbody></table></div>` : '' }
        ${ pxRows ? `<div><div class="chat-doc-table-title">⚕️ CPT Procedures</div><table class="code-table"><tbody>${pxRows}</tbody></table></div>` : '' }
      </div>
      <div class="chat-doc-meta">${r.total_diagnosis_codes} diagnosis · ${r.total_procedure_codes} procedure code(s)</div>
    </div>
  `;
}

function renderChatMessages() {
  const container = document.getElementById('chatMessages');
  container.innerHTML = state.chatMessages.map((msg) => {
    if (msg.role === 'typing') {
      return '<div class="chat-msg typing">Assistant is typing...</div>';
    }
    if (msg.role === 'doc_result') {
      return `<div class="chat-msg assistant">${renderDocResultCard(msg)}</div>`;
    }
    const cls = msg.role === 'user' ? 'user' : msg.role === 'system' ? 'system' : 'assistant';
    const routedHtml = msg.routed ? renderRoutedSummary(msg.routed) : '';
    return `<div class="chat-msg ${cls}">${escapeHtml(msg.text)}${routedHtml}</div>`;
  }).join('');
  container.scrollTop = container.scrollHeight;
}

function renderChatSuggestions(suggestions) {
  const container = document.getElementById('chatSuggestions');
  if (!suggestions || !suggestions.length) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = suggestions
    .map(text => `<button type="button" class="chat-suggestion-chip">${escapeHtml(text)}</button>`)
    .join('');
}

function buildChatContext() {
  // Intentionally NOT carrying forward state.lastRoutedContext here: sending stale
  // routed-capability data from a previous, unrelated question let the assistant LLM
  // "ground" its answer to a completely different question in old data (e.g. answering
  // "Show patient history" using a specialist recommendation from a prior turn). Each
  // turn now only relies on whatever the backend computes fresh for the CURRENT question.
  return {};
}

async function sendChatMessage(rawQuestion) {
  const inputEl = document.getElementById('chatInput');
  const question = (rawQuestion ?? inputEl.value).trim();
  if (!question || state.chatBusy) return;

  state.chatMessages.push({ role: 'user', text: question });
  state.chatMessages.push({ role: 'typing', text: '' });
  renderChatMessages();
  renderChatSuggestions([]);
  inputEl.value = '';
  state.chatBusy = true;
  document.getElementById('chatSendBtn').disabled = true;

  try {
    const response = await sendJsonRpc('capability.route', {
      capability: 'conversational_assistant',
      payload: {
        question,
        asker_role: roleLabel(state.role),
        context: buildChatContext(),
      },
    });

    if (response.error) {
      throw new Error(response.error.message || 'Assistant error');
    }

    const agentResult = response.result?.agent_result || {};
    const routedCapability = response.result?.routed_capability || null;
    const routedResult = response.result?.routed_agent_result || null;

    state.chatMessages = state.chatMessages.filter(msg => msg.role !== 'typing');
    state.chatMessages.push({
      role: 'assistant',
      text: agentResult.answer || 'I could not generate an answer.',
      routed: routedCapability && routedResult ? { capability: routedCapability, result: routedResult } : null,
    });
    renderChatMessages();
    renderChatSuggestions(agentResult.follow_up_suggestions || []);
  } catch (error) {
    state.chatMessages = state.chatMessages.filter(msg => msg.role !== 'typing');
    state.chatMessages.push({ role: 'assistant', text: `Sorry, something went wrong: ${error.message}` });
    renderChatMessages();
  } finally {
    state.chatBusy = false;
    document.getElementById('chatSendBtn').disabled = false;
  }
}

function wireEvents() {
  document.getElementById('loginBtn').addEventListener('click', () => {
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    if (!username || !password) {
      const errorEl = document.getElementById('loginError');
      errorEl.textContent = 'Enter both a username and password.';
      errorEl.classList.remove('hidden');
      return;
    }
    login(username, password);
  });

  document.getElementById('loginPassword').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      document.getElementById('loginBtn').click();
    }
  });

  document.querySelectorAll('.demo-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.getElementById('loginUsername').value = btn.dataset.username;
      document.getElementById('loginPassword').value = btn.dataset.password;
      login(btn.dataset.username, btn.dataset.password);
    });
  });

  document.getElementById('logoutBtn').addEventListener('click', logout);

  document.getElementById('chatForm').addEventListener('submit', (event) => {
    event.preventDefault();
    sendChatMessage();
  });

  document.getElementById('chatInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendChatMessage();
    }
  });

  document.getElementById('chatSuggestions').addEventListener('click', (event) => {
    const chip = event.target.closest('.chat-suggestion-chip');
    if (chip) {
      sendChatMessage(chip.textContent);
    }
  });

  // Chat file attachment (paperclip button)
  document.getElementById('chatFileInput').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) handleChatFileAttach(file);
  });

  // Tab switching
  document.getElementById('chatTabBtn').addEventListener('click', () => switchTab('chat'));
  document.getElementById('docTabBtn').addEventListener('click', () => switchTab('doc'));

  // Document upload wiring
  const fileInput = document.getElementById('fileInput');
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    if (file) loadFileIntoTextArea(file);
  });

  const dropZone = document.getElementById('dropZone');
  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drag-over'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (file) loadFileIntoTextArea(file);
  });

  document.getElementById('extractBtn').addEventListener('click', runExtraction);
  document.getElementById('injectToChatBtn').addEventListener('click', injectCodesToChat);
}

// ===================== Tab management =====================

function switchTab(tab) {
  const chatTab = document.getElementById('chatTab');
  const docTab = document.getElementById('docTab');
  const chatBtn = document.getElementById('chatTabBtn');
  const docBtn = document.getElementById('docTabBtn');

  if (tab === 'chat') {
    chatTab.classList.remove('hidden');
    docTab.classList.add('hidden');
    chatBtn.classList.add('active');
    docBtn.classList.remove('active');
  } else {
    chatTab.classList.add('hidden');
    docTab.classList.remove('hidden');
    docBtn.classList.add('active');
    chatBtn.classList.remove('active');
    loadSampleDocs();
  }
}

// ===================== Document Analyzer =====================

let lastExtractionResult = null;

function loadFileIntoTextArea(file) {
  if (!file.name.match(/\.(txt|text)$/i)) {
    renderToast('Only .txt files are supported.');
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('docTextInput').value = e.target.result;
    document.getElementById('docStatus').textContent = `Loaded: ${file.name}`;
    document.getElementById('docResults').classList.add('hidden');
    lastExtractionResult = null;
  };
  reader.readAsText(file);
}

async function loadSampleDocs() {
  const container = document.getElementById('sampleDocBtns');
  if (container.dataset.loaded === 'true') return;

  try {
    const response = await fetch(`${DEFAULT_BACKEND_URL}/api/v1/documents/sample-docs`, {
      headers: { 'X-Session-Token': state.token || '' },
    });
    if (!response.ok) {
      // If unauthorized (patient role), hide the sample docs row gracefully
      container.parentElement.style.display = 'none';
      return;
    }
    const docs = await response.json();
    container.innerHTML = docs.map((doc) =>
      `<button type="button" class="sample-doc-btn" data-text="${escapeHtml(doc.text)}" data-id="${escapeHtml(doc.document_id)}">${escapeHtml(doc.document_id)}</button>`
    ).join('');
    container.dataset.loaded = 'true';

    container.addEventListener('click', (e) => {
      const btn = e.target.closest('.sample-doc-btn');
      if (btn) {
        document.getElementById('docTextInput').value = btn.dataset.text;
        document.getElementById('docStatus').textContent = `Sample loaded: ${btn.dataset.id}`;
        document.getElementById('docResults').classList.add('hidden');
        lastExtractionResult = null;
      }
    });
  } catch {
    container.parentElement.style.display = 'none';
  }
}

async function runExtraction() {
  const text = document.getElementById('docTextInput').value.trim();
  if (!text) {
    renderToast('Please paste or upload a document first.');
    return;
  }

  const btn = document.getElementById('extractBtn');
  const status = document.getElementById('docStatus');
  btn.disabled = true;
  btn.textContent = 'Extracting...';
  status.textContent = '';
  document.getElementById('docResults').classList.add('hidden');

  try {
    const response = await fetch(`${DEFAULT_BACKEND_URL}/api/v1/documents/extract-codes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Token': state.token || '',
      },
      body: JSON.stringify({ document_text: text }),
    });

    if (response.status === 403) {
      renderToast('Document extraction is only available to providers and care agents.');
      return;
    }
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${response.status}`);
    }

    const result = await response.json();
    lastExtractionResult = result;
    renderExtractionResults(result);
  } catch (err) {
    renderToast(`Extraction failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = '🔍 Extract Codes';
  }
}

function renderExtractionResults(result) {
  const resultsEl = document.getElementById('docResults');
  const summaryEl = document.getElementById('docSummaryCard');
  const dxBody = document.getElementById('diagnosisTableBody');
  const pxBody = document.getElementById('procedureTableBody');
  const noDxMsg = document.getElementById('noDxMsg');
  const noPxMsg = document.getElementById('noPxMsg');

  // Summary card
  const method = result.extraction_method || 'unknown';
  const docId = result.document_id ? `Document ID: <strong>${escapeHtml(result.document_id)}</strong> &nbsp;|&nbsp; ` : '';
  summaryEl.innerHTML = `
    <div class="summary-meta">${docId}
      <span class="method-badge method-${method.replace(/\+/g, '-')}">${escapeHtml(method)}</span>
      &nbsp;|&nbsp; ${result.total_diagnosis_codes} diagnosis code(s) &nbsp;|&nbsp; ${result.total_procedure_codes} procedure code(s)
    </div>
    ${result.clinical_summary ? `<div class="summary-text">${escapeHtml(result.clinical_summary)}</div>` : ''}
  `;

  // Diagnosis table
  if (result.diagnosis_codes && result.diagnosis_codes.length) {
    dxBody.innerHTML = result.diagnosis_codes.map((item) =>
      `<tr><td><code class="code-tag">${escapeHtml(item.code)}</code></td><td>${escapeHtml(item.description)}</td></tr>`
    ).join('');
    noDxMsg.classList.add('hidden');
  } else {
    dxBody.innerHTML = '';
    noDxMsg.classList.remove('hidden');
  }

  // Procedure table
  if (result.procedure_codes && result.procedure_codes.length) {
    pxBody.innerHTML = result.procedure_codes.map((item) =>
      `<tr><td><code class="code-tag">${escapeHtml(item.code)}</code></td><td>${escapeHtml(item.description)}</td></tr>`
    ).join('');
    noPxMsg.classList.add('hidden');
  } else {
    pxBody.innerHTML = '';
    noPxMsg.classList.remove('hidden');
  }

  resultsEl.classList.remove('hidden');
}

function injectCodesToChat() {
  if (!lastExtractionResult) return;

  const dxCodes = (lastExtractionResult.diagnosis_codes || []).map((c) => c.code).join(', ');
  const pxCodes = (lastExtractionResult.procedure_codes || []).map((c) => c.code).join(', ');
  const summary = lastExtractionResult.clinical_summary || '';

  let question = 'I extracted the following codes from a referral document. ';
  if (dxCodes) question += `Diagnosis codes: ${dxCodes}. `;
  if (pxCodes) question += `Procedure codes: ${pxCodes}. `;
  if (summary) question += `Clinical context: ${summary}. `;
  question += 'What specialist should I refer this patient to?';

  switchTab('chat');
  document.getElementById('chatInput').value = question;
  document.getElementById('chatInput').focus();
}

// ===================== Chat document attachment =====================

async function handleChatFileAttach(file) {
  if (!file || !file.name.match(/\.(txt|text|pdf)$/i)) {
    renderToast('Only .pdf and .txt files are supported.');
    return;
  }
  if (state.chatBusy) return;

  // Patient role cannot extract codes
  if (state.role === 'patient') {
    state.chatMessages.push({
      role: 'assistant',
      text: 'Document code extraction is only available to providers and care agents. As a patient you can ask your provider to share the extracted codes.',
    });
    renderChatMessages();
    return;
  }

  // Show user bubble: file name
  state.chatMessages.push({ role: 'user', text: `📎 Attached: ${file.name}` });
  state.chatMessages.push({ role: 'typing', text: '' });
  renderChatMessages();
  state.chatBusy = true;
  document.getElementById('chatSendBtn').disabled = true;

  try {
    // Use multipart upload endpoint — handles both PDF and TXT server-side
    const formData = new FormData();
    formData.append('file', file);

    const res = await fetch(`${DEFAULT_BACKEND_URL}/api/v1/documents/upload-extract`, {
      method: 'POST',
      headers: { 'X-Session-Token': state.token || '' },
      body: formData,
    });

    if (res.status === 401) { logout(); return; }

    state.chatMessages = state.chatMessages.filter(m => m.role !== 'typing');

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      state.chatMessages.push({ role: 'assistant', text: `Could not extract codes: ${body.detail || res.status}` });
      renderChatMessages();
      return;
    }

    const result = await res.json();
    // Store for potential inject-to-chat use
    docState.lastResult = result;

    // Show structured doc result card in chat
    state.chatMessages.push({ role: 'doc_result', filename: file.name, docResult: result });
    renderChatMessages();

    // If codes were found, auto-ask the conversational assistant to comment
    if (result.total_diagnosis_codes > 0) {
      const dxList = result.diagnosis_codes.map(c => `${c.code} (${c.description})`).join(', ');
      const pxList = result.procedure_codes.length
        ? result.procedure_codes.map(c => `${c.code} (${c.description})`).join(', ')
        : 'none';
      const autoQuestion = `Based on this referral document, the extracted ICD-10 codes are: ${dxList}. Procedure codes: ${pxList}. What specialist should this patient be referred to?`;

      state.chatMessages.push({ role: 'typing', text: '' });
      renderChatMessages();

      const rpcRes = await sendJsonRpc('capability.route', {
        capability: 'conversational_assistant',
        payload: { question: autoQuestion, asker_role: roleLabel(state.role), context: {} },
      });

      state.chatMessages = state.chatMessages.filter(m => m.role !== 'typing');

      if (!rpcRes.error) {
        const agentResult = rpcRes.result?.agent_result || {};
        state.chatMessages.push({
          role: 'assistant',
          text: agentResult.answer || 'I could not generate a recommendation.',
          routed: rpcRes.result?.routed_capability ? { capability: rpcRes.result.routed_capability, result: rpcRes.result.routed_agent_result } : null,
        });
        renderChatSuggestions(agentResult.follow_up_suggestions || []);
      }
      renderChatMessages();
    }
  } catch (err) {
    state.chatMessages = state.chatMessages.filter(m => m.role !== 'typing');
    state.chatMessages.push({ role: 'assistant', text: `Error processing document: ${err.message}` });
    renderChatMessages();
  } finally {
    state.chatBusy = false;
    document.getElementById('chatSendBtn').disabled = false;
    // Reset so the same file can be re-attached
    document.getElementById('chatFileInput').value = '';
  }
}

function init() {
  wireEvents();
  wireDocEvents();
  restoreSession();
}

// ===================== Document Analyzer =====================

const docState = {
  busy: false,
  lastResult: null,
};

function switchTab(tab) {
  const chatTab = document.getElementById('chatTab');
  const docTab = document.getElementById('docTab');
  const chatBtn = document.getElementById('chatTabBtn');
  const docBtn = document.getElementById('docTabBtn');

  if (tab === 'chat') {
    chatTab.classList.remove('hidden');
    docTab.classList.add('hidden');
    chatBtn.classList.add('active');
    docBtn.classList.remove('active');
  } else {
    chatTab.classList.add('hidden');
    docTab.classList.remove('hidden');
    docBtn.classList.add('active');
    chatBtn.classList.remove('active');
    loadSampleDocs();
  }
}

async function loadSampleDocs() {
  const container = document.getElementById('sampleDocBtns');
  if (!container || container.childElementCount > 0) return;
  if (!state.token) return;

  try {
    const res = await fetch(`${DEFAULT_BACKEND_URL}/api/v1/documents/sample-docs`, {
      headers: { 'X-Session-Token': state.token },
    });
    if (!res.ok) return;
    const docs = await res.json();
    container.innerHTML = '';
    docs.forEach((doc) => {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'sample-doc-btn';
      btn.textContent = doc.document_id || doc.filename;
      btn.title = doc.title;
      btn.addEventListener('click', () => {
        document.getElementById('docTextInput').value = doc.text;
        document.getElementById('docStatus').textContent = `Loaded: ${doc.title}`;
      });
      container.appendChild(btn);
    });
  } catch {
    // Silently ignore - sample docs are optional
  }
}

function renderExtractionResults(result) {
  const resultsEl = document.getElementById('docResults');
  const summaryEl = document.getElementById('docSummaryCard');
  const dxBody = document.getElementById('diagnosisTableBody');
  const pxBody = document.getElementById('procedureTableBody');
  const noDxMsg = document.getElementById('noDxMsg');
  const noPxMsg = document.getElementById('noPxMsg');

  const method = result.extraction_method || 'unknown';
  const methodClass = `method-${method.replace(/\+/g, '-').replace(/_/g, '-')}`;
  const docId = result.document_id ? `<strong>${escapeHtml(result.document_id)}</strong> · ` : '';
  const summary = result.clinical_summary
    ? `<div class="summary-text">${escapeHtml(result.clinical_summary)}</div>`
    : '';

  summaryEl.innerHTML = `
    <div class="summary-meta">
      ${docId}
      ${result.total_diagnosis_codes} diagnosis code(s) · ${result.total_procedure_codes} procedure code(s) ·
      <span class="method-badge ${methodClass}">${escapeHtml(method)}</span>
    </div>
    ${summary}
  `;

  // Diagnosis codes table
  if (result.diagnosis_codes && result.diagnosis_codes.length) {
    dxBody.innerHTML = result.diagnosis_codes.map((item) => `
      <tr>
        <td><span class="code-tag">${escapeHtml(item.code)}</span></td>
        <td>${escapeHtml(item.description)}</td>
      </tr>
    `).join('');
    noDxMsg.classList.add('hidden');
    dxBody.closest('table').classList.remove('hidden');
  } else {
    dxBody.innerHTML = '';
    noDxMsg.classList.remove('hidden');
  }

  // Procedure codes table
  if (result.procedure_codes && result.procedure_codes.length) {
    pxBody.innerHTML = result.procedure_codes.map((item) => `
      <tr>
        <td><span class="code-tag">${escapeHtml(item.code)}</span></td>
        <td>${escapeHtml(item.description)}</td>
      </tr>
    `).join('');
    noPxMsg.classList.add('hidden');
    pxBody.closest('table').classList.remove('hidden');
  } else {
    pxBody.innerHTML = '';
    noPxMsg.classList.remove('hidden');
  }

  resultsEl.classList.remove('hidden');
}

async function extractCodes() {
  if (docState.busy) return;
  const text = document.getElementById('docTextInput').value.trim();
  const statusEl = document.getElementById('docStatus');

  if (!text) {
    statusEl.textContent = 'Please paste or upload a document first.';
    return;
  }

  if (!state.token) {
    statusEl.textContent = 'Please sign in first.';
    return;
  }

  docState.busy = true;
  document.getElementById('extractBtn').disabled = true;
  statusEl.textContent = 'Extracting codes...';
  document.getElementById('docResults').classList.add('hidden');

  try {
    const res = await fetch(`${DEFAULT_BACKEND_URL}/api/v1/documents/extract-codes`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Session-Token': state.token,
      },
      body: JSON.stringify({ document_text: text }),
    });

    if (res.status === 403) {
      statusEl.textContent = 'Access denied. Document extraction is only available to providers and care agents.';
      return;
    }

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `HTTP ${res.status}`);
    }

    const result = await res.json();
    docState.lastResult = result;
    statusEl.textContent = `Done — extracted ${result.total_diagnosis_codes} diagnosis and ${result.total_procedure_codes} procedure code(s).`;
    renderExtractionResults(result);
  } catch (err) {
    statusEl.textContent = `Error: ${err.message}`;
  } finally {
    docState.busy = false;
    document.getElementById('extractBtn').disabled = false;
  }
}

function injectCodesToChat() {
  if (!docState.lastResult) return;
  const { diagnosis_codes, procedure_codes } = docState.lastResult;
  const dxList = diagnosis_codes.map((c) => `${c.code} (${c.description})`).join(', ') || 'none';
  const pxList = procedure_codes.map((c) => `${c.code} (${c.description})`).join(', ') || 'none';
  const question = `I have a referral with these ICD-10 codes: ${dxList}. Procedures: ${pxList}. What specialist should I refer to?`;
  switchTab('chat');
  document.getElementById('chatInput').value = question;
  document.getElementById('chatInput').focus();
}

function wireDocEvents() {
  document.getElementById('docTabBtn').addEventListener('click', () => switchTab('doc'));
  document.getElementById('chatTabBtn').addEventListener('click', () => switchTab('chat'));
  document.getElementById('extractBtn').addEventListener('click', extractCodes);
  document.getElementById('injectToChatBtn').addEventListener('click', injectCodesToChat);

  // File input
  const fileInput = document.getElementById('fileInput');
  const dropZone = document.getElementById('dropZone');
  const docTextInput = document.getElementById('docTextInput');

  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      docTextInput.value = ev.target.result;
      document.getElementById('docStatus').textContent = `Loaded: ${file.name}`;
    };
    reader.readAsText(file);
  });

  // Drag and drop
  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drag-over'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      docTextInput.value = ev.target.result;
      document.getElementById('docStatus').textContent = `Loaded: ${file.name}`;
    };
    reader.readAsText(file);
  });
}

window.addEventListener('DOMContentLoaded', init);
