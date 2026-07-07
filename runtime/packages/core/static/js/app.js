// static/js/app.js

const BASE = window.location.origin;
let activeChar = null;
let sessionId = crypto.randomUUID();
let characters = [];
let authToken = null;
let authUser = null;

// DOM Elements
const els = {
    statusDot: document.getElementById('statusDot'),
    statusText: document.getElementById('statusText'),
    kalCount: document.getElementById('kalCount'),
    entityCount: document.getElementById('entityCount'),
    convCount: document.getElementById('convCount'),
    charList: document.getElementById('charList'),
    modeSelect: document.getElementById('modeSelect'),
    clearBtn: document.getElementById('clearBtn'),
    chatCharName: document.getElementById('chatCharName'),
    chatCharRole: document.getElementById('chatCharRole'),
    messages: document.getElementById('messages'),
    queryInput: document.getElementById('queryInput'),
    sendBtn: document.getElementById('sendBtn'),
    telemetryContent: document.getElementById('telemetryContent'),
    authStatus: document.getElementById('authStatus'),
    authIdentifier: document.getElementById('authIdentifier'),
    authPassword: document.getElementById('authPassword'),
    loginBtn: document.getElementById('loginBtn'),
    registerBtn: document.getElementById('registerBtn'),
    logoutBtn: document.getElementById('logoutBtn'),
};

// Initialize
async function init() {
    restoreAuth();
    bindEvents();
    pollHealth();
    await loadCharacters();
    setInterval(pollHealth, 5000);
}

function bindEvents() {
    els.sendBtn.addEventListener('click', sendMessage);
    els.queryInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    els.clearBtn.addEventListener('click', () => {
        sessionId = crypto.randomUUID();
        els.messages.innerHTML = `
            <div class="empty-state">
                <i class="fa-solid fa-broom"></i>
                <p>Memory purged. Neural link reset.</p>
            </div>
        `;
        clearTelemetry();
    });

    if (els.loginBtn) {
        els.loginBtn.addEventListener('click', login);
    }
    if (els.registerBtn) {
        els.registerBtn.addEventListener('click', register);
    }
    if (els.logoutBtn) {
        els.logoutBtn.addEventListener('click', logout);
    }
}

function restoreAuth() {
    try {
        authToken = localStorage.getItem('synthesus_jwt');
        const userRaw = localStorage.getItem('synthesus_user');
        authUser = userRaw ? JSON.parse(userRaw) : null;
    } catch (e) {
        authToken = null;
        authUser = null;
    }
    updateAuthUi();
}

function setAuth(token, user) {
    authToken = token;
    authUser = user;
    try {
        if (token) localStorage.setItem('synthesus_jwt', token);
        if (user) localStorage.setItem('synthesus_user', JSON.stringify(user));
    } catch (e) {
        // ignore
    }
    if (user?.session_id) {
        sessionId = user.session_id;
    }
    updateAuthUi();
}

function clearAuth() {
    authToken = null;
    authUser = null;
    try {
        localStorage.removeItem('synthesus_jwt');
        localStorage.removeItem('synthesus_user');
    } catch (e) {
        // ignore
    }
    updateAuthUi();
}

function updateAuthUi() {
    if (!els.authStatus) return;
    const isAuthed = !!authToken;
    els.authStatus.textContent = isAuthed ? `Authenticated${authUser?.username ? ` (${authUser.username})` : ''}` : 'Anonymous';
    if (els.logoutBtn) els.logoutBtn.style.display = isAuthed ? '' : 'none';
}

function authHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
    return headers;
}

async function login() {
    const identifier = els.authIdentifier?.value?.trim();
    const password = els.authPassword?.value || '';
    if (!identifier || !password) return;
    try {
        const r = await fetch(`${BASE}/api/v1/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ identifier, password })
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d?.detail || 'Login failed');
        setAuth(d.token, { user_id: d.user_id, username: d.username, session_id: d.session_id });
    } catch (e) {
        console.error(e);
    }
}

async function register() {
    const identifier = els.authIdentifier?.value?.trim();
    const password = els.authPassword?.value || '';
    if (!identifier || !password) return;
    // For minimal UI: treat identifier as email, and derive a username
    const email = identifier;
    const username = identifier.split('@')[0] || identifier;
    try {
        const r = await fetch(`${BASE}/api/v1/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, username, password })
        });
        const d = await r.json();
        if (!r.ok) throw new Error(d?.detail || 'Registration failed');
        setAuth(d.token, { user_id: d.user_id, username: d.username, session_id: d.session_id });
    } catch (e) {
        console.error(e);
    }
}

async function logout() {
    clearAuth();
}

