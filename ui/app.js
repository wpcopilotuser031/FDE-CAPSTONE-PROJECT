const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8090';
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

function renderChatMessages() {
  const container = document.getElementById('chatMessages');
  container.innerHTML = state.chatMessages.map((msg) => {
    if (msg.role === 'typing') {
      return '<div class="chat-msg typing">Assistant is typing...</div>';
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
  return { ...state.lastRoutedContext };
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

    if (routedCapability && routedResult) {
      state.lastRoutedContext = {
        last_routed_capability_result: {
          capability: routedCapability,
          result: routedResult,
        },
      };
    }

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
}

function init() {
  wireEvents();
  restoreSession();
}

window.addEventListener('DOMContentLoaded', init);