// Data Fetching
async function pollHealth() {
    try {
        const r = await fetch(`${BASE}/api/v1/health`);
        const d = await r.json();
        
        const isOnline = d.status === 'healthy';
        els.statusDot.className = `pulse-dot ${isOnline ? 'online' : ''}`;
        els.statusText.textContent = isOnline ? 'ONLINE' : 'DEGRADED';
        els.statusText.style.color = isOnline ? 'var(--accent-green)' : 'var(--accent-red)';

        // UI labels are business-grade; map to available server metrics.
        if (els.kalCount) els.kalCount.textContent = Number(d?.rag?.vectors || 0).toLocaleString();
        if (els.entityCount) els.entityCount.textContent = Number(d?.characters_loaded || 0).toLocaleString();
        if (els.convCount) els.convCount.textContent = Number(d?.active_sessions || 0).toLocaleString();
    } catch(e) {
        els.statusDot.className = 'pulse-dot';
        els.statusText.textContent = 'OFFLINE';
        els.statusText.style.color = 'var(--text-muted)';
    }
}

async function loadCharacters() {
    try {
        const r = await fetch(`${BASE}/api/v1/characters`);
        const d = await r.json();
        characters = d.characters;
        renderCharList();
        if (characters.length > 0) {
            // Default to 'synth' if it exists, else the first one
            const defaultChar = characters.find(c => c.id === 'synth') || characters[0];
            selectChar(defaultChar.id);
        }
    } catch(e) {
        els.charList.innerHTML = `<div class="empty-state"><i class="fa-solid fa-triangle-exclamation"></i><p>Failed to load neural roster.</p></div>`;
    }
}

// UI Rendering
function renderCharList() {
    els.charList.innerHTML = characters.map(c => `
        <div class="char-card ${c.id === activeChar ? 'active' : ''}" data-id="${c.id}">
            <div class="char-name">${c.name}</div>
            <div class="char-role">${c.role || c.description.slice(0,50)+'...'}</div>
        </div>
    `).join('');
    
    // Bind clicks
    document.querySelectorAll('.char-card').forEach(card => {
        card.addEventListener('click', () => selectChar(card.dataset.id));
    });
}

function selectChar(id) {
    activeChar = id;
    const c = characters.find(x => x.id === id);
    if (!c) return;
    
    // Update active class
    document.querySelectorAll('.char-card').forEach(card => {
        card.classList.toggle('active', card.dataset.id === id);
    });
    
    els.chatCharName.textContent = c.name;
    els.chatCharRole.textContent = c.role || 'Digital Entity';
    
    // Focus input
    els.queryInput.focus();
}

function addMessage(role, content, meta = null) {
    // Remove empty state
    const emptyState = els.messages.querySelector('.empty-state');
    if (emptyState) emptyState.remove();

    const div = document.createElement('div');
    div.className = `message ${role}`;
    
    let metaHtml = '';
    if (role === 'assistant' && meta) {
        const sourceClass = String(meta.source || 'fallback').toLowerCase();
        metaHtml = `
            <div class="msg-meta">
                <span class="badge ${sourceClass}">${meta.source}</span>
                <span>CONF: ${(meta.confidence * 100).toFixed(1)}%</span>
                <span>${meta.latency_ms.toFixed(0)}ms</span>
            </div>
        `;
    }

    div.innerHTML = `
        <div class="msg-content">${escapeHtml(content)}</div>
        ${metaHtml}
    `;
    
    els.messages.appendChild(div);
    els.messages.scrollTop = els.messages.scrollHeight;
}

function showTyping() {
    const emptyState = els.messages.querySelector('.empty-state');
    if (emptyState) emptyState.remove();
    
    const div = document.createElement('div');
    div.className = 'message assistant id-typing';
    div.innerHTML = `
        <div class="msg-content" style="background:transparent; padding:0; border:none;">
            <div class="typing-fx"><span></span><span></span><span></span></div>
        </div>
    `;
    els.messages.appendChild(div);
    els.messages.scrollTop = els.messages.scrollHeight;
}

function hideTyping() {
    const typing = els.messages.querySelector('.id-typing');
    if (typing) typing.remove();
}

// Chat Logic
async function sendMessage() {
    const q = els.queryInput.value.trim();
    if (!q || !activeChar) return;
    
    els.queryInput.value = '';
    els.sendBtn.disabled = true;
    
    addMessage('user', q);
    showTyping();
    
    try {
        const r = await fetch(`${BASE}/api/v1/query`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                query: q,
                character: activeChar,
                mode: els.modeSelect.value,
                session_id: sessionId,
                include_sources: true,
                include_debug: true,
            })
        });
        
        hideTyping();
        
        if (r.status === 429) {
            addMessage('assistant', 'System overloaded. Link degraded temporarily.');
            return;
        }
        
        const d = await r.json();
        addMessage('assistant', d.response, {
            source: d.source,
            confidence: d.confidence,
            latency_ms: d.latency_ms
        });
        
        renderTelemetry(d);
        
    } catch(e) {
        hideTyping();
        addMessage('assistant', 'Connection error. Signal lost.');
        console.error(e);
    } finally {
        els.sendBtn.disabled = false;
        els.queryInput.focus();
    }
}

// Tooling
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Telemetry Rendering
function clearTelemetry() {
    els.telemetryContent.innerHTML = `
        <div class="empty-telemetry">
            <i class="fa-solid fa-wave-square"></i>
            <p>Awaiting Signal Data...</p>
        </div>
    `;
}

function getConfidenceColor(val) {
    if(val > 0.7) return 'var(--accent-green)';
    if(val > 0.4) return 'var(--accent-cyan)';
    return 'var(--accent-red)';
}

function renderTelemetry(data) {
    let html = '';
    const ml = data.debug?.ml_swarm;
    const isCognitive = data.source === 'cognitive';
    const isRag = data.source === 'rag';

    // 1. Overall Routing
    html += `
        <div class="t-module">
            <div class="t-module-title"><span>System Routing</span> <span>${data.latency_ms.toFixed(1)}ms</span></div>
            <div class="t-data-row">
                <span class="t-label">Selected Source</span>
                <span class="t-val ${isCognitive ? 'val-high' : (isRag ? 'val-med' : 'val-low')}">${data.source.toUpperCase()}</span>
            </div>
            <div class="t-data-row" style="flex-direction:column; align-items:flex-start">
                <div style="width:100%; display:flex; justify-content:space-between">
                    <span class="t-label">Confidence</span>
                    <span class="t-val" style="color:${getConfidenceColor(data.confidence)}">${(data.confidence * 100).toFixed(1)}%</span>
                </div>
                <div class="meter-rail">
                    <div class="meter-fill" style="width:${Math.max(5, data.confidence * 100)}%; background:${getConfidenceColor(data.confidence)}"></div>
                </div>
            </div>
        </div>
    `;

    // 2. ML Swarm (if available)
    if (ml) {
        html += `
            <div class="t-module">
                <div class="t-module-title">ML Swarm Analysis</div>
                <div class="t-data-row">
                    <span class="t-label">Player Intent</span>
                    <span class="t-val">${ml.intent.toUpperCase()}</span>
                </div>
                <div class="t-data-row">
                    <span class="t-label">Sentiment</span>
                    <span class="t-val">${ml.sentiment.toUpperCase()}</span>
                </div>
                <div class="t-data-row">
                    <span class="t-label">Emotion Detected</span>
                    <span class="t-val">${ml.player_emotion.toUpperCase()} (${(ml.emotion_intensity * 100).toFixed(0)}%)</span>
                </div>
                <div class="t-data-row">
                    <span class="t-label">Predicted Behavior</span>
                    <span class="t-val">${ml.predicted_action.toUpperCase()}</span>
                </div>
            </div>
        `;
    }

    // 3. Cognitive Engine (if used)
    if (isCognitive && data.debug) {
        const d = data.debug;
        html += `
            <div class="t-module">
                <div class="t-module-title">Right Hemisphere (Cognitive)</div>
                <div class="t-data-row">
                    <span class="t-label">Current Emotion</span>
                    <span class="t-val">${d.emotion_state || 'NEUTRAL'}</span>
                </div>
                <div class="t-data-row">
                    <span class="t-label">Pattern Match</span>
                    <span class="t-val">${d.pattern_matched || 'NONE'}</span>
                </div>
                <div class="t-data-row">
                    <span class="t-label">Active Modules</span>
                    <span class="t-val">${d.modules_executed ? d.modules_executed.length : 0}/15</span>
                </div>
            </div>
        `;
    }

    // 4. RAG sources (if provided)
    if (data.sources && data.sources.length > 0) {
        html += `
            <div class="t-module">
                <div class="t-module-title">Left Hemisphere (RAG)</div>
        `;
        data.sources.slice(0, 3).forEach((s, idx) => {
            html += `
                <div class="t-data-row" style="flex-direction:column; align-items:flex-start; margin-bottom:0.5rem">
                    <div style="width:100%; display:flex; justify-content:space-between">
                        <span class="t-label">Match #${idx+1}</span>
                        <span class="t-val" style="color:${getConfidenceColor(s.score)}">${(s.score * 100).toFixed(1)}%</span>
                    </div>
                    <span style="font-size:0.7rem; color:var(--text-muted); text-overflow:ellipsis; white-space:nowrap; overflow:hidden; width:100%">${s.pattern || 'Unknown syntax'}</span>
                </div>
            `;
        });
        html += `</div>`;
    }

    els.telemetryContent.innerHTML = html;
}

// Bootstrap
document.addEventListener('DOMContentLoaded', init);
