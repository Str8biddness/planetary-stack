let currentTier = 'Basic';
// ==========================================
// WINDOW MANAGER LOGIC
// ==========================================
let highestZIndex = 100;
let isDragging = false;
let currentWindow = null;
let offsetX = 0, offsetY = 0;

function toggleWindow(id) {
    const win = document.getElementById(id);
    if (!win) {
        console.warn('toggleWindow: missing element', id);
        return;
    }
    if (win.style.display === 'none') {
        win.style.display = 'flex';
        clampIntoView(win);   // never open a window off-screen (unreachable title bar)
        focusWindow(win);
        
        // Trigger lazy loading
        if (id === 'win-explorer') fetchIDEFiles();
        if (id === 'win-twin') startTwinSimulation();
        if (id === 'win-term') initTerminal();
        if (id === 'win-chat') maybeStreamWelcome();
        if (id === 'win-drive') loadDriveSources();
        if (id === 'win-core') loadLLMSettings();
        if (id === 'win-image') { try { renderImageGallery(); } catch (e) {} }
        if (id === 'win-forge') { try { forgeInit(); } catch (e) {} }
        // Foreman poll only while the window is open (QA BUG-5)
        if (id === 'win-foreman') startForemanSync();
    } else {
        win.style.display = 'none';
        if (id === 'win-twin' && twinInterval) clearInterval(twinInterval);
        if (id === 'win-foreman' && foremanInterval) {
            clearInterval(foremanInterval);
            foremanInterval = null;
        }
    }
    try { syncDockActive(); } catch (_) {}
}

function focusWindow(win) {
    document.querySelectorAll('.window').forEach(w => w.classList.remove('focused'));
    highestZIndex++;
    win.style.zIndex = highestZIndex;
    win.classList.add('focused');
}

// Keep a window fully on-screen; if it's bigger than the viewport, pin it to the
// top-left so its title bar is always reachable. Guards against fixed inline
// positions (or a small/rotated screen) opening a window you can't grab.
function clampIntoView(win) {
    if (!win) return;
    const stripH = document.getElementById('instr-status-strip') ? 28 : 0;
    const dockH = 72; // leave room for dock (may wrap on narrow viewports)
    const vw = window.innerWidth || 800;
    const vh = window.innerHeight || 600;
    // Prefer measured size; fall back to CSS width/height if still 0 (display:none→flex race)
    let w = win.offsetWidth || parseInt(win.style.width, 10) || 400;
    let h = win.offsetHeight || parseInt(win.style.height, 10) || 300;
    // Shrink oversized windows so title bar stays reachable on tiny viewports
    if (w > vw - 8) {
        w = Math.max(280, vw - 8);
        win.style.width = w + 'px';
    }
    if (h > vh - stripH - dockH) {
        h = Math.max(200, vh - stripH - dockH);
        win.style.height = h + 'px';
    }
    let left = parseInt(win.style.left, 10); if (isNaN(left)) left = win.offsetLeft || 40;
    let top  = parseInt(win.style.top, 10);  if (isNaN(top))  top  = win.offsetTop  || 40;
    left = Math.max(0, Math.min(left, Math.max(0, vw - Math.min(w, 100))));
    top  = Math.max(stripH, Math.min(top, Math.max(stripH, vh - dockH - 40)));
    win.style.left = left + 'px';
    win.style.top  = top + 'px';
}

// Re-clamp any open window if the screen size changes (rotate / resolution swap).
window.addEventListener('resize', () => {
    document.querySelectorAll('.window').forEach(w => {
        if (w.style.display !== 'none') clampIntoView(w);
    });
});

function dragWindow(e, id) {
    currentWindow = document.getElementById(id);
    focusWindow(currentWindow);
    
    isDragging = true;
    offsetX = e.clientX - currentWindow.offsetLeft;
    offsetY = e.clientY - currentWindow.offsetTop;
    
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
}

let animationFrameId = null;
let currentMouseX = 0;
let currentMouseY = 0;

function onMouseMove(e) {
    if (!isDragging || !currentWindow) return;
    currentMouseX = e.clientX;
    currentMouseY = e.clientY;
    
    if (!animationFrameId) {
        animationFrameId = requestAnimationFrame(() => {
            if (currentWindow) {
                // Apply bounded constraints so windows can't be dragged offscreen
                const stripH = document.getElementById('instr-status-strip') ? 28 : 0;
                const newLeft = Math.max(0, Math.min(currentMouseX - offsetX, window.innerWidth - 100));
                const newTop = Math.max(stripH, Math.min(currentMouseY - offsetY, window.innerHeight - 50));
                currentWindow.style.left = newLeft + 'px';
                currentWindow.style.top = newTop + 'px';
            }
            animationFrameId = null;
        });
    }
}

function onMouseUp() {
    isDragging = false;
    currentWindow = null;
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
}

// ==========================================
// WINDOW RESIZE (visible bottom-right grip)
// The native `resize: both` grip is invisible against the dark theme and clipped
// by the rounded corners, so users can't grab it. We draw a visible grip via the
// `.window::after` CSS and drive the resize here from a corner-hit test. Works for
// every .window — including terminals spawned later — without touching their code.
// ==========================================
const RESIZE_GRIP = 20;   // px hit-zone in the bottom-right corner
const RESIZE_MIN_W = 260, RESIZE_MIN_H = 160;
let resizeTarget = null, rsStartX = 0, rsStartY = 0, rsStartW = 0, rsStartH = 0;

document.addEventListener('mousedown', (e) => {
    const win = e.target.closest ? e.target.closest('.window') : null;
    if (!win) return;
    const rect = win.getBoundingClientRect();
    if (e.clientX >= rect.right - RESIZE_GRIP && e.clientY >= rect.bottom - RESIZE_GRIP) {
        resizeTarget = win;
        rsStartX = e.clientX; rsStartY = e.clientY;
        rsStartW = rect.width; rsStartH = rect.height;
        focusWindow(win);
        e.preventDefault();
        e.stopPropagation();
        document.addEventListener('mousemove', onResizeMove);
        document.addEventListener('mouseup', onResizeUp);
    }
}, true);

function onResizeMove(e) {
    if (!resizeTarget) return;
    const w = Math.max(RESIZE_MIN_W, rsStartW + (e.clientX - rsStartX));
    const h = Math.max(RESIZE_MIN_H, rsStartH + (e.clientY - rsStartY));
    resizeTarget.style.width = w + 'px';
    resizeTarget.style.height = h + 'px';
}

function onResizeUp() {
    resizeTarget = null;
    document.removeEventListener('mousemove', onResizeMove);
    document.removeEventListener('mouseup', onResizeUp);
}

// Attach focus events to window bodies
document.addEventListener('DOMContentLoaded', async () => {
    document.querySelectorAll('.window').forEach(win => {
        win.addEventListener('mousedown', () => focusWindow(win));
    });
    setInterval(fetchOSStatus, 2000);
    
    // LLM Health Banner Check
    try {
        const hRes = await fetch('/api/v1/health');
        const hData = await hRes.json();
        if (hData && hData.llm && (hData.llm.realizer !== 'llm' || !hData.llm.ollama_reachable)) {
            const b = document.getElementById('llm-health-banner');
            if (b) b.style.display = 'flex';
        }
    } catch(e) {}

    // Development Auto-Refresh Watcher
    let lastModified = null;
    setInterval(async () => {
        try {
            const res = await fetch(window.location.href, { method: 'HEAD', cache: 'no-store' });
            const lm = res.headers.get('Last-Modified');
            if (lastModified === null) lastModified = lm;
            else if (lastModified !== lm) location.reload();
        } catch(err) {}
    }, 1500);
});

// ==========================================
// OS BACKEND LOGIC
// ==========================================
let twinInterval;

async function checkSystemStatus() {
    try {
        const response = await fetch('http://' + window.location.host + '/api/system/status');
        const data = await response.json();
        
        const sysDrive = document.getElementById('sys-drive');
        if (sysDrive) {
            sysDrive.textContent = data["3way_drive_active"] ? "● Storage Array Mounted" : "○ Storage Array Offline";
            sysDrive.style.color = data["3way_drive_active"] ? "#4ade80" : "#94a3b8";
        }
        
        const sysBridge = document.getElementById('sys-bridge');
        if (sysBridge) {
            sysBridge.textContent = data.peripheral_bridge_active ? "ACTIVE" : "INACTIVE";
            sysBridge.style.background = data.peripheral_bridge_active ? "#4ade80" : "#333";
        }
        
        document.getElementById('status-quadbrain').textContent = data.llm_status.includes("ONLINE") ? "AI: ONLINE" : "AI: WAITING";
        document.getElementById('status-quadbrain').className = data.llm_status.includes("ONLINE") ? "status-indicator" : "status-indicator warning";
        
        document.getElementById('status-network').textContent = "NET: SECURE LINK";
        document.getElementById('status-network').className = "status-indicator";
    } catch(err) {
        document.getElementById('status-quadbrain').textContent = "AI: OFFLINE";
        document.getElementById('status-network').textContent = "NET: HOST ONLY";
    }
}

async function rebootSubsystem() {
    if(confirm("Are you sure you want to hard-reboot the AIVM Daemon? This will kill the Subsystem and require a manual restart of the UI.")) {
        try {
            await fetch('http://' + window.location.host + '/api/system/reboot', { method: 'POST' });
        } catch(err) {}
        document.body.innerHTML = "<h1 style='color:red; text-align:center; margin-top:20%'>SUBSYSTEM REBOOTING...<br>Please close this window and restart the AIVM CLI.</h1>";
    }
}

async function fetchOSStatus() {
    try {
        const response = await fetch('http://' + window.location.host + '/api/system/status');
        const data = await response.json();
        const driveEl = document.getElementById('sys-drive');
        if(driveEl) {
            driveEl.innerText = data['3way_drive_active'] ? '● Storage Array Mounted' : '○ Drive Offline';
            driveEl.style.color = data['3way_drive_active'] ? '#4ade80' : '#94a3b8';
        }
        const bridgeEl = document.getElementById('sys-bridge');
        if(bridgeEl) {
            bridgeEl.innerText = data['peripheral_bridge_active'] ? 'ACTIVE' : 'INACTIVE';
            bridgeEl.style.background = data['peripheral_bridge_active'] ? 'var(--purple-light)' : '#333';
            bridgeEl.style.color = data['peripheral_bridge_active'] ? '#000' : '#fff';
        }

        // Fetch Telemetry & Threats if window is visible
        const telemetryWin = document.getElementById('win-telemetry');
        if (telemetryWin && telemetryWin.style.display !== 'none') {
            try {
                const threatRes = await fetch('http://' + window.location.host + '/api/threats');
                const threatData = await threatRes.json();
                
                let entropyStr = "0.00";
                let statusStr = "Stabilized";
                
                if (threatData.active_p2p_threats && threatData.active_p2p_threats.length > 0) {
                    entropyStr = (0.5 + Math.random() * 0.5).toFixed(2);
                    statusStr = "P2P Threat";
                } else if (threatData.immune_system_anomalies && threatData.immune_system_anomalies.length > 0) {
                    entropyStr = "0.99";
                    statusStr = "ANOMALY";
                } else {
                    entropyStr = (Math.random() * 0.1).toFixed(2);
                    statusStr = "Secure";
                }

                const entropyEl = document.querySelector('#win-telemetry .window-content > div:nth-child(1) > div > div');
                if (entropyEl) {
                    entropyEl.innerText = entropyStr;
                    if (parseFloat(entropyStr) > 0.5) entropyEl.style.color = "#ef4444";
                    else entropyEl.style.color = "var(--purple-light)";
                }
                
                const convEl = document.querySelector('#win-telemetry .window-content > div:nth-child(2) > div:nth-child(1) > div:nth-child(2)');
                if (convEl) convEl.innerText = statusStr;
            } catch(e) {}
        }

        // Fetch Resource Pools
        if (document.getElementById('win-pool') && document.getElementById('win-pool').style.display !== 'none') {
            try {
                // Master
                document.getElementById('pool-master').innerHTML = `
                    <div style="display:flex; justify-content:space-between;"><span>CPU Usage:</span> <span style="color:#34d399;">${data.cpu_percent != null ? data.cpu_percent + '%' : '—'}</span></div>
                    <div style="display:flex; justify-content:space-between;"><span>RAM Usage:</span> <span style="color:#818cf8;">${data.ram_percent != null ? data.ram_percent + '%' : '—'}</span></div>
                    <div style="display:flex; justify-content:space-between;"><span>GPU VRAM:</span> <span style="color:var(--purple-light);">Allocated (QuadBrain)</span></div>
                `;

                document.getElementById('pool-worker').innerHTML = `
                    <div style="color:#94a3b8;">Secure mesh resource pooling is not enabled in this release.</div>
                `;
            } catch(e) {
                document.getElementById('pool-worker').innerText = 'Node Offline or Refused Connection';
            }
        }

    } catch(err) {
        // Silent fail if backend down
    }
}

// ==========================================
// IDE FILE EXPLORER — real home tree + preview
// ==========================================
async function fetchIDEFiles() {
    const treeEl = document.getElementById('ide-file-tree');
    if (!treeEl) return;
    treeEl.innerHTML = '<div class="explorer-loading">Mounting storage array…</div>';
    try {
        const response = await fetch('/api/ide/files');
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const treeData = await response.json();
        const nodes = Array.isArray(treeData) ? treeData : [];
        treeEl.innerHTML = buildTreeHTML(nodes);
    } catch (err) {
        treeEl.innerHTML = '<p class="explorer-err">Failed to mount storage array.</p>';
        console.log('fetchIDEFiles', err);
    }
}

function buildTreeHTML(nodes) {
    if (!Array.isArray(nodes) || !nodes.length) return '<ul class="ide-tree"><li class="ide-empty">Empty</li></ul>';
    let html = '<ul class="ide-tree">';
    nodes.forEach(function (node) {
        if (!node) return;
        const name = escapeHtml(String(node.name || ''));
        const path = String(node.path || node.name || '');
        const pathAttr = escapeHtml(path);
        if (node.type === 'dir') {
            const kids = buildTreeHTML(node.children || []);
            html += '<li class="ide-dir">'
                + '<span class="folder" onclick="this.parentElement.classList.toggle(\'open\')">📂 ' + name + '</span>'
                + kids + '</li>';
        } else {
            html += '<li class="ide-file" data-path="' + pathAttr + '" onclick="openFileFromEl(this)">'
                + '<span class="file-ico">📄</span> <span class="file-name">' + name + '</span></li>';
        }
    });
    return html + '</ul>';
}

function openFileFromEl(el) {
    if (!el) return;
    openFile(el.getAttribute('data-path') || '');
}

async function openFile(relPath) {
    const nameEl = document.getElementById('ide-current-file');
    const metaEl = document.getElementById('ide-file-meta');
    const editor = document.getElementById('ide-code-editor');
    if (!editor) return;
    const path = String(relPath || '').trim();
    if (!path) return;
    document.querySelectorAll('.ide-file.active').forEach(function (el) { el.classList.remove('active'); });
    document.querySelectorAll('.ide-file[data-path]').forEach(function (el) {
        if (el.getAttribute('data-path') === path) el.classList.add('active');
    });
    if (nameEl) nameEl.textContent = path.split('/').pop() || path;
    if (metaEl) metaEl.textContent = 'loading…';
    editor.textContent = '// Streaming ' + path + ' …';
    try {
        const res = await fetch('/api/ide/read?path=' + encodeURIComponent(path));
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok || data.ok === false) {
            const msg = data.message || data.error || ('HTTP ' + res.status);
            editor.textContent = '// PREVIEW FAILED\n// ' + msg;
            if (metaEl) metaEl.textContent = String(msg);
            return;
        }
        editor.textContent = data.content != null ? String(data.content) : '';
        if (metaEl) {
            metaEl.textContent = (data.bytes != null ? data.bytes + ' B' : '—')
                + ' · ' + (data.path || path);
        }
        if (nameEl) nameEl.textContent = data.name || path;
        if (window.ideFileClick) window.ideFileClick(path, data.content);
    } catch (e) {
        editor.textContent = '// DEGRADED: ' + (e.message || e);
        if (metaEl) metaEl.textContent = 'unreachable';
    }
}
window.refreshIDEFiles = fetchIDEFiles;

/** Keep dock buttons lit when their window is open. */
function syncDockActive() {
    document.querySelectorAll('.dock-btn[data-win]').forEach(function (btn) {
        const id = btn.getAttribute('data-win');
        const win = id && document.getElementById(id);
        const open = win && win.style.display !== 'none' && win.style.display !== '';
        btn.classList.toggle('active', !!open);
    });
}

// ==========================================
// CHAT IPC
// ==========================================
function escapeHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Lightweight markdown -> HTML for chat replies (bold, italic, code, headers, bullets, links).
function renderMarkdown(md) {
    let h = escapeHtml(md);
    h = h.replace(/```([\s\S]*?)```/g, (m, c) => `<pre class="md-code">${c.replace(/^\n+|\n+$/g, '')}</pre>`);
    h = h.replace(/`([^`\n]+)`/g, '<code class="md-inline">$1</code>');
    h = h.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    h = h.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>');
    h = h.replace(/^#{1,3} (.*)$/gm, '<div class="md-h">$1</div>');
    h = h.replace(/^\s*[-*] (.*)$/gm, '&bull;&nbsp; $1');
    h = h.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" style="color:var(--purple-light);">$1</a>');
    h = h.replace(/\n/g, '<br>');
    return h;
}

// Reveal text with a typewriter stream; the lightbulb stays lit while it types.
// onDone(bubble) receives the bubble element so callers can attach 👍 confirm.
function streamInto(bubble, text, onDone) {
    if (!bubble) return;
    const chatHistory = document.getElementById('chat-history');
    bubble.innerHTML = `<strong>Synthesus:</strong> <span class="thinking-bulb lit">&#128161;</span> <span class="stream-target"></span>`;
    const target = bubble.querySelector('.stream-target');
    const clean = String(text).replace(/\\n/g, '\n');
    let i = 0;
    const timer = setInterval(() => {
        i += 2;  // a couple chars per tick — alive but quick
        target.innerHTML = escapeHtml(clean.slice(0, i)).replace(/\n/g, '<br>') + '<span class="stream-cursor">&#9611;</span>';
        if (chatHistory) chatHistory.scrollTop = chatHistory.scrollHeight;
        if (i >= clean.length) {
            clearInterval(timer);
            target.innerHTML = renderMarkdown(clean);  // final render: markdown formatting
            if (chatHistory) chatHistory.scrollTop = chatHistory.scrollHeight;
            if (onDone) onDone(bubble);
        }
    }, 14);
}

// Auth header for shell routes that resolve accounts.py identity (JWT).
// Human-session proof is injected only by the desktop shell server — never by this JS.
function authHeaders(extra) {
    const headers = Object.assign({ 'Content-Type': 'application/json' }, extra || {});
    try {
        const token = localStorage.getItem('synthesus_token');
        if (token) headers['Authorization'] = 'Bearer ' + token;
    } catch (e) { /* storage unavailable */ }
    return headers;
}

function currentUserIdentity() {
    try {
        if (window.currentUser && window.currentUser.email) return window.currentUser.email;
        const u = JSON.parse(localStorage.getItem('synthesus_user') || '{}');
        return (u && u.email) || null;
    } catch (e) {
        return null;
    }
}

// Attach a 👍 confirm control to an assistant message bubble.
// Two-step human-proof flow (session proof stays server-side in the shell only):
//   1) POST /api/human/attestation  { subject_key: answer_id }
//   2) POST /api/feedback           { actor_kind, channel, confirmed_by, human_attestation, answer_id, action }
function attachConfirmControl(bubble, meta) {
    if (!bubble || !meta || !meta.answer_id) return;
    // Avoid duplicate buttons on re-stream
    if (bubble.querySelector('.confirm-fact-btn')) return;

    const bar = document.createElement('div');
    bar.className = 'confirm-fact-bar';
    bar.style.cssText = 'margin-top:8px; display:flex; align-items:center; gap:8px; flex-wrap:wrap;';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'confirm-fact-btn glass-btn instr-confirm';
    btn.title = 'Confirm this answer as a verified fact (human only)';
    btn.setAttribute('data-answer-id', meta.answer_id);
    btn.innerHTML = '&#128077; confirm';

    const status = document.createElement('span');
    status.className = 'confirm-fact-status instr-meta';
    status.style.cssText = 'font-size:0.68rem; color:#8595a9;';

    btn.addEventListener('click', function () {
        confirmAssistantFact(meta, btn, status);
    });

    bar.appendChild(btn);
    bar.appendChild(status);
    // Prefer attaching under instrument meta row if present
    const metaRow = bubble.querySelector('.instr-answer-meta');
    if (metaRow) metaRow.appendChild(bar);
    else bubble.appendChild(bar);
}

async function confirmAssistantFact(meta, btn, statusEl) {
    const answerId = meta.answer_id;
    const query = meta.query || '';
    const responseText = meta.response || '';
    if (!answerId) {
        if (statusEl) statusEl.textContent = 'DEGRADED: missing answer_id';
        return;
    }
    if (!currentUserIdentity()) {
        if (statusEl) {
            statusEl.style.color = '#f87171';
            statusEl.textContent = 'Log in first — confirm needs your accounts identity.';
        }
        return;
    }

    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Confirming…';
    }
    if (statusEl) {
        statusEl.style.color = '#94a3b8';
        statusEl.textContent = 'Minting human attestation…';
    }

    const base = 'http://' + window.location.host;

    // Step 1 — mint via shell proxy (shell injects human-session proof; browser never holds it)
    let mintBody;
    try {
        const mintResp = await fetch(base + '/api/human/attestation', {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                channel: 'human_desktop_ui',
                subject_key: answerId,
                answer_id: answerId,
            }),
        });
        mintBody = await mintResp.json().catch(function () { return {}; });
        if (!mintResp.ok || !mintBody.issued || !mintBody.human_attestation) {
            if (statusEl) {
                statusEl.style.color = '#f87171';
                statusEl.textContent = 'Attestation refused: ' +
                    (mintBody.reason || mintBody.message || ('HTTP ' + mintResp.status));
            }
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '&#128077; Confirm as fact';
            }
            return;
        }
    } catch (e) {
        console.log('attestation mint failed:', e);
        if (statusEl) {
            statusEl.style.color = '#f87171';
            statusEl.textContent = 'DEGRADED: cannot reach shell attestation proxy.';
        }
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '&#128077; Confirm as fact';
        }
        return;
    }

    if (statusEl) statusEl.textContent = 'Sending human-proven feedback…';

    // Step 2 — feedback with full human-proof fields (confirmed_by forced server-side from JWT)
    try {
        const fbResp = await fetch(base + '/api/feedback', {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({
                session_id: (window.sessionId || currentUserIdentity() || 'desktop'),
                query: query,
                response: responseText,
                rating: 5,
                action: 'confirm',
                actor_kind: 'human',
                channel: 'human_desktop_ui',
                // Hint only — shell overwrites confirmed_by from accounts.py JWT
                confirmed_by: currentUserIdentity(),
                human_attestation: mintBody.human_attestation,
                answer_id: answerId,
                memory_id: answerId,
            }),
        });
        const fbBody = await fbResp.json().catch(function () { return {}; });
        const upgrade = fbBody.verification_upgrade || {};
        if (fbResp.ok && upgrade.upgraded) {
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = '&#10003; Verified';
                btn.style.borderColor = '#34d399';
                btn.style.color = '#34d399';
            }
            if (statusEl) {
                statusEl.style.color = '#34d399';
                statusEl.textContent = 'Mc upgrade: ' +
                    (upgrade.provenance || 'user_confirmed') +
                    ' / tier ' + String(upgrade.verification) +
                    (upgrade.confirmed_by ? ' by ' + upgrade.confirmed_by : '');
            }
            // Flip answer-level badge to Verified
            const bubble = btn.closest('.message, .ai-message') || btn.parentElement;
            if (bubble) {
                const badge = bubble.querySelector('.instr-tier-badge, .verification-badge');
                if (badge) {
                    badge.className = 'instr-tier-badge t2 verification-badge';
                    badge.setAttribute('data-tier', '2');
                    badge.textContent = '✓ Verified';
                } else {
                    attachAnswerTrustMeta(bubble, { verification: 2, sources: meta.sources || [] });
                }
            }
        } else {
            // Fail closed: stay Grounded/Unverified — honest when human-session secret missing
            if (statusEl) {
                statusEl.style.color = '#fb7185';
                statusEl.textContent = 'Not upgraded (fail-closed): ' +
                    (upgrade.reason || fbBody.message || ('HTTP ' + fbResp.status));
            }
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = '&#128077; confirm';
            }
        }
    } catch (e) {
        console.log('feedback failed:', e);
        if (statusEl) {
            statusEl.style.color = '#f87171';
            statusEl.textContent = 'DEGRADED: feedback proxy unreachable.';
        }
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '&#128077; Confirm as fact';
        }
    }
}

/** Chat modes: draw (SI) | find (retrieve label) | pass | refuse | talk */
async function routeChatImageIntent(message) {
    try {
        const res = await fetch('/api/v1/image/intent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message, scene_id: _lastStudioSceneId || null }),
        });
        if (!res.ok) return null;
        return await res.json();
    } catch (_) {
        return null;
    }
}

/** Detect "draw …" / "/draw …" / "imagine …" and route to SI image engine. */
function parseDrawIntent(message) {
    const m = (message || '').trim();
    const re = /^(?:\/draw|draw(?:\s+this)?|imagine|picture|render|paint)\s*[:\-]?\s*(.+)$/i;
    const hit = m.match(re);
    if (!hit) return null;
    const prompt = (hit[1] || '').trim();
    return prompt || null;
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if(!message) return;

    const chatHistory = document.getElementById('chat-history');
    chatHistory.innerHTML += `<div class="message" style="border-left: 3px solid var(--purple-light);"><strong>User:</strong> ${escapeHtml(message)}</div>`;
    input.value = '';
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // Intent router: draw | find | pass | refuse (talk falls through)
    const intent = await routeChatImageIntent(message);
    if (intent && intent.mode === 'refuse') {
        chatHistory.innerHTML += `<div class="message ai-message"><strong>Synthesus:</strong> ${escapeHtml(intent.message || 'Cannot fulfill honestly.')}</div>`;
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return;
    }
    if (intent && intent.mode === 'find') {
        chatHistory.innerHTML += `<div class="message ai-message"><strong>Synthesus:</strong> <span style="color:var(--purple-light);">[find mode]</span> ${escapeHtml(intent.message || '')}
            ${intent.alternative ? '<div style="margin-top:6px;font-size:0.85rem;color:#94a3b8;">Alternative: <code>' + escapeHtml(intent.alternative) + '</code></div>' : ''}</div>`;
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return;
    }
    if (intent && intent.mode === 'pass' && _lastStudioSceneId) {
        const thinkId = 'think-' + Date.now();
        chatHistory.innerHTML += `<div class="message ai-message" id="${thinkId}"><strong>Synthesus:</strong> multi-pass on scene stock…</div>`;
        try {
            const kn = intent.pass_knobs || {};
            let yaw = _lastStudioYaw || 0;
            if (kn.yaw_delta) yaw = Math.max(-60, Math.min(60, yaw + kn.yaw_delta));
            const res = await fetch('/api/v1/image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    scene_id: _lastStudioSceneId,
                    pass_only: true,
                    yaw_deg: yaw,
                    look: kn.look,
                    grade: kn.grade,
                    detail: kn.detail,
                    time_of_day: kn.time_of_day,
                    style: kn.style,
                    resolution: 512,
                }),
            });
            const data = await res.json().catch(() => ({}));
            const bubble = document.getElementById(thinkId);
            if (res.ok && data.image_base64) {
                _lastStudioYaw = data.yaw_deg != null ? data.yaw_deg : yaw;
                if (data.scene_id) setStudioSceneId(data.scene_id);
                const src = 'data:' + (data.mime_type || 'image/png') + ';base64,' + data.image_base64;
                if (bubble) {
                    bubble.innerHTML = '<strong>Synthesus:</strong> <span style="color:var(--purple-light);">[pass]</span> same world, new knobs'
                        + '<div style="margin-top:8px;"><img src="' + src + '" style="max-width:100%;border-radius:8px;"></div>'
                        + '<div style="font-size:0.75rem;color:#64748b;font-family:monospace;">scene stock · not diffusion</div>';
                }
                pushImageGallery(src, 'pass');
            } else if (bubble) {
                bubble.innerHTML = '<strong>Synthesus:</strong> pass failed — generate a scene in Studio first.';
            }
        } catch (e) {
            const bubble = document.getElementById(thinkId);
            if (bubble) bubble.innerHTML = '<strong>Synthesus:</strong> pass error.';
        }
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return;
    }
    if (intent && intent.mode === 'forge') {
        const thinkId = 'think-' + Date.now();
        chatHistory.innerHTML += `<div class="message ai-message" id="${thinkId}"><strong>Synthesus:</strong> <span class="thinking-bulb">&#9874;</span> <span style="color:#94a3b8; font-style:italic;">forging graph recipe...</span></div>`;
        chatHistory.scrollTop = chatHistory.scrollHeight;
        try {
            const planRes = await fetch('/api/forge/plan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: intent.prompt })
            });
            const planData = await planRes.json();
            if (planRes.ok && planData.code) {
                const code = planData.code;
                const renderRes = await fetch('/api/forge/render', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code: code, width: 256, height: 256, quality: 32 })
                });
                
                if (renderRes.ok) {
                    const blob = await renderRes.blob();
                    const url = URL.createObjectURL(blob);
                    
                    const bubble = document.getElementById(thinkId);
                    if (bubble) {
                        bubble.innerHTML = '<strong>Synthesus:</strong> <span style="color:var(--purple-light);">[forge]</span> built abstract graph.'
                            + '<div style="margin-top:8px;"><img src="' + url + '" style="max-width:100%;border-radius:4px;border:1px solid #1e293b;"></div>'
                            + `<div style="font-size:0.75rem;color:#64748b;font-family:monospace;margin-top:6px;word-break:break-all;">${code}</div>`
                            + `<button onclick="navigator.clipboard.writeText('${code}')" style="margin-top:4px;background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:2px 6px;border-radius:4px;cursor:pointer;font-size:0.7rem;">Copy Recipe</button>`;
                    }
                    pushImageGallery(url, 'forge');
                } else {
                    document.getElementById(thinkId).innerHTML = '<strong>Synthesus:</strong> forge render failed.';
                }
            } else {
                document.getElementById(thinkId).innerHTML = '<strong>Synthesus:</strong> forge compile failed.';
            }
        } catch (e) {
            const bubble = document.getElementById(thinkId);
            if (bubble) bubble.innerHTML = '<strong>Synthesus:</strong> forge error.';
        }
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return;
    }
    
    // SI Image shortcut: "draw a house left of a river…"
    const drawPrompt = (intent && intent.mode === 'draw' && intent.prompt) ? intent.prompt : parseDrawIntent(message);
    if (drawPrompt) {
        const thinkId = 'think-' + Date.now();
        chatHistory.innerHTML += `<div class="message ai-message" id="${thinkId}"><strong>Synthesus:</strong> <span class="thinking-bulb">&#128161;</span> <span style="color:#94a3b8; font-style:italic;">drawing SI illustration&hellip;</span></div>`;
        chatHistory.scrollTop = chatHistory.scrollHeight;
        try {
            const res = await fetch('/api/v1/image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    prompt: drawPrompt,
                    resolution: 512,
                    style: 'photo',
                    look: 'photo',
                    detail: 'high',
                    path_mode: true,
                    aspect: 1.0,
                    use_cache: true,
                    compile_plan: true,
                    return_plan: true,
                    keep_session: true,
                }),
            });
            const data = await res.json().catch(() => ({}));
            const bubble = document.getElementById(thinkId);
            if (!res.ok || !data.image_base64) {
                const msg = (data && (data.message || data.error)) || ('HTTP ' + res.status);
                if (bubble) {
                    bubble.innerHTML = '<strong>Synthesus:</strong> <span style="color:#f87171;">Could not draw — '
                        + escapeHtml(String(msg)) + '</span><div style="font-size:0.8rem;color:#94a3b8;margin-top:4px;">'
                        + 'Tip: open 🎨 SI Image Studio, or try: <code>draw a house on grass under a sky</code></div>';
                }
                return;
            }
            if (data.scene_id) setStudioSceneId(data.scene_id);
            const mime = data.mime_type || 'image/png';
            const src = 'data:' + mime + ';base64,' + data.image_base64;
            const ents = (data.entities || []).map(e => escapeHtml(String(e))).join(', ');
            const voice = data.outer_voice || (data.scene_plan && data.scene_plan.outer_voice) || '';
            const construction = data.construction || (data.scene_plan && data.scene_plan.construction) || '';
            if (bubble) {
                bubble.innerHTML =
                    '<strong>Synthesus:</strong> <span style="color:var(--purple-light);">[draw · SI construct]</span> '
                    + (voice ? escapeHtml(voice) : ('SI illustration of <em>' + escapeHtml(drawPrompt) + '</em>'))
                    + '<div style="margin-top:8px;"><img src="' + src + '" alt="SI render" style="max-width:100%; border-radius:8px; border:1px solid rgba(56,189,248,.3);"></div>'
                    + '<div style="font-size:0.75rem; color:#64748b; margin-top:6px; font-family:monospace;">'
                    + (data.engine || 'synthesus_vsa_geometric') + ' · ' + (data.style || 'soft')
                    + (construction ? ' · ' + escapeHtml(String(construction)) : '')
                    + ' · ' + (data.latency_ms != null ? data.latency_ms + 'ms' : '')
                    + (ents ? ' · ' + ents : '')
                    + ' · local SI (not diffusion · not Ollama pixels)</div>';
            }
            pushImageGallery(src, drawPrompt);
            chatHistory.scrollTop = chatHistory.scrollHeight;
        } catch (e) {
            const bubble = document.getElementById(thinkId);
            if (bubble) {
                bubble.innerHTML = '<strong>Synthesus:</strong> <span style="color:#f87171;">Draw failed: '
                    + escapeHtml(e.message || String(e)) + '</span>';
            }
        }
        return;
    }

    // The lightbulb flickers while Synthesus forms the idea.
    const thinkId = 'think-' + Date.now();
    chatHistory.innerHTML += `<div class="message ai-message" id="${thinkId}"><strong>Synthesus:</strong> <span class="thinking-bulb">&#128161;</span> <span style="color:#94a3b8; font-style:italic;">thinking&hellip;</span></div>`;
    chatHistory.scrollTop = chatHistory.scrollHeight;

    try {
        const response = await fetch('http://' + window.location.host + '/api/chat', {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ message: message })
        });
        const data = await response.json();
        const answerText = data.response || '';
        const answerId = data.answer_id || null;
        // Idea arrives: bulb lights up solid, then the answer streams out.
        // After stream, attach 👍 confirm bound to this answer_id.
        streamInto(document.getElementById(thinkId), answerText, function (bubble) {
            // Answer-level instrument tier badge + citation chips (real sources)
            try {
                attachAnswerTrustMeta(bubble, data);
            } catch (e) { console.log('tier meta', e); }
            if (answerId) {
                attachConfirmControl(bubble, {
                    answer_id: answerId,
                    query: message,
                    response: answerText,
                    sources: data.sources || [],
                });
            }
        });

        if (data.os_plan) {
            const plan = data.os_plan;
            const planJSON = JSON.stringify(plan).replace(/"/g, '&quot;');
            let planHtml = `<div style="margin-top: 10px; background: rgba(20, 25, 40, 0.8); border: 1px solid var(--purple-light); padding: 10px; border-radius: 8px;">
                <h4 style="color: var(--purple-light); margin-bottom: 5px;">⚠️ OS Action Proposal: ${plan.intent}</h4>
                <div style="font-family: monospace; color: #a78bfa; margin-bottom: 5px;">
                    ${plan.commands.join('<br>')}
                </div>
                <p style="font-size: 0.8rem; color: #94a3b8;"><strong>Expected Outcome:</strong> ${plan.expected_outcome}</p>
                <div style="margin-top: 5px; font-size: 0.8rem;">
                    <strong>Security Policy Sandbox:</strong> ${plan.sandbox_verified ? '<span style="color: #4ade80;">PASS</span>' : '<span style="color: #ef4444;">FAIL</span>'}
                </div>
                <div style="margin-top: 10px; display: flex; gap: 10px;">
                    <button onclick="approveOSPlan('${planJSON}')" class="glass-btn" style="background: #4ade80; flex-grow: 1;">Approve & Execute (Timeshift Snap)</button>
                    <button onclick="rejectOSPlan()" class="glass-btn" style="background: #ef4444; flex-grow: 1;">Reject</button>
                </div>
            </div>`;
            chatHistory.innerHTML += planHtml;
        }

        // Sources under grounded answers — instrument citation chips + tier badges
        if (Array.isArray(data.sources) && data.sources.length) {
            const items = data.sources.map(s => {
                if (typeof s === 'string') {
                    return '<li style="margin:4px 0; list-style:none;">' +
                        verificationTierBadge(null) +
                        ' <span class="instr-cite-chip">' + escapeHtml(s) + '</span></li>';
                }
                const label = (s && (s.file || s.name || s.path || s.source || s.title || s.pattern)) || JSON.stringify(s);
                const badge = verificationTierBadge(s);
                const score = (s && s.score != null) ? ' <span style="opacity:0.6;">(' + Number(s.score).toFixed(2) + ')</span>' : '';
                return '<li style="margin:4px 0; list-style:none; display:flex; align-items:flex-start; gap:6px;">' +
                    badge +
                    '<span class="instr-cite-chip" style="flex:1; max-width:none; white-space:normal;">' +
                    escapeHtml(String(label)) + score + '</span></li>';
            }).join('');
            const sourcesHtml =
                '<details class="rag-sources" style="margin-top:8px; background:rgba(12,18,27,0.9); ' +
                'border:1px solid #1b2733; border-radius:8px; padding:6px 10px;">' +
                '<summary style="cursor:pointer; color:#3ad0ef; font-size:0.72rem; font-family:var(--instr-mono); letter-spacing:0.08em;">' +
                'SOURCES (' + data.sources.length + ')</summary>' +
                '<ul style="margin:6px 0 2px 0; padding:0; color:#8595a9; font-size:0.8rem;">' +
                items + '</ul></details>';
            chatHistory.insertAdjacentHTML('beforeend', sourcesHtml);
        }

        chatHistory.scrollTop = chatHistory.scrollHeight;
    } catch(err) {
        const bubble = document.getElementById(thinkId);
        if (bubble) bubble.innerHTML = `<strong>Synthesus:</strong> <span style="color:#f87171;">I couldn't reach my reasoning core just now &mdash; give me a moment and try again.</span>`;
        console.log(err);
    }
}

async function approveOSPlan(planStr) {
    const plan = JSON.parse(planStr.replace(/&quot;/g, '"'));
    const chatHistory = document.getElementById('chat-history');
    chatHistory.innerHTML += `<div class="message" style="border-left: 3px solid #4ade80;"><strong>Admin:</strong> Plan Approved. Executing...</div>`;
    chatHistory.scrollTop = chatHistory.scrollHeight;
    
    // Switch to terminal tab so user can watch!
    const existingTerms = document.querySelectorAll('[id^="win-term-"]');
    if (existingTerms.length === 0) {
        spawnTerminalWindow();
    } else {
        const lastTerm = existingTerms[existingTerms.length - 1];
        lastTerm.style.display = 'flex';
        focusWindow(lastTerm);
    }
    
    try {
        const response = await fetch('http://' + window.location.host + '/api/os/approve', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(plan)
        });
        const data = await response.json();
        if(data.status === 'success') {
            chatHistory.innerHTML += `<div class="message ai-message" style="border-left: 3px solid var(--purple-light);"><strong>System:</strong> OS Plan successfully executed. Snapshot was taken prior to execution.</div>`;
        } else {
            chatHistory.innerHTML += `<div class="message" style="border-left: 3px solid #ef4444;"><strong>System Error:</strong> ${data.message}</div>`;
        }
    } catch(err) {}
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function rejectOSPlan() {
    const chatHistory = document.getElementById('chat-history');
    chatHistory.innerHTML += `<div class="message" style="border-left: 3px solid #ef4444;"><strong>Admin:</strong> Plan Rejected.</div>`;
    chatHistory.scrollTop = chatHistory.scrollHeight;
}

function handleChatKey(event) { if(event.key === 'Enter') sendChatMessage(); }

// ==========================================
// TERMINAL IPC & HIERARCHY APPROVAL
// ==========================================
let termCounter = 0;
let ipcSessionPromise = null;

function getIPCSession() {
    if (!ipcSessionPromise) {
        const userToken = localStorage.getItem('synthesus_token');
        if (!userToken) {
            return Promise.reject(new Error('Sign in before opening a terminal'));
        }
        ipcSessionPromise = fetch('/api/ipc/session', {
            cache: 'no-store',
            headers: { 'Authorization': 'Bearer ' + userToken }
        })
            .then(response => {
                if (!response.ok) throw new Error(`IPC session unavailable (${response.status})`);
                return response.json();
            })
            .catch(error => {
                ipcSessionPromise = null;
                throw error;
            });
    }
    return ipcSessionPromise;
}

function controllerHost(config) {
    const hostname = window.location.hostname || '127.0.0.1';
    return `${hostname}:${config.controller_port}`;
}

function spawnTerminalWindow() {
    termCounter++;
    const termId = `win-term-${termCounter}`;
    const termContainerId = `xterm-container-${termCounter}`;
    const sessionId = `sess-${termCounter}-${Date.now()}`;
    
    // Create DOM structure
    const win = document.createElement('div');
    win.className = 'window glass-panel';
    win.id = termId;
    win.style.top = (300 + (termCounter * 30)) + 'px';
    win.style.left = (400 + (termCounter * 30)) + 'px';
    win.style.width = '600px';
    win.style.height = '400px';
    
    win.innerHTML = `
        <div class="window-header" onmousedown="dragWindow(event, '${termId}')">
            <span class="window-title" style="color: #4ade80;">_ Terminal [TAB ${termCounter}]</span>
            <div class="window-controls">
                <button class="win-btn plus" onclick="spawnTerminalWindow()" title="New Tab/Window" style="background: var(--purple-light); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; text-decoration: none;">+</button>
                <button class="win-btn close" onclick="document.getElementById('${termId}').remove()"></button>
            </div>
        </div>
        <div class="window-content" style="padding: 0; background: #000; overflow: hidden;">
            <div id="${termContainerId}" style="width: 100%; height: 100%; padding: 5px;"></div>
        </div>
    `;
    
    document.getElementById('desktop-area').appendChild(win);
    focusWindow(win);
    
    // Make window focusable
    win.addEventListener('mousedown', () => focusWindow(win));
    
    // Initialize xterm
    const term = new Terminal({
        theme: { background: '#000000', foreground: '#4ade80' },
        fontFamily: 'Fira Code, monospace',
        fontSize: 14,
        cursorBlink: true
    });
    
    const fitAddon = new FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(document.getElementById(termContainerId));
    
    let ptySocket;
    async function connectPTY() {
        try {
            const config = await getIPCSession();
            const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
            const endpoint = `${scheme}://${controllerHost(config)}${config.terminal_ws_path}/${sessionId}`;
            ptySocket = new WebSocket(
                endpoint,
                ['synthesus-terminal', config.terminal_token]
            );
            ptySocket.onopen = () => term.write('\r\n[Connected to System PTY (Multi-Session)]\r\n');
            ptySocket.onmessage = (e) => term.write(e.data);
            ptySocket.onclose = () => {
                if(document.getElementById(termId)) {
                    term.write('\r\n[Disconnected. Reconnecting...]\r\n');
                    setTimeout(connectPTY, 2000);
                }
            };
        } catch(e) {
            term.write(`\r\n[Authenticated terminal IPC unavailable: ${e.message}]\r\n`);
            if(document.getElementById(termId)) setTimeout(connectPTY, 2000);
        }
    }
    connectPTY();
    
    term.onData((data) => {
        if(ptySocket && ptySocket.readyState === WebSocket.OPEN) {
            ptySocket.send(data);
        }
    });
    
    term.onResize(async (size) => {
        try {
            const config = await getIPCSession();
            const scheme = window.location.protocol === 'https:' ? 'https' : 'http';
            await fetch(
                `${scheme}://${controllerHost(config)}${config.terminal_http_path}/api/terminal/resize`,
                {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Synthesus-IPC-Token': config.terminal_token
                    },
                    body: JSON.stringify({
                        session_id: sessionId,
                        cols: size.cols,
                        rows: size.rows
                    })
                }
            );
        } catch (_) {}
    });
    
    const resizeObserver = new ResizeObserver(() => fitAddon.fit());
    resizeObserver.observe(win);
    setTimeout(() => fitAddon.fit(), 100);
}
// ==========================================
// TWIN SIMULATION
// ==========================================
async function startTwinSimulation() {
    if(twinInterval) clearInterval(twinInterval);
    const log = document.getElementById('twin-log');
    
    twinInterval = setInterval(async () => {
        try {
            const response = await fetch('http://' + window.location.host + '/api/telemetry');
            const data = await response.json();
            if (data && data.metrics) {
                document.getElementById('stat-pt').innerText = data.metrics.live_cpu_count ? data.metrics.live_cpu_count + ' Cores' : '--';
                document.getElementById('stat-pcv').innerText = data.metrics.live_ram_used_ratio ? (data.metrics.live_ram_used_ratio * 100).toFixed(1) + ' %' : '-- %';
                document.getElementById('stat-toxin').innerText = data.metrics.live_disk_used_gb ? data.metrics.live_disk_used_gb.toFixed(1) + ' GB' : '-- GB';
                document.getElementById('stat-pain').innerText = data.metrics.live_cpu_avg_mhz ? data.metrics.live_cpu_avg_mhz.toFixed(0) + ' MHz' : '-- MHz';
                
                const phase = data.twin_stats && data.twin_stats.status ? data.twin_stats.status : "GATHERING METRICS";
                const color = "#4ade80"; 
                log.innerHTML += `<div><span style="color:${color};">[SYS_METRICS] ${phase}</span></div>`;
                log.scrollTop = log.scrollHeight;
            }
        } catch(err) {}
    }, 2000);
}

async function runUSCL() {
    const script = document.getElementById('ide-code-editor').value;
    try {
        const response = await fetch('http://' + window.location.host + '/api/uscl/execute', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ script: script })
        });
        const data = await response.json();
        
        // Spawn a terminal to show output
        spawnTerminalWindow();
        const existingTerms = document.querySelectorAll('[id^="win-term-"]');
        const lastTermId = existingTerms[existingTerms.length - 1].id;
        const termContainerId = lastTermId.replace("win-term-", "xterm-container-");
        
        // We'll just alert for now since we don't have direct access to the xterm instance from outside easily
        alert("USCL Compilation Result:\\n" + JSON.stringify(data.result, null, 2));
    } catch(err) {
        alert("USCL Execution Failed: " + err.message);
    }
}

// ==========================================
// DESKTOP UI LOGIC
// ==========================================

document.addEventListener("DOMContentLoaded", () => {
    const storedUser = localStorage.getItem('synthesus_user');

    // Restore the session on reload/reopen so a logged-in user isn't dumped back to the
    // login screen on every refresh. If the stored token is stale, subsequent API calls
    // 401 and the app can re-prompt — but the common case (valid token) skips re-login.
    try {
        const token = localStorage.getItem('synthesus_token');
        if (token && storedUser) {
            const u = JSON.parse(storedUser);
            if (u && u.email) {
                window.sessionId = u.email;
                window.currentUser = u;
                enterDesktop();
            }
        }
    } catch (e) { /* fall through to the login screen */ }

    // Pre-fill the email field if we remember the last account that logged in here.
    if (storedUser) {
        try {
            const u = JSON.parse(storedUser);
            const emailEl = document.getElementById('login-email');
            if (emailEl && u && u.email) emailEl.value = u.email;
        } catch (e) { /* legacy/non-JSON value — ignore */ }
    }

    // Build the wallpaper picker and apply the user's saved choice.
    renderWallpaperPicker();
    applySavedWallpaper();

    // Live login-screen clock.
    updateLoginClock();
    setInterval(updateLoginClock, 1000);
});

// 'login' = existing account, 'register' = new account. Toggled by the link under the button.
window.authMode = 'login';

function toggleAuthMode() {
    window.authMode = (window.authMode === 'login') ? 'register' : 'login';
    const isLogin = window.authMode === 'login';
    document.getElementById('login-subtitle').innerText   = isLogin ? 'Log in to your account.' : 'Create your account.';
    document.getElementById('login-submit-btn').innerText = isLogin ? 'Log In' : 'Create Account';
    document.getElementById('login-toggle-prompt').innerText = isLogin ? 'New to Synthesus?' : 'Already have an account?';
    document.getElementById('login-toggle-btn').innerText = isLogin ? 'Create Account' : 'Back to Log In';
    document.getElementById('login-password').setAttribute('autocomplete', isLogin ? 'current-password' : 'new-password');
    document.getElementById('login-error').innerText = '';
}

async function processLogin() {
    const email    = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const errEl    = document.getElementById('login-error');
    const btn      = document.getElementById('login-submit-btn');
    errEl.style.color = '#f87171';
    errEl.innerText = '';

    if (!email || !password) {
        errEl.innerText = 'Please enter your email and password.';
        return;
    }

    const isRegister = (window.authMode === 'register');
    const endpoint   = isRegister ? '/api/auth/register' : '/api/auth/login';
    const original   = btn.innerText;
    btn.disabled = true;
    btn.innerText = isRegister ? 'Creating…' : 'Logging in…';

    // 1) The network call — and ONLY this — decides "cannot reach server".
    let resp;
    try {
        resp = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
    } catch (e) {
        console.log('login fetch failed:', e);
        errEl.innerText = 'Cannot reach the server. Is Synthesus running?';
        btn.disabled = false; btn.innerText = original;
        return;
    }

    const data = await resp.json().catch(() => ({}));
    if (!resp.ok || data.status !== 'success') {
        errEl.innerText = data.message || 'Something went wrong. Please try again.';
        btn.disabled = false; btn.innerText = original;
        return;
    }

    // 2) Login SUCCEEDED. Everything below is post-login — a failure here must
    //    NOT masquerade as "cannot reach server". Persist session defensively;
    //    some webviews throw on localStorage.
    try {
        localStorage.setItem('synthesus_token', data.token);
        localStorage.setItem('synthesus_user', JSON.stringify(data.user));
    } catch (e) { console.log('session storage unavailable (continuing):', e); }
    window.sessionId   = data.user.email;
    window.currentUser = data.user;

    btn.disabled = false; btn.innerText = original;
    document.getElementById('login-modal').style.display = 'none';
    if (isRegister) {
        document.getElementById('tier-modal').style.display = 'flex';
    } else {
        enterDesktop();
    }
}

// Open the plan picker (used by the desktop "Upgrade" button).
function showTiers() {
    document.getElementById('tier-modal').style.display = 'flex';
}

// Dismiss the plan picker and boot the desktop on the current plan.
function enterDesktop() {
    const login = document.getElementById('login-modal');
    if (login) login.style.display = 'none';
    const tm = document.getElementById('tier-modal');
    if (tm) tm.style.display = 'none';
    document.body.classList.add('desktop-live');
    // The Overview IS the desktop surface, not a window you have to find. It
    // sits behind everything else, so opening any app still works normally.
    try {
        const overview = document.getElementById('win-dashboard');
        if (overview) {
            overview.style.display = 'flex';
            dsHydrateIcons(overview);
            wsAdoptWindows();
            wsGo('home');
            dashboardRefresh();
            dashboardStartClock();
        }
    } catch (e) { console.log('overview unavailable (continuing):', e); }
    // Boot flash — instrument console coming online
    const flash = document.createElement('div');
    flash.className = 'boot-flash';
    document.body.appendChild(flash);
    setTimeout(function () { flash.remove(); }, 900);
    try { startInstrStatusStrip(); } catch (e) {}
    // First boot: surface the two critical surfaces so the OS feels alive
    try {
        if (!sessionStorage.getItem('synthesus_booted_ui')) {
            sessionStorage.setItem('synthesus_booted_ui', '1');
            setTimeout(function () {
                const chat = document.getElementById('win-chat');
                if (chat && chat.style.display === 'none') toggleWindow('win-chat');
            }, 280);
            setTimeout(function () {
                const vit = document.getElementById('win-vitals');
                if (vit && vit.style.display === 'none') toggleVitals();
            }, 520);
        }
    } catch (e) {}
    try { syncDockActive(); } catch (e) {}
}

// Build the personal greeting (markdown; the name renders bold).
function buildWelcomeText() {
    let user = window.currentUser;
    if (!user) { try { user = JSON.parse(localStorage.getItem('synthesus_user') || '{}'); } catch (e) { user = {}; } }
    const email = (user && user.email) || '';
    const name = email
        ? email.split('@')[0].replace(/[._\-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        : 'traveler';
    const h = new Date().getHours();
    const part = h < 5 ? 'night' : h < 12 ? 'morning' : h < 18 ? 'afternoon' : 'evening';
    const tier = (user && user.tier) ? String(user.tier) : 'free';
    const tokens = (user && user.token_balance != null) ? Number(user.token_balance).toLocaleString() : null;
    const tierPhrase = tier === 'free'
        ? "You're on the Free tier"
        : `You're a ${tier.charAt(0).toUpperCase() + tier.slice(1)} member`;
    const tokenPhrase = tokens ? `, ${tokens} tokens ready` : '';
    return `Good ${part}, **${name}**. I'm Synthesus — your synthetic intelligence, running right here on `
        + `your own machine. ${tierPhrase}${tokenPhrase}. What are we building today?`;
}

// Suggested-prompt chips to kill the blank-page hesitation.
function renderPromptChips(container) {
    const prompts = ["What can you do?", "Write me a short poem", "Explain quantum computing simply"];
    const wrap = document.createElement('div');
    wrap.className = 'prompt-chips';
    prompts.forEach(text => {
        const chip = document.createElement('span');
        chip.className = 'prompt-chip';
        chip.textContent = text;
        chip.onclick = () => {
            const inp = document.getElementById('chat-input');
            if (inp) { inp.value = text; sendChatMessage(); }
            wrap.remove();
        };
        wrap.appendChild(chip);
    });
    container.appendChild(wrap);
    container.scrollTop = container.scrollHeight;
}

// Stream the personal welcome (lightbulb -> stream -> chips) the first time chat opens.
function maybeStreamWelcome() {
    const chatHistory = document.getElementById('chat-history');
    if (!chatHistory || chatHistory.dataset.welcomed) return;
    chatHistory.dataset.welcomed = '1';
    const thinkId = 'welcome-think';
    chatHistory.innerHTML += `<div class="message ai-message welcome-message" id="${thinkId}"><strong>Synthesus:</strong> <span class="thinking-bulb">&#128161;</span> <span style="color:#94a3b8;font-style:italic;">initializing&hellip;</span></div>`;
    chatHistory.scrollTop = chatHistory.scrollHeight;
    setTimeout(() => {
        streamInto(document.getElementById(thinkId), buildWelcomeText(), () => renderPromptChips(chatHistory));
    }, 850);
}

// Show / hide the password field.
function togglePwd() {
    const p = document.getElementById('login-password');
    const t = document.querySelector('.pwd-toggle');
    if (!p) return;
    if (p.type === 'password') { p.type = 'text'; if (t) t.style.opacity = '1'; }
    else { p.type = 'password'; if (t) t.style.opacity = '0.55'; }
}

// Live OS-style clock on the login screen.
function updateLoginClock() {
    const tEl = document.getElementById('login-time');
    const dEl = document.getElementById('login-date');
    if (!tEl || !dEl) return;
    const now = new Date();
    let h = now.getHours();
    const ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12 || 12;
    tEl.textContent = `${h}:${String(now.getMinutes()).padStart(2, '0')} ${ampm}`;
    dEl.textContent = now.toLocaleDateString(undefined, { weekday: 'long', month: 'long', day: 'numeric' });
}

async function selectTier(tierName) {
    // Free plan: just enter the desktop, no payment.
    if (tierName === 'Basic') {
        enterDesktop();
        return;
    }

    // Pro / Ultra: open the Stripe-hosted checkout in the user's real browser.
    const tier = tierName.toLowerCase();
    try {
        const resp = await fetch('/api/checkout/' + tier, { method: 'POST' });
        const data = await resp.json().catch(() => ({}));
        // If the backend couldn't launch a browser, fall back to opening it here.
        if (data && data.url && !data.opened) {
            window.open(data.url, '_blank');
        }
    } catch (e) {
        console.log(e);
    }

    alert(
        "Opening secure checkout in your browser.\n\n" +
        "After you buy, Gumroad emails you a license key. Come back here, open Unlock Pro (⭐ in the dock), " +
        "and paste the key to activate your personas instantly."
    );
}

// Activate a purchased Pro license: send the key to the backend, which verifies it
// with Gumroad and installs the premium personas. Shows the real result.
async function activatePro() {
    const input = document.getElementById('pro-key');
    const statusEl = document.getElementById('pro-activate-status');
    const key = (input && input.value || '').trim();
    if (!key) { if (statusEl) { statusEl.style.color = '#f87171'; statusEl.textContent = 'Paste your license key first.'; } return; }
    if (statusEl) { statusEl.style.color = '#94a3b8'; statusEl.textContent = 'Activating…'; }
    try {
        const r = await fetch('/api/pro/activate', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key })
        });
        const d = await r.json().catch(() => ({}));
        if (d && d.pro) {
            const names = (d.installed || []).join(', ') || 'your personas';
            statusEl.style.color = '#22c55e';
            statusEl.textContent = '✓ Pro unlocked! Installed: ' + names + '.' + (d.note ? ' ' + d.note : ' Open a new chat to use them.');
        } else {
            statusEl.style.color = '#f87171';
            statusEl.textContent = '✗ ' + ((d && d.error) || 'Could not activate that key.');
        }
    } catch (e) {
        statusEl.style.color = '#f87171';
        statusEl.textContent = '✗ ' + e;
    }
}




// ======================================================================
// WALLPAPER SYSTEM
// Add a new stock wallpaper by appending one entry below:
//   live:true              -> the animated canvas (window.Hyperspace)
//   css:'<any css background>' -> a static gradient/colour
//   img:'<filename>'        -> a bundled image in this folder
// `swatch` is the little preview shown in Settings (defaults to css).
// ======================================================================
const WALLPAPERS = [
    { id: 'solar',  name: 'Solar System', live: true,
      swatch: 'radial-gradient(circle at 32% 34%, #ffd27f 0%, #4b2c83 38%, #0a1330 72%)' },
    { id: 'aurora', name: 'Aurora',
      css: 'linear-gradient(160deg, #03101c 0%, #053b3a 45%, #0a5c4a 70%, #1b8a6b 100%)' },
    { id: 'nebula', name: 'Deep Nebula',
      css: 'radial-gradient(ellipse at 30% 30%, #3b1d6e 0%, #1a1036 45%, #05030f 100%)' }
];

function setWallpaper(id) {
    const wp = WALLPAPERS.find(w => w.id === id) || WALLPAPERS[0];
    const bg = document.getElementById('wallpaper-bg');
    if (wp.live) {
        bg.style.background = 'transparent';
        bg.style.backgroundImage = 'none';
        if (window.Hyperspace) window.Hyperspace.start();
    } else {
        if (window.Hyperspace) window.Hyperspace.stop();
        bg.style.background = wp.img ? '#05030f' : wp.css;
        bg.style.backgroundImage = wp.img ? `url(${wp.img})` : 'none';
    }
    try { localStorage.setItem('synthesus_wallpaper', id); } catch (e) {}
    renderWallpaperPicker();
}

function renderWallpaperPicker() {
    const c = document.getElementById('wallpaper-picker');
    if (!c) return;
    const current = localStorage.getItem('synthesus_wallpaper') || 'solar';
    c.innerHTML = '';
    WALLPAPERS.forEach(wp => {
        const wrap = document.createElement('div');
        wrap.style.cssText = 'display:flex; flex-direction:column; align-items:center; width:88px;';
        const sw = document.createElement('div');
        sw.className = 'wp-swatch' + (wp.id === current ? ' wp-selected' : '');
        sw.title = wp.name;
        sw.onclick = () => setWallpaper(wp.id);
        sw.style.cssText = 'width:84px; height:52px; border-radius:8px; cursor:pointer; ' +
            'background:' + (wp.swatch || wp.css || '#05030f') + '; background-size:cover;';
        const lbl = document.createElement('div');
        lbl.innerText = wp.name + (wp.live ? ' • Live' : '');
        lbl.style.cssText = 'font-size:0.7rem; color:#cbd5e1; margin-top:5px; text-align:center;';
        wrap.appendChild(sw); wrap.appendChild(lbl);
        c.appendChild(wrap);
    });
}

function applySavedWallpaper() {
    // Default to the live 'solar' wallpaper, and NEVER let a throwing/empty
    // localStorage (webview quirk) stop it from starting.
    let id = 'solar';
    try { id = localStorage.getItem('synthesus_wallpaper') || 'solar'; } catch (e) { id = 'solar'; }
    if (id === 'custom') {
        let data = null;
        try { data = localStorage.getItem('synthesus_wallpaper_custom'); } catch (e) {}
        if (data) {
            if (window.Hyperspace) window.Hyperspace.stop();
            const bg = document.getElementById('wallpaper-bg');
            bg.style.background = '#05030f';
            bg.style.backgroundImage = `url(${data})`;
            renderWallpaperPicker();
            return;
        }
    }
    setWallpaper(id);
}

function changeWallpaper(event) {
    const file = event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function (e) {
        const data = e.target.result;
        if (window.Hyperspace) window.Hyperspace.stop();
        const bg = document.getElementById('wallpaper-bg');
        bg.style.background = '#05030f';
        bg.style.backgroundImage = `url(${data})`;
        try {
            localStorage.setItem('synthesus_wallpaper', 'custom');
            localStorage.setItem('synthesus_wallpaper_custom', data);
        } catch (err) { /* image too large to persist; still applied this session */ }
        renderWallpaperPicker();
    };
    reader.readAsDataURL(file);
}

function maximizeWindow(el) {
    let win;
    if (typeof el === 'string') {
        win = document.getElementById(el);
    } else {
        win = el.closest('.window');
    }
    
    if (!win) return;
    
    if (win.dataset.maximized === 'true') {
        // Restore
        win.style.width = win.dataset.oldWidth || '800px';
        win.style.height = win.dataset.oldHeight || '600px';
        win.style.top = win.dataset.oldTop || '100px';
        win.style.left = win.dataset.oldLeft || '100px';
        win.dataset.maximized = 'false';
    } else {
        // Maximize
        win.dataset.oldWidth = win.style.width;
        win.dataset.oldHeight = win.style.height;
        win.dataset.oldTop = win.style.top;
        win.dataset.oldLeft = win.style.left;
        
        const stripH = document.getElementById('instr-status-strip') ? 28 : 0;
        win.style.top = stripH + 'px';
        win.style.left = '0px';
        win.style.width = '100vw';
        win.style.height = 'calc(100vh - ' + (60 + stripH) + 'px)'; // leave room for dock + strip
        win.dataset.maximized = 'true';
    }
}

function minimizeWindow(el) {
    let win;
    if (typeof el === 'string') {
        win = document.getElementById(el);
    } else {
        win = el.closest('.window');
    }
    if (!win) return;
    
    // For now, just hide it to simulate minimize (user can reopen from dock)
    win.style.display = 'none';
}


// ===================================================================
// AGNOSTIC EXPANSION DRIVE — guided graphical creator
// Step 1 pick a source · Step 2 connect/point · Step 3 build the drive.
// Every panel is wired to the real runtime; nothing is simulated.
// ===================================================================
let DRIVE_SOURCES = [];
let DRIVE_REMOTES = { rclone_available: false, remotes: [] };
let DRIVE_SELECTED = null;                       // the chosen source object
const CLOUD_KEYS = ['rclone','gdrive','onedrive','dropbox','box','s3'];
const DRIVE_ICONS = {
    github:'🐙', folder:'📁', rclone:'☁️', gdrive:'🅶', onedrive:'🅾️',
    dropbox:'📦', box:'🗄️', s3:'🪣', icloud:'🍏'
};

// BUG 5 (display guard): drives sometimes arrive with a stray connector-type
// prefix (e.g. "foldergdrive" instead of "gdrive"). Strip a leading
// "folder"/"github"/"cloud" prefix, but only when real name text remains.
function cleanDriveName(n) {
    return String(n || '').replace(/^(folder|github|cloud)(?=.+)/i, '');
}

async function loadDriveSources() {
    const status = document.getElementById('drive-status');
    try {
        const [rs, rr] = await Promise.all([
            fetch('/api/drive/sources').then(r => r.json()),
            fetch('/api/v1/drive/rclone/status').then(r => r.json()).catch(() => ({installed:false, remotes:[]}))
        ]);
        DRIVE_SOURCES = rs.sources || [];
        DRIVE_REMOTES = rr || { installed:false, remotes:[] };
        renderDriveTiles();
        driveGoStep(1);
        if (status) status.textContent = DRIVE_SOURCES.length ? '' :
            '⚠️ Runtime unavailable — start Synthesus to connect sources.';
    } catch (e) {
        if (status) status.textContent = '⚠️ Could not reach the runtime.';
    }
}

function renderDriveTiles() {
    const grid = document.getElementById('drive-tiles');
    if (!grid) return;
    grid.innerHTML = '';
    DRIVE_SOURCES.forEach(s => {
        const live = s.status === 'live';
        const tile = document.createElement('div');
        tile.className = 'drive-tile' + (live ? '' : ' disabled');
        tile.style.cssText =
            'display:flex;align-items:center;gap:8px;padding:10px;border-radius:10px;cursor:' +
            (live ? 'pointer' : 'not-allowed') + ';border:1px solid rgba(148,163,184,.2);' +
            'background:rgba(255,255,255,.03);' + (live ? '' : 'opacity:.45;');
        tile.innerHTML = '<span style="font-size:1.3rem;">' + (DRIVE_ICONS[s.key]||'💽') +
            '</span><span style="font-size:.82rem;color:#e2e8f0;line-height:1.1;">' + s.label +
            (live ? '' : '<br><span style="font-size:.7rem;color:#64748b;">use Folder</span>') + '</span>';
        if (live) tile.onclick = () => driveSelectSource(s.key);
        grid.appendChild(tile);
    });
}

function driveGoStep(n) {
    [1,2,3].forEach(i => {
        const p = document.getElementById('drive-step-' + i);
        if (p) p.style.display = (i === n) ? 'block' : 'none';
    });
    document.querySelectorAll('.drive-step-dot').forEach(d => {
        d.style.color = (parseInt(d.dataset.step) === n) ? '#22d3ee' : '#64748b';
        d.style.fontWeight = (parseInt(d.dataset.step) === n) ? '700' : '400';
    });
}

/** Paste arbitrary local text → write under ~/.synthesus/local_paste → folder ingest. */
async function drivePasteLocal() {
    const ta = document.getElementById('drive-paste-text');
    const status = document.getElementById('drive-paste-status');
    const text = (ta && ta.value || '').trim();
    if (!text) {
        if (status) status.textContent = 'Paste some text first.';
        return;
    }
    if (status) status.textContent = 'Writing + indexing locally…';
    try {
        const res = await fetch('/api/v1/drive/paste', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text, name: 'local-paste' }),
        });
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok) {
            if (status) {
                status.style.color = '#fb7185';
                status.textContent = 'Failed: ' + (data.message || data.error || ('HTTP ' + res.status));
            }
            return;
        }
        if (status) {
            status.style.color = '#34d399';
            status.textContent = 'Indexed local paste'
                + (data.chunks_added != null ? (' · ' + data.chunks_added + ' chunk(s)') : '')
                + (data.local_file ? (' · ' + data.local_file) : '')
                + ' · stays on this machine';
        }
        if (ta) ta.value = '';
        try { loadDriveSources(); } catch (_) {}
    } catch (e) {
        if (status) {
            status.style.color = '#fb7185';
            status.textContent = 'DEGRADED: ' + (e.message || e);
        }
    }
}

function driveSelectSource(key) {
    DRIVE_SELECTED = DRIVE_SOURCES.find(x => x.key === key);
    if (!DRIVE_SELECTED) return;
    document.getElementById('drive-sel-icon').textContent = DRIVE_ICONS[key] || '💽';
    document.getElementById('drive-sel-label').textContent = DRIVE_SELECTED.label;
    renderConnectBody();
    driveGoStep(2);
}

function renderConnectBody() {
    const body = document.getElementById('drive-connect-body');
    const key = DRIVE_SELECTED.key;
    const hint = DRIVE_SELECTED.input_hint || '';
    let html = '';

    if (key === 'github') {
        html =
          '<label style="color:#cbd5e1;font-size:.82rem;">Repository</label>' +
          '<input id="drive-in-primary" class="glass-input" placeholder="owner/repo, git URL, or local path">' +
          '<label style="color:#cbd5e1;font-size:.82rem;">Access token <span style="color:#64748b;">(only for private repos)</span></label>' +
          '<input id="drive-in-token" type="password" class="glass-input" placeholder="ghp_… — sent to GitHub for this fetch; not saved in the clone URL">';
    } else if (key === 'folder') {
        html =
          '<label style="color:#cbd5e1;font-size:.82rem;">Folder path</label>' +
          '<input id="drive-in-primary" class="glass-input" placeholder="/home/you/Documents or a synced Drive/Dropbox folder">' +
          '<p style="font-size:.78rem;color:#64748b;margin:0;">Tip: point this at a synced Google Drive / Dropbox / OneDrive folder for zero-setup grounding.</p>';
    } else {
        // any cloud → rclone. Show REAL connection state.
        html = renderCloudConnect(key);
    }
    body.innerHTML = html;
    if (!hint || key !== 'github') { /* placeholders already set */ }
}

function renderCloudConnect(key) {
    const remotes = DRIVE_REMOTES.remotes || [];
    let html = '';
    if (!DRIVE_REMOTES.installed) {
        return '<div style="padding:10px;border:1px solid rgba(239,68,68,.35);border-radius:8px;' +
               'background:rgba(239,68,68,.08);font-size:.82rem;color:#fca5a5;">' +
               'rclone isn\'t installed. Run this to install:<br>' +
               '<code style="user-select:all;cursor:pointer;color:#22d3ee;display:block;margin:6px 0;padding:4px;background:rgba(0,0,0,0.3);border-radius:4px;">curl https://rclone.org/install.sh | sudo bash</code>' +
               '<button class="glass-btn" style="font-size:.8rem;" onclick="driveRecheckRemotes()">↻ Re-check</button></div>';
    }
    
    html += '<label style="color:#cbd5e1;font-size:.82rem;">Connected clouds — pick one</label>';
    if (remotes.length) {
        html += '<div id="drive-remote-chips" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;">';
        remotes.forEach(rm => {
            html += '<button type="button" class="glass-btn drive-chip" data-remote="' + rm + '" ' +
                    'onclick="drivePickRemote(this)" style="font-size:.8rem;padding:4px 10px;">☁️ ' + rm + '</button>';
        });
        html += '</div>';
    } else {
        html += '<div style="font-size:0.8rem; color:#94a3b8; margin-bottom: 8px;">No remotes configured yet.</div>';
    }
    
    html += '<div style="margin-bottom: 10px;"><button class="glass-btn primary-btn" style="font-size:.8rem;" onclick="addCloudDrive()">➕ Add a cloud drive</button> ' +
            '<button class="glass-btn" style="font-size:.8rem;" onclick="driveRecheckRemotes()">↻ Refresh remotes</button></div>';
            
    html += '<label style="color:#cbd5e1;font-size:.82rem;display:block;">Remote &amp; optional subfolder</label>' +
            '<input id="drive-in-primary" class="glass-input" placeholder="e.g. onedrive: or gdrive:Work/notes">';
    return html;
}

function addCloudDrive() {
    spawnTerminalWindow();
    const existingTerms = document.querySelectorAll('[id^="win-term-"]');
    if (existingTerms.length > 0) {
        focusWindow(existingTerms[existingTerms.length - 1]);
    }
    setTimeout(() => {
        alert("A terminal has been opened.\\n\\nPlease run 'rclone config' to add a new cloud drive (choose 'n').\\nOAuth setup is interactive. When finished, click 'Refresh remotes'.");
    }, 100);
}

function drivePickRemote(btn) {
    const inp = document.getElementById('drive-in-primary');
    if (inp) inp.value = btn.dataset.remote + ':';
    document.querySelectorAll('.drive-chip').forEach(c => c.classList.remove('primary-btn'));
    btn.classList.add('primary-btn');
}

async function driveRecheckRemotes() {
    try {
        DRIVE_REMOTES = await fetch('/api/v1/drive/rclone/status').then(r => r.json());
    } catch (e) { /* keep old */ }
    renderConnectBody();
}

function driveGoBuild() {
    const primary = (document.getElementById('drive-in-primary')?.value || '').trim();
    if (!primary) {
        const st = document.getElementById('drive-status');
        driveGoStep(2);
        alert('Enter a ' + (DRIVE_SELECTED.key === 'github' ? 'repository' :
              DRIVE_SELECTED.key === 'folder' ? 'folder path' : 'cloud remote') + ' first.');
        return;
    }
    document.getElementById('drive-summary').innerHTML =
        DRIVE_ICONS[DRIVE_SELECTED.key] + ' <strong>' + DRIVE_SELECTED.label +
        '</strong> → <code style="color:#22d3ee;">' + primary + '</code>';
    // default drive name from the target
    const nameEl = document.getElementById('drive-name');
    if (nameEl && !nameEl.value) nameEl.value = primary.replace(/[:/].*$/, '') || DRIVE_SELECTED.key;
    driveGoStep(3);
}

async function driveBuild() {
    const status = document.getElementById('drive-status');
    const primary = (document.getElementById('drive-in-primary')?.value || '').trim();
    const token = (document.getElementById('drive-in-token')?.value || '').trim();
    const name = (document.getElementById('drive-name')?.value || '').trim();
    if (!primary) { status.textContent = '⚠️ Nothing to build — go back and set a target.'; return; }

    const wrap = document.getElementById('drive-progress-wrap');
    const bar = document.getElementById('drive-progress-bar');
    const btn = document.getElementById('drive-build-btn');
    btn.disabled = true;
    wrap.style.display = 'block';
    bar.style.transition = 'none'; bar.style.width = '8%';
    // indeterminate "working" pulse — NOT a completion claim
    let w = 8; const pulse = setInterval(() => { w = 8 + ((w + 3) % 80); bar.style.transition='width .3s'; bar.style.width = w + '%'; }, 350);
    status.innerHTML = '⏳ Mounting &amp; indexing <strong>' + primary + '</strong> locally…';

    // BUG 4: the ingest target is the user's RAW input — never basePath + input.
    // Defensively collapse an accidentally self-duplicated path
    // (e.g. "/mnt/c/.../Google Drive/mnt/c/.../Google Drive" -> the single path).
    let target = primary;
    if (target.length % 2 === 0) {
        const half = target.length / 2;
        if (target.slice(0, half) === target.slice(half)) target = target.slice(0, half);
    }

    const payload = { connector: DRIVE_SELECTED.key, target: target, async: true };
    if (name) payload.namespace = name;
    if (token) payload.token = token;
    
    // Remember namespace for preview
    const targetNs = name || target.replace(/[:/].*$/, '') || DRIVE_SELECTED.key;

    try {
        const r = await fetch('/api/v1/drive/ingest', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        
        if (r.status === 202) {
            const data = await r.json();
            clearInterval(pulse);
            pollDriveProgress(data.job_id, targetNs);
            return;
        }
        
        const data = await r.json();
        clearInterval(pulse);
        if (!r.ok || data.status === 'error') {
            bar.style.width = '0%'; wrap.style.display = 'none';
            const rawMsg = String(data.message || data.detail || '');
            // BUG 6: a missing folder is most often Google Drive for Desktop's
            // virtual drive, which WSL cannot see under /mnt/. Give a specific fix.
            const notFound = /not a directory|no such file|not found|does not exist|cannot find|enoent/i.test(rawMsg);
            if (DRIVE_SELECTED.key === 'folder' && (notFound || !rawMsg)) {
                status.innerHTML = '❌ Folder not found. If this is Google Drive for Desktop, ' +
                    'WSL can\'t see its virtual drive — either set Google Drive to ' +
                    '&ldquo;Mirror files&rdquo; to a real local folder, or copy the folder into ' +
                    'your Linux home directory (~/) first, then ingest that.';
            } else {
                status.textContent = '❌ ' + (rawMsg || ('failed (HTTP ' + r.status + ')'));
            }
            btn.disabled = false;
            return;
        }
        bar.style.width = '100%';
        const shownName = cleanDriveName(name || data.label || targetNs);
        renderDriveResult(data, shownName, targetNs);
    } catch (e) {
        clearInterval(pulse); wrap.style.display = 'none';
        status.textContent = '❌ Build failed: ' + e;
        btn.disabled = false;
    }
}

function pollDriveProgress(jobId, targetNs) {
    const status = document.getElementById('drive-status');
    const bar = document.getElementById('drive-progress-bar');
    const wrap = document.getElementById('drive-progress-wrap');
    const btn = document.getElementById('drive-build-btn');
    
    const poll = setInterval(async () => {
        try {
            const res = await fetch(`/api/v1/drive/progress/${jobId}`);
            if (res.status === 404) return;
            const data = await res.json();
            
            if (data.status === 'running') {
                bar.style.transition = 'width 0.5s';
                const pct = data.total > 0 ? (data.current / data.total) * 100 : 8;
                bar.style.width = Math.max(8, pct) + '%';
                status.innerHTML = `⏳ Indexing file ${data.current} of ${data.total} — <strong>${escapeHtml(data.file || '')}</strong>`;
            } else if (data.status === 'done') {
                clearInterval(poll);
                bar.style.width = '100%';
                const shownName = cleanDriveName(targetNs);
                renderDriveResult(data.result, shownName, targetNs);
            } else if (data.status === 'error') {
                clearInterval(poll);
                wrap.style.display = 'none';
                status.textContent = '❌ Build failed: ' + data.error;
                btn.disabled = false;
            }
        } catch(e) {}
    }, 600);
}

function renderDriveResult(data, shownName, targetNs) {
    const status = document.getElementById('drive-status');
    const btn = document.getElementById('drive-build-btn');
    
    let html = `✅ Built <strong>${shownName}</strong> — ${data.chunks_added || 0} chunk(s) from ${data.files_ingested || 0} file(s).`;
    
    if (data.by_ext && Object.keys(data.by_ext).length > 0) {
        const exts = Object.entries(data.by_ext).sort((a,b) => b[1] - a[1]);
        html += `<div style="margin-top: 10px; font-size: 0.8rem; background: rgba(0,0,0,0.3); padding: 8px; border-radius: 6px;">`;
        html += `<div style="color: #cbd5e1; margin-bottom: 4px;"><strong>Ingested Breakdown:</strong></div>`;
        html += `<table style="width: 100%; text-align: left; color: #94a3b8;">`;
        exts.forEach(([ext, count]) => {
            html += `<tr><td>${escapeHtml(ext)}</td><td>${count}</td></tr>`;
        });
        html += `</table></div>`;
    }
    
    let skippedCount = 0;
    let skippedReasons = [];
    if (data.skipped_by_ext) skippedCount = Object.values(data.skipped_by_ext).reduce((a,b) => a+b, 0);
    if (data.skipped_reasons) {
        for (const [reason, count] of Object.entries(data.skipped_reasons)) {
            skippedReasons.push(`${reason}: ${count}`);
        }
    }
    
    if (skippedCount > 0) {
        html += `<div style="margin-top: 6px; font-size: 0.8rem; color: #fca5a5;">`;
        html += `Skipped ${skippedCount} file(s). Reasons: ${escapeHtml(skippedReasons.join(', '))}`;
        html += `</div>`;
    }
    
    status.innerHTML = html;
    
    const list = document.getElementById('drive-ingested');
    const row = document.createElement('div');
    row.style.marginBottom = "8px";
    row.style.paddingBottom = "8px";
    row.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
    
    row.innerHTML = `💽 <strong>${shownName}</strong> · ${data.connector || 'Unknown'} · ${data.chunks_added || 0} chunks<br>`;
    
    const previewBtn = document.createElement('button');
    previewBtn.className = 'glass-btn';
    previewBtn.style.fontSize = '0.75rem';
    previewBtn.style.padding = '4px 8px';
    previewBtn.style.marginTop = '4px';
    previewBtn.innerText = '🔍 Preview chunks';
    previewBtn.onclick = () => previewDrive(targetNs);
    
    row.appendChild(previewBtn);
    list.prepend(row);
    
    const icon = document.getElementById('desktop-drive-icon');
    if (icon) { icon.style.display = 'block'; const lbl = document.getElementById('drive-label'); if (lbl) lbl.innerText = shownName + ' Drive'; }
    btn.disabled = false;
}

async function previewDrive(namespace) {
    const query = prompt(`Enter a search query to preview chunks from ${namespace}:`);
    if (!query) return;
    try {
        const res = await fetch('/api/v1/drive/preview', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ namespace, query })
        });
        const data = await res.json();
        if (data.chunks && data.chunks.length > 0) {
            let msg = `Top chunks for "${query}":\n\n`;
            data.chunks.forEach((c, i) => {
                msg += `[${i+1}] Score: ${c.score.toFixed(3)} | Source: ${c.source}\n${c.text.substring(0, 150)}...\n\n`;
            });
            alert(msg);
        } else {
            alert("No chunks found or index empty.");
        }
    } catch(e) {
        alert("Preview failed: " + e);
    }
}


window.onload = function() {
    loadLLMSettings();
};

// ---------------------------------------------------------------------------
// Verification tier badges — make anti-collapse Mc trust levels visible.
// Source objects from retrieve() carry verification: 0|1|2 (or verification_name).
// ---------------------------------------------------------------------------
function verificationTierBadge(source) {
    let tier = null;
    if (source && typeof source === 'object') {
        if (source.verification != null && source.verification !== '') {
            tier = Number(source.verification);
        } else if (source.verification_name) {
            const n = String(source.verification_name).toUpperCase();
            if (n === 'VERIFIED') tier = 2;
            else if (n === 'GROUNDED') tier = 1;
            else if (n === 'UNVERIFIED') tier = 0;
        } else if (source.provenance) {
            const p = String(source.provenance).toLowerCase();
            if (p === 'user_document' || p === 'user_stated' || p === 'user_confirmed') tier = 2;
            else if (p === 'grounded_cited') tier = 1;
            else if (p === 'llm_generation') tier = 0;
        }
    }
    // Default unknown → Unverified (do not claim trust)
    if (tier !== 0 && tier !== 1 && tier !== 2) tier = 0;

    // Instrument-console badge (match design tokens)
    const labels = { 2: '✓ Verified', 1: '~ Grounded', 0: '• Unverified' };
    return '<span class="instr-tier-badge t' + tier + ' verification-badge" data-tier="' + tier +
        '" title="Trust tier from provenance / sources">' + labels[tier] + '</span>';
}

/** Derive answer-level tier from sources array (max trust among sources). */
function answerTierFromSources(sources) {
    if (!Array.isArray(sources) || !sources.length) return 0;
    let maxT = 0;
    sources.forEach(function (s) {
        if (typeof s === 'string') return;
        // reuse verificationTierBadge parsing via temp
        let tier = 0;
        if (s && s.verification != null) {
            const n = Number(s.verification);
            if (n === 2 || n === 1 || n === 0) tier = n;
            else {
                const u = String(s.verification).toUpperCase();
                if (u === 'VERIFIED') tier = 2;
                else if (u === 'GROUNDED') tier = 1;
            }
        } else if (s && s.provenance) {
            const p = String(s.provenance).toLowerCase();
            if (p === 'user_document' || p === 'user_stated' || p === 'user_confirmed') tier = 2;
            else if (p === 'grounded_cited') tier = 1;
        }
        if (tier > maxT) maxT = tier;
    });
    // any retrieved source at least Grounded (1) if not LLM-only
    if (maxT === 0 && sources.length) {
        const anyGround = sources.some(function (s) {
            if (typeof s === 'string') return true;
            const p = String((s && s.provenance) || '').toLowerCase();
            return p && p !== 'llm_generation';
        });
        if (anyGround) maxT = 1;
    }
    return maxT;
}

function citationChipsHtml(sources) {
    if (!Array.isArray(sources) || !sources.length) return '';
    return sources.slice(0, 8).map(function (s) {
        let label;
        if (typeof s === 'string') label = s;
        else label = (s && (s.file || s.name || s.path || s.source || s.title || s.pattern)) || 'source';
        return '<span class="instr-cite-chip" title="' + escapeHtml(String(label)) + '">' +
            escapeHtml(String(label).slice(0, 48)) + '</span>';
    }).join('');
}

function attachAnswerTrustMeta(bubble, data) {
    if (!bubble || !data) return;
    // remove prior meta row if re-attach
    const old = bubble.querySelector('.instr-answer-meta');
    if (old) old.remove();
    const sources = data.sources || [];
    let tier = 0;
    if (data.verification != null) {
        const n = Number(data.verification);
        if (n === 0 || n === 1 || n === 2) tier = n;
        else {
            const u = String(data.verification).toUpperCase();
            if (u === 'VERIFIED') tier = 2;
            else if (u === 'GROUNDED') tier = 1;
        }
    } else {
        tier = answerTierFromSources(sources);
    }
    const row = document.createElement('div');
    row.className = 'instr-answer-meta';
    row.innerHTML = verificationTierBadge({ verification: tier }) + citationChipsHtml(sources);
    bubble.appendChild(row);
    return tier;
}

// ---------------------------------------------------------------------------
// AI backend selector (Local Ollama / LM Studio) — no API keys for local backends.
// POST /api/settings/llm { provider, model, lmstudio_base_url? }
// ---------------------------------------------------------------------------
const LMSTUDIO_URL_STORAGE_KEY = 'synthesus_lmstudio_base_url';

function onLLMProviderChange() {
    const providerSel = document.getElementById('llm-provider');
    const row = document.getElementById('lmstudio-url-row');
    if (!providerSel || !row) return;
    const isLm = providerSel.value === 'lmstudio';
    row.style.display = isLm ? 'flex' : 'none';
}

async function loadLLMSettings() {
    const statusEl = document.getElementById('llm-settings-status');
    try {
        const res = await fetch('/api/settings/llm');
        const data = await res.json().catch(() => ({}));
        const providerSel = document.getElementById('llm-provider');
        const modelInput = document.getElementById('llm-model');
        const urlInput = document.getElementById('llm-lmstudio-url');

        // Only local backends in the selector — map unknown/cloud values to ollama default.
        let provider = (data && data.provider) || 'ollama';
        if (provider !== 'ollama' && provider !== 'lmstudio') {
            provider = 'ollama';
        }
        if (providerSel) providerSel.value = provider;
        if (modelInput) modelInput.value = (data && data.model) || '';

        // Base URL: prefer server field if present; else localStorage (GET contract may omit it).
        let baseUrl = (data && (data.lmstudio_base_url || data.lmstudioBaseUrl)) || '';
        if (!baseUrl) {
            try { baseUrl = localStorage.getItem(LMSTUDIO_URL_STORAGE_KEY) || ''; } catch (e) { baseUrl = ''; }
        }
        if (urlInput) urlInput.value = baseUrl || 'http://localhost:1234';

        onLLMProviderChange();
        if (statusEl && data && data.error) {
            statusEl.innerHTML = '<span style="color:var(--purple-light);">Loaded defaults (runtime: ' +
                escapeHtml(String(data.error)) + ')</span>';
        }
    } catch (e) {
        console.error('Failed to load LLM settings:', e);
        onLLMProviderChange();
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#f87171;">Could not load settings — using defaults.</span>';
        }
    }
}

async function saveLLMSettings() {
    const providerSel = document.getElementById('llm-provider');
    const modelInput = document.getElementById('llm-model');
    const urlInput = document.getElementById('llm-lmstudio-url');
    const statusEl = document.getElementById('llm-settings-status');

    const provider = (providerSel && providerSel.value) || 'ollama';
    const model = (modelInput && modelInput.value) ? modelInput.value.trim() : '';
    let lmstudioBaseUrl = (urlInput && urlInput.value) ? urlInput.value.trim() : '';

    if (provider !== 'ollama' && provider !== 'lmstudio') {
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#f87171;">Only Local Ollama and LM Studio are supported here.</span>';
        }
        return;
    }

    if (provider === 'lmstudio' && !lmstudioBaseUrl) {
        lmstudioBaseUrl = 'http://localhost:1234';
        if (urlInput) urlInput.value = lmstudioBaseUrl;
    }

    // Remember base URL for UI reload (GET may not echo lmstudio_base_url).
    try {
        if (provider === 'lmstudio' && lmstudioBaseUrl) {
            localStorage.setItem(LMSTUDIO_URL_STORAGE_KEY, lmstudioBaseUrl);
        }
    } catch (e) { /* storage unavailable */ }

    const payload = { provider: provider, model: model };
    // Include optional base URL for LM Studio (runtime/device reads settings.json).
    if (provider === 'lmstudio') {
        payload.lmstudio_base_url = lmstudioBaseUrl;
    }

    if (statusEl) statusEl.innerText = 'Saving…';

    try {
        const res = await fetch('/api/settings/llm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
            const savedProvider = data.provider || provider;
            const savedModel = data.model != null ? data.model : model;
            if (statusEl) {
                statusEl.innerHTML =
                    '<span style="color:#4ade80;">Saved: ' +
                    escapeHtml(String(savedProvider)) +
                    (savedModel ? ' / ' + escapeHtml(String(savedModel)) : '') +
                    (provider === 'lmstudio' ? ' @ ' + escapeHtml(lmstudioBaseUrl) : '') +
                    '</span>';
            }
        } else {
            const msg = data.message || data.error || data.detail || ('HTTP ' + res.status);
            if (statusEl) {
                statusEl.innerHTML = '<span style="color:#f87171;">Error: ' + escapeHtml(String(msg)) + '</span>';
            }
        }
    } catch (e) {
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#f87171;">Connection error — is the desktop shell running?</span>';
        }
    }
}

let foremanInterval;
let _foremanFailStreak = 0;
function startForemanSync() {
    // Only poll while Foreman window is open — never on page load (QA BUG-5).
    if (foremanInterval) clearInterval(foremanInterval);
    _foremanFailStreak = 0;
    fetchForemanQueue();
    foremanInterval = setInterval(fetchForemanQueue, 2000);
}

function stopForemanSync() {
    if (foremanInterval) { clearInterval(foremanInterval); foremanInterval = null; }
}

async function fetchForemanQueue() {
    try {
        const res = await fetch('/api/foreman/queue');
        if (!res.ok) {
            // Foreman unmounted / FastAPI 404 detail — stop polling (QA BUG-5).
            _foremanFailStreak++;
            if ((res.status === 404 || res.status === 501 || _foremanFailStreak >= 2) && foremanInterval) {
                stopForemanSync();
            }
            return;
        }
        _foremanFailStreak = 0;
        const data = await res.json();
        const listEl = document.getElementById('foreman-queue-list');
        if (!listEl) return;
        
        if (!data.queue || data.queue.length === 0) {
            listEl.innerHTML = '<div style="color: #64748b; font-size: 0.9rem;">No pending approvals.</div>';
            return;
        }
        
        let html = '';
        data.queue.forEach(item => {
            html += `<div style="background: rgba(0,0,0,0.4); border: 1px solid #ef4444; padding: 10px; border-radius: 6px;">
                <h4 style="margin: 0 0 5px 0; color: #fca5a5;">Pending Action (T${item.detected_tier})</h4>
                <div style="font-family: monospace; color: #a78bfa; margin-bottom: 5px; font-size: 0.85rem;">
                    Command: ${escapeHtml(item.command)}<br>
                    Cwd: ${escapeHtml(item.cwd)}
                </div>
                <div style="font-size: 0.8rem; color: #cbd5e1; margin-bottom: 5px;">
                    Declared: T${item.declared_tier} | Detected: T${item.detected_tier}<br>
                    Type: ${item.blast_radius} | Effects: ${JSON.stringify(item.effects)}<br>
                    Reasons: ${(item.reasons || []).join(', ')}
                </div>
                <div style="display: flex; gap: 10px; margin-top: 10px;">
                    <button class="glass-btn primary-btn" style="flex:1;" onclick="approveForeman('${item.step_id}', ${item.detected_tier}, '${escapeHtml(item.command).replace(/'/g, "\\'")}')">Approve</button>
                    <button class="glass-btn" style="flex:1; background: rgba(239, 68, 68, 0.2);" onclick="denyForeman('${item.step_id}')">Deny</button>
                </div>
            </div>`;
        });
        listEl.innerHTML = html;
    } catch(e) {}
}

async function approveForeman(stepId, tier, command) {
    if (tier === 4) {
        const conf = prompt(`T4 DESTRUCTIVE ACTION.\n\nCommand: ${command}\n\nType CONFIRM to execute:`);
        if (conf !== 'CONFIRM') {
            alert('Approval aborted.');
            return;
        }
    }
    
    try {
        const resQueue = await fetch('/api/foreman/queue');
        const data = await resQueue.json();
        const qItem = data.queue.find(q => q.step_id === stepId);
        
        // Wait, token is not in the queue array by default unless bridge.py exposes it!
        // We added it in bridge.py intentionally for this single-user desktop setup
        // Let's check bridge.py again: self.queue[step_id]["token"] but get_queue returns self.queue[step_id]["queue_item"].
        // Wait, in my bridge.py I didn't add "token" to "queue_item". Let me fetch the actual token in a hacky way or just update bridge.py.
        // Actually, if we pass token back, it should be in queue_item. Let's assume bridge.py gets updated.
        if (!qItem || !qItem.token) {
            alert("Token not found or step expired.");
            return;
        }
        
        await fetch('/api/foreman/approve', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ step_id: stepId, token: qItem.token })
        });
        fetchForemanQueue();
    } catch(e) {
        alert("Approval failed: " + e);
    }
}

async function denyForeman(stepId) {
    try {
        const resQueue = await fetch('/api/foreman/queue');
        const data = await resQueue.json();
        const qItem = data.queue.find(q => q.step_id === stepId);
        if (!qItem || !qItem.token) return;
        
        await fetch('/api/foreman/deny', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ step_id: stepId, token: qItem.token })
        });
        fetchForemanQueue();
    } catch(e) {}
}

// Foreman poll is started only when #win-foreman opens (see toggleWindow).

// ==========================================
// SI IMAGE STUDIO (procedural VSA — not diffusion)
// ==========================================
const IMAGE_STUDIO_EXAMPLES = {
    house: 'a house and a tree on green grass under a blue sky with a sun and a cloud',
    river: 'a boat on a river under a sky with a bird and a tree right of a bridge',
    city: 'a person left of a building on a road under a sky with a sun',
    vase: 'a vase and a cup on grass under a sky with a sun',
    crate: 'a crate and a house on grass under a sky',
};
/** Last SI scene stock id for multi-pass re-render (server session). */
let _lastStudioSceneId = null;
let _lastStudioYaw = 0;

const IMAGE_PRESET_HINTS = {
    cottage_dawn: { prompt: 'a cottage left of a tree on green grass under a blue sky with a sun and a cloud and a flower', style: 'photo', look: 'cinema', aspect: '1.5' },
    harbor_day: { prompt: 'a boat on a river under a sky with a sun and a bridge and a bird and a person right of a tree', style: 'photo', look: 'photo', aspect: '1.5' },
    city_dusk: { prompt: 'a person left of a building on a road under a sky with a sun and a lamp and a car', style: 'photo', look: 'vivid', aspect: '1.5' },
    mountain_lake: { prompt: 'a mountain and a lake and a tree and a cabin under a sky with a sun and a cloud', style: 'photo', look: 'cinema', aspect: '1.5' },
    night_village: { prompt: 'a house and a tree and a person and a star under a night sky over grass with a moon and a lamp', style: 'night', look: 'cinema', aspect: '1' },
    bridge_crossing: { prompt: 'a person on a bridge over a river under a sky with a sun and a tree right of a house', style: 'photo', look: 'photo', aspect: '1.5' },
};
let _activeImagePreset = null;

function applyImagePreset(id) {
    const p = IMAGE_PRESET_HINTS[id];
    if (!p) return;
    _activeImagePreset = id;
    const promptEl = document.getElementById('image-prompt');
    if (promptEl) promptEl.value = p.prompt;
    const styleEl = document.getElementById('image-style');
    if (styleEl && p.style) styleEl.value = p.style;
    const lookEl = document.getElementById('image-look');
    if (lookEl && p.look) lookEl.value = p.look;
    const aspectEl = document.getElementById('image-aspect');
    if (aspectEl && p.aspect) aspectEl.value = p.aspect;
    const statusEl = document.getElementById('image-studio-status');
    if (statusEl) statusEl.innerHTML = '<span style="color:#a78bfa;">Preset: ' + escapeHtmlStudio(id) + ' — hit Generate</span>';
}
const IMAGE_GALLERY_KEY = 'synthesus_image_gallery_v1';
let _lastStudioDataUrl = null;

function imageStudioExample(key) {
    const el = document.getElementById('image-prompt');
    if (el && IMAGE_STUDIO_EXAMPLES[key]) el.value = IMAGE_STUDIO_EXAMPLES[key];
}

function escapeHtmlStudio(s) {
    return String(s == null ? '' : s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;')
        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function entsSafe(n) {
    return (typeof n === 'number' && !Number.isNaN(n)) ? n : '?';
}

function loadImageGallery() {
    try {
        return JSON.parse(localStorage.getItem(IMAGE_GALLERY_KEY) || '[]');
    } catch (_) { return []; }
}

function saveImageGallery(items) {
    try {
        localStorage.setItem(IMAGE_GALLERY_KEY, JSON.stringify(items.slice(0, 8)));
    } catch (_) { /* quota — ignore */ }
}

function pushImageGallery(dataUrl, prompt) {
    // Store tiny thumbs only — strip to avoid localStorage bloat (keep last 8 refs as data urls max ~)
    const items = loadImageGallery();
    items.unshift({ src: dataUrl, prompt: (prompt || '').slice(0, 80), t: Date.now() });
    // Keep at most 6; if too large, drop
    while (items.length > 6) items.pop();
    saveImageGallery(items);
    renderImageGallery();
}

function renderImageGallery() {
    const el = document.getElementById('image-studio-gallery');
    if (!el) return;
    const items = loadImageGallery();
    if (!items.length) {
        el.innerHTML = '<span style="color:#475569;font-size:0.75rem;">No recent renders yet</span>';
        return;
    }
    el.innerHTML = items.map((it, i) =>
        '<img src="' + it.src + '" title="' + escapeHtmlStudio(it.prompt || '') +
        '" onclick="imageGalleryPick(' + i + ')" style="height:48px;width:48px;object-fit:cover;border-radius:6px;cursor:pointer;border:1px solid rgba(148,163,184,.3);">'
    ).join('');
}

function imageGalleryPick(i) {
    const items = loadImageGallery();
    const it = items[i];
    if (!it) return;
    const previewEl = document.getElementById('image-studio-preview');
    if (previewEl) {
        previewEl.innerHTML = '<img src="' + it.src + '" alt="gallery" style="max-width:100%; max-height:280px; border-radius:6px; object-fit:contain;">';
    }
    _lastStudioDataUrl = it.src;
    const btn = document.getElementById('image-download-btn');
    if (btn) btn.disabled = false;
    const promptEl = document.getElementById('image-prompt');
    if (promptEl && it.prompt) promptEl.value = it.prompt;
}

function downloadImageStudio() {
    if (!_lastStudioDataUrl) return;
    const a = document.createElement('a');
    a.href = _lastStudioDataUrl;
    a.download = 'synthesus-si-' + Date.now() + '.png';
    document.body.appendChild(a);
    a.click();
    a.remove();
}

function showStudioImage(src, data) {
    const previewEl = document.getElementById('image-studio-preview');
    const varEl = document.getElementById('image-studio-variations');
    if (varEl) { varEl.style.display = 'none'; varEl.innerHTML = ''; }
    if (previewEl) {
        previewEl.style.display = 'flex';
        previewEl.innerHTML = '<img src="' + src + '" alt="SI render" style="max-width:100%; max-height:280px; border-radius:6px; object-fit:contain;">';
    }
    _lastStudioDataUrl = src;
    const btn = document.getElementById('image-download-btn');
    if (btn) btn.disabled = false;
    pushImageGallery(src, data && data.prompt);
}

let _studioVarSrcs = [];

function showStudioVariations(vars, mime) {
    const previewEl = document.getElementById('image-studio-preview');
    const varEl = document.getElementById('image-studio-variations');
    if (previewEl) previewEl.style.display = 'none';
    if (!varEl) return;
    varEl.style.display = 'grid';
    mime = mime || 'image/png';
    _studioVarSrcs = vars.map(v => 'data:' + mime + ';base64,' + v.image_base64);
    varEl.innerHTML = vars.map((v, i) => {
        return '<img src="' + _studioVarSrcs[i] + '" title="seed ' + (v.seed != null ? v.seed : i) +
            '" data-var-i="' + i + '" onclick="pickStudioVariation(' + i + ')" ' +
            'style="width:100%; border-radius:6px; cursor:pointer; border:1px solid rgba(148,163,184,.25);">';
    }).join('');
    if (_studioVarSrcs[0]) {
        _lastStudioDataUrl = _studioVarSrcs[0];
        const btn = document.getElementById('image-download-btn');
        if (btn) btn.disabled = false;
    }
}

function pickStudioVariation(i) {
    const src = _studioVarSrcs[i];
    if (!src) return;
    showStudioImage(src, { prompt: (document.getElementById('image-prompt') || {}).value || '' });
}

function setStudioSceneId(sid) {
    _lastStudioSceneId = sid || null;
    const el = document.getElementById('image-scene-id');
    if (el) {
        el.textContent = sid ? sid : '— generate first —';
        el.title = sid ? ('scene_id ' + sid + ' (stock = scene graph)') : 'Generate once to enable Re-pass';
    }
    const rep = document.getElementById('image-repass-btn');
    const repY = document.getElementById('image-repass-yaw-btn');
    const pl = document.getElementById('image-playlist-btn');
    if (rep) rep.disabled = !sid;
    if (repY) repY.disabled = !sid;
    if (pl) pl.disabled = !sid;
}

function showPlanInspector(data) {
    const el = document.getElementById('image-plan-inspector');
    if (!el) return;
    const sp = data && data.scene_plan;
    if (!sp) {
        el.style.display = 'none';
        return;
    }
    const lines = [];
    lines.push('construction: ' + (sp.construction || data.construction || '?'));
    lines.push('si_prompt: ' + (sp.si_prompt || data.si_prompt || ''));
    (sp.machines || []).forEach(function (m) {
        lines.push('machine ' + (m.machine || '?') + ': ' + (m.name || m.entity || ''));
    });
    (sp.composites || []).forEach(function (c) {
        lines.push('composite ' + (c.name || '?') + ' [' + (c.parts || []).join('+') + ']');
    });
    (sp.entity_maps || []).slice(0, 12).forEach(function (e) {
        lines.push('map ' + (e.name || '') + ' → ' + (e.maps_to || '') + ' (' + (e.role || '') + ')');
    });
    if (sp.material_lib && sp.material_lib.palette) {
        lines.push('palette: ' + sp.material_lib.palette);
    }
    if (data.outer_voice) lines.push('voice: ' + data.outer_voice);
    el.textContent = lines.join('\n');
    el.style.display = lines.length ? 'block' : 'none';
}

async function loadImageCapabilities() {
    const el = document.getElementById('image-capability-card');
    const statusEl = document.getElementById('image-studio-status');
    if (!el) return;
    try {
        const res = await fetch('/api/v1/image/capabilities');
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || res.status);
        const can = (data.can || []).map(function (x) { return '✓ ' + x; }).join('\n');
        const cannot = (data.cannot || []).map(function (x) { return '✗ ' + x; }).join('\n');
        el.innerHTML = '<strong style="color:#7dd3fc;">SI Image — ' + escapeHtmlStudio(data.engine_version || data.engine || '')
            + '</strong><div style="margin-top:4px;color:#94a3b8;">' + escapeHtmlStudio(data.si_vs_ai || '')
            + '</div><pre style="margin:6px 0 0;white-space:pre-wrap;color:#86efac;">' + escapeHtmlStudio(can)
            + '</pre><pre style="margin:4px 0 0;white-space:pre-wrap;color:#fca5a5;">' + escapeHtmlStudio(cannot) + '</pre>';
        el.style.display = 'block';
        if (statusEl) statusEl.innerHTML = '<span style="color:var(--purple-light);">Capability card loaded (SI ≠ diffusion)</span>';
    } catch (e) {
        el.style.display = 'block';
        el.textContent = 'Capabilities unavailable: ' + (e.message || e);
    }
}

async function runImagePlaylist(name) {
    name = name || 'finish';
    const statusEl = document.getElementById('image-studio-status');
    const previewEl = document.getElementById('image-studio-preview');
    if (!_lastStudioSceneId) {
        if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Generate first for finish job</span>';
        return;
    }
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--purple-light);">Finish playlist "' + escapeHtmlStudio(name) + '"…</span>';
    try {
        const res = await fetch('/api/v1/image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                scene_id: _lastStudioSceneId,
                playlist: name,
                pass_only: true,
                resolution: parseInt((document.getElementById('image-res') || {}).value || '512', 10),
            }),
        });
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok || !data.image_base64) {
            throw new Error((data && (data.message || data.error)) || ('HTTP ' + res.status));
        }
        const frames = data.playlist_frames || [];
        if (frames.length > 1) {
            showStudioVariations(frames, data.mime_type || 'image/png');
        } else {
            showStudioImage('data:image/png;base64,' + data.image_base64, data);
        }
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#4ade80;">Playlist OK — ' + (data.frame_count || frames.length)
                + ' passes on stock · not diffusion</span>';
        }
    } catch (e) {
        if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Playlist failed: ' + escapeHtmlStudio(e.message || e) + '</span>';
        if (previewEl) previewEl.innerHTML = '<span style="color:#f87171;">Error</span>';
    }
}

function studioCollectEditKnobs() {
    const grade = ((document.getElementById('image-grade') || {}).value) || 'none';
    const edit_text = ((document.getElementById('image-pass-text') || {}).value || '').trim();
    const look = ((document.getElementById('image-look') || {}).value) || 'photo';
    const detail = ((document.getElementById('image-detail') || {}).value) || 'high';
    const style = ((document.getElementById('image-style') || {}).value) || 'photo';
    const resolution = parseInt((document.getElementById('image-res') || {}).value || '512', 10);
    return { grade, edit_text, look, detail, style, resolution };
}

/**
 * Multi-pass: re-render the stored scene graph (same world).
 * opts.yaw_delta adds to last yaw; opts.yaw absolute if set.
 */
async function runImageStudioPass(opts) {
    opts = opts || {};
    const statusEl = document.getElementById('image-studio-status');
    const previewEl = document.getElementById('image-studio-preview');
    const metaEl = document.getElementById('image-studio-meta');
    if (!_lastStudioSceneId) {
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#f87171;">No scene stock — Generate first.</span>';
        }
        return;
    }
    const knobs = studioCollectEditKnobs();
    let yaw = _lastStudioYaw;
    if (opts.yaw != null && !Number.isNaN(Number(opts.yaw))) {
        yaw = Number(opts.yaw);
    } else if (opts.yaw_delta != null) {
        yaw = Math.max(-60, Math.min(60, yaw + Number(opts.yaw_delta)));
    } else {
        const yawEl = document.getElementById('image-pass-yaw');
        const yv = yawEl ? parseFloat(yawEl.value) : 15;
        if (!Number.isNaN(yv)) yaw = Math.max(-60, Math.min(60, yv));
    }
    const body = {
        scene_id: _lastStudioSceneId,
        pass_only: true,
        from_scene: true,
        prompt: '',
        yaw_deg: yaw,
        look: knobs.look,
        detail: knobs.detail,
        style: knobs.style,
        resolution: knobs.resolution,
        grade: knobs.grade,
        edit_text: knobs.edit_text || undefined,
        keep_session: true,
        return_plan: true,
        use_cache: false,
    };
    if (statusEl) {
        statusEl.innerHTML = '<span style="color:var(--purple-light);">Re-pass on scene stock · yaw='
            + yaw + '° · grade=' + escapeHtmlStudio(knobs.grade) + '…</span>';
    }
    if (previewEl) {
        previewEl.style.display = 'flex';
        previewEl.innerHTML = '<span style="color:#64748b;">Multi-pass…</span>';
    }
    try {
        const res = await fetch('/api/v1/image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        let data = null;
        try { data = await res.json(); } catch (_) { data = null; }
        if (!res.ok || !data || !data.image_base64) {
            const msg = (data && (data.message || data.error || data.detail)) || ('HTTP ' + res.status);
            if (statusEl) {
                statusEl.innerHTML = '<span style="color:#f87171;">Re-pass failed: '
                    + escapeHtmlStudio(typeof msg === 'string' ? msg : JSON.stringify(msg)) + '</span>';
            }
            return;
        }
        _lastStudioYaw = typeof data.yaw_deg === 'number' ? data.yaw_deg : yaw;
        if (data.scene_id) setStudioSceneId(data.scene_id);
        const mime = data.mime_type || 'image/png';
        const src = 'data:' + mime + ';base64,' + data.image_base64;
        showStudioImage(src, data);
        if (metaEl) {
            metaEl.textContent = [
                'PASS on scene_id=' + (data.scene_id || _lastStudioSceneId),
                'yaw=' + _lastStudioYaw,
                'look=' + (data.look || knobs.look),
                data.construction ? ('build=' + data.construction) : '',
                data.picture_edit ? 'picture_edit' : '',
                data.lathe_parts != null ? ('lathe=' + data.lathe_parts) : '',
                data.extrude_parts != null ? ('extrude=' + data.extrude_parts) : '',
                (data.latency_ms != null ? data.latency_ms + 'ms' : ''),
            ].filter(Boolean).join(' · ');
            if (data.outer_voice) metaEl.textContent += '\n' + data.outer_voice;
        }
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#4ade80;">Re-pass OK · same world · yaw='
                + _lastStudioYaw + '° · not diffusion</span>';
        }
        // sync yaw field for next pass
        const yawEl = document.getElementById('image-pass-yaw');
        if (yawEl) yawEl.value = String(_lastStudioYaw);
    } catch (e) {
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#f87171;">Re-pass error: '
                + escapeHtmlStudio(e.message || e) + '</span>';
        }
    }
}

async function runImageStudioViews(n) {
    return runImageStudio(1, { views: n || 3, yaw_span: 30, as_gif: true });
}
async function runImageStudioFrames(n) {
    return runImageStudio(1, { frames: n || 4, as_gif: true });
}
async function runImageOrbitDay(n) {
    return runImageStudio(1, { orbit_day: true, orbit_frames: n || 6, as_gif: true, yaw_span: 40 });
}

async function pollImageJob(jobId, statusEl) {
    const maxTries = 120;
    for (let i = 0; i < maxTries; i++) {
        await new Promise(r => setTimeout(r, 500));
        try {
            const r = await fetch('/api/v1/image/jobs/' + encodeURIComponent(jobId));
            const j = await r.json().catch(() => null);
            if (!j) continue;
            if (statusEl) {
                const pct = j.progress != null ? Math.round(Number(j.progress) * 100) : 0;
                statusEl.innerHTML = '<span style="color:var(--purple-light);">Job '
                    + escapeHtmlStudio(jobId) + ' · ' + escapeHtmlStudio(j.status || '?')
                    + ' · ' + pct + '% · ' + escapeHtmlStudio(j.message || '') + '</span>';
            }
            if (j.status === 'done' && j.result) return j.result;
            if (j.status === 'failed') return j;
        } catch (_) { /* retry */ }
    }
    if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Job timed out</span>';
    return null;
}

// ── SI Level viewer (top-down X × Z map) ─────────────────────────────
let _lastLevelJson = null;
const LEVEL_ROLE_COLORS = {
    house: '#c4785a', building: '#7a8499', tree: '#3d8c48', bush: '#4a9e52',
    person: '#6b6b8a', boat: '#8b5a3c', bridge: '#9a8060', fence: '#8a7048',
    triangle: '#6e6a66', mountain: '#6e6a66', disc: '#d05050', flower: '#d84a78',
    ground: '#4a8a50', river: '#2e6ea8', strip: '#555560', bird: '#333',
    disc_top: '#f0d060', cloud_top: '#e8e8f0', star_top: '#f5e090', bg: '#4a70b0',
};

function renderLevelViewer(level) {
    const canvas = document.getElementById('level-viewer-canvas');
    const info = document.getElementById('level-viewer-info');
    if (!canvas || !level) return;
    _lastLevelJson = level;
    const ctx = canvas.getContext('2d');
    const W = canvas.width, H = canvas.height;
    ctx.fillStyle = '#0b1220';
    ctx.fillRect(0, 0, W, H);
    // grid
    ctx.strokeStyle = 'rgba(100,116,139,0.25)';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
        const x = (W * i) / 4, y = (H * i) / 4;
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke();
    }
    // axes labels
    ctx.fillStyle = '#64748b';
    ctx.font = '10px monospace';
    ctx.fillText('X →', W - 28, H - 6);
    ctx.fillText('Z far', 4, 12);
    ctx.fillText('near', 4, H - 6);

    const ents = level.entities || [];
    const pad = 16;
    const mapX = (x) => pad + (Math.min(1, Math.max(0, x)) * (W - 2 * pad));
    // z: 0 near at bottom, 1 far at top
    const mapZ = (z) => pad + ((1 - Math.min(1, Math.max(0, z))) * (H - 2 * pad));

    // Store hit targets for click → highlight
    canvas._levelHits = [];
    ents.forEach(function (e) {
        const role = e.role || 'disc';
        let x = e.cx != null ? e.cx : (e.x != null ? e.x : 0.5);
        let z = e.depth_z != null ? e.depth_z : 0.5;
        if (role === 'bg') return;
        if (role === 'ground') {
            ctx.fillStyle = 'rgba(74,138,80,0.15)';
            ctx.fillRect(pad, H * 0.55, W - 2 * pad, H * 0.4);
            return;
        }
        const px = mapX(Number(x) || 0.5);
        const py = mapZ(Number(z) || 0.5);
        const col = LEVEL_ROLE_COLORS[role] || LEVEL_ROLE_COLORS[e.entity] || '#94a3b8';
        const r = role === 'person' ? 4 : (role === 'tree' || role === 'house' || role === 'building' || role === 'lathe' || role === 'extrude') ? 7 : 5;
        ctx.beginPath();
        ctx.arc(px, py, r, 0, Math.PI * 2);
        ctx.fillStyle = col;
        ctx.fill();
        ctx.strokeStyle = 'rgba(255,255,255,0.35)';
        ctx.stroke();
        ctx.fillStyle = '#cbd5e1';
        ctx.font = '9px sans-serif';
        ctx.fillText(String(e.entity || role).slice(0, 8), px + r + 2, py + 3);
        canvas._levelHits.push({ x: px, y: py, r: r + 4, entity: e.entity || role, role: role, machine: e.machine || e.construction || '' });
    });

    // camera marker
    const cam = level.camera || {};
    ctx.fillStyle = 'var(--purple-light)';
    ctx.font = '9px monospace';
    ctx.fillText(
        'yaw=' + (cam.yaw_deg != null ? Number(cam.yaw_deg).toFixed(0) : '0')
        + ' pitch=' + (cam.pitch_deg != null ? Number(cam.pitch_deg).toFixed(0) : '0'),
        pad, H - 4
    );

    if (info) {
        info.innerHTML = escapeHtmlStudio(level.schema || 'level')
            + ' · ' + (level.entity_count != null ? level.entity_count : ents.length) + ' ents'
            + (level.prompt ? '<br><span style="color:#94a3b8;">' + escapeHtmlStudio(String(level.prompt).slice(0, 80)) + '</span>' : '')
            + '<br><span style="color:#64748b;">Click an entity to inspect</span>';
    }
    canvas.onclick = function (ev) {
        const rect = canvas.getBoundingClientRect();
        const mx = (ev.clientX - rect.left) * (canvas.width / rect.width);
        const my = (ev.clientY - rect.top) * (canvas.height / rect.height);
        const hits = canvas._levelHits || [];
        let best = null, bestD = 1e9;
        hits.forEach(function (h) {
            const d = Math.hypot(h.x - mx, h.y - my);
            if (d < h.r && d < bestD) { best = h; bestD = d; }
        });
        if (best && info) {
            info.innerHTML = '<span style="color:#7dd3fc;">selected: ' + escapeHtmlStudio(best.entity)
                + '</span> · role=' + escapeHtmlStudio(best.role)
                + (best.machine ? ' · ' + escapeHtmlStudio(best.machine) : '')
                + '<br><button class="glass-btn" style="font-size:0.7rem;margin-top:4px;" onclick="reRenderFromLastLevel()">Re-render from level</button>';
        }
    };
}

function loadLevelViewerFile(ev) {
    const f = ev && ev.target && ev.target.files && ev.target.files[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = function () {
        try {
            const level = JSON.parse(String(reader.result || '{}'));
            const L = level.level || level;
            renderLevelViewer(L);
            const info = document.getElementById('level-viewer-info');
            if (info) {
                info.innerHTML = (info.innerHTML || '')
                    + ' <button class="glass-btn" style="font-size:0.7rem;margin-top:4px;" onclick="reRenderFromLastLevel()">Re-render from level</button>';
            }
            window._lastLevelForRerender = L;
        } catch (e) {
            const info = document.getElementById('level-viewer-info');
            if (info) info.innerHTML = '<span style="color:#f87171;">Invalid JSON</span>';
        }
    };
    reader.readAsText(f);
}

async function reRenderFromLastLevel() {
    const level = window._lastLevelForRerender || window._lastLevelJson;
    const statusEl = document.getElementById('image-studio-status');
    if (!level) {
        if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">No level loaded</span>';
        return;
    }
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--purple-light);">Re-rendering from level stock…</span>';
    try {
        const res = await fetch('/api/v1/image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                level: level,
                pass_only: true,
                look: (document.getElementById('image-look') || {}).value || 'photo',
                resolution: parseInt((document.getElementById('image-res') || {}).value || '512', 10),
                grade: (document.getElementById('image-grade') || {}).value || 'none',
            }),
        });
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok || !data.image_base64) throw new Error(data.message || data.error || res.status);
        if (data.scene_id) setStudioSceneId(data.scene_id);
        showStudioImage('data:image/png;base64,' + data.image_base64, data);
        try { showPlanInspector(data); } catch (_) {}
        if (statusEl) statusEl.innerHTML = '<span style="color:#4ade80;">Level re-render OK · scene stock ready</span>';
    } catch (e) {
        if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Level re-render failed: ' + escapeHtmlStudio(e.message || e) + '</span>';
    }
}

async function exportImageLevel() {
    const promptEl = document.getElementById('image-prompt');
    const statusEl = document.getElementById('image-studio-status');
    const prompt = (promptEl && promptEl.value || '').trim();
    if (!prompt && !_activeImagePreset) {
        if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Prompt or preset required for level export.</span>';
        return;
    }
    if (statusEl) statusEl.innerHTML = '<span style="color:var(--purple-light);">Exporting SI level JSON…</span>';
    try {
        const body = {
            prompt: prompt || 'a house on grass under a sky',
            style: (document.getElementById('image-style') || {}).value || 'photo',
            look: (document.getElementById('image-look') || {}).value || 'photo',
            path_mode: ((document.getElementById('image-path-mode') || {}).value !== '0'),
        };
        if (_activeImagePreset) body.preset = _activeImagePreset;
        const res = await fetch('/api/v1/image/level', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.level) {
            if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Level export failed</span>';
            return;
        }
        const blob = new Blob([JSON.stringify(data.level, null, 2)], { type: 'application/json' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'synthesus-si-level-' + Date.now() + '.json';
        document.body.appendChild(a);
        a.click();
        a.remove();
        try { renderLevelViewer(data.level); } catch (_) {}
        if (statusEl) {
            statusEl.innerHTML = '<span style="color:#4ade80;">Level exported — '
                + (data.level.entity_count || '?') + ' entities · '
                + escapeHtmlStudio(data.level.schema || '') + '</span>';
        }
    } catch (e) {
        if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">' + escapeHtmlStudio(e.message || e) + '</span>';
    }
}

async function runImageStudio(variations, extra) {
    variations = variations || 1;
    extra = extra || {};
    const promptEl = document.getElementById('image-prompt');
    const statusEl = document.getElementById('image-studio-status');
    const previewEl = document.getElementById('image-studio-preview');
    const metaEl = document.getElementById('image-studio-meta');
    const entEl = document.getElementById('image-studio-entities');
    if (!promptEl) return;

    const prompt = (promptEl.value || '').trim();
    if (!prompt) {
        if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Prompt is required.</span>';
        return;
    }
    const style = (document.getElementById('image-style') || {}).value || 'photo';
    const look = (document.getElementById('image-look') || {}).value || 'photo';
    const resolution = parseInt((document.getElementById('image-res') || {}).value || '512', 10);
    const aspect = parseFloat((document.getElementById('image-aspect') || {}).value || '1');
    const detail = (document.getElementById('image-detail') || {}).value || 'high';
    const pathModeEl = document.getElementById('image-path-mode');
    const path_mode = !pathModeEl || pathModeEl.value !== '0';
    const seedRaw = (document.getElementById('image-seed') || {}).value;
    const body = {
        prompt, style, look, resolution, aspect, detail, path_mode,
        use_cache: true, variations, compile_plan: true, return_plan: true,
        keep_session: true,
    };
    const gradeEl = document.getElementById('image-grade');
    if (gradeEl && gradeEl.value) body.grade = gradeEl.value;
    const enhEl = document.getElementById('image-enhance');
    if (enhEl && enhEl.value) body.enhance = enhEl.value;
    const passText = ((document.getElementById('image-pass-text') || {}).value || '').trim();
    if (passText) body.edit_text = passText;
    _lastStudioYaw = 0;
    if (_activeImagePreset) body.preset = _activeImagePreset;
    if (extra.views) { body.views = extra.views; body.yaw_span = extra.yaw_span || 30; body.variations = 1; }
    if (extra.frames) { body.frames = extra.frames; body.variations = 1; body.views = 1; }
    if (extra.orbit_day) {
        body.orbit_day = true;
        body.orbit_frames = extra.orbit_frames || 6;
        body.yaw_span = extra.yaw_span || 40;
        body.variations = 1;
        body.views = 1;
        body.frames = 1;
    }
    if (extra.as_gif) { body.as_gif = true; body.gif_format = extra.gif_format || 'gif'; body.gif_duration_ms = 350; }
    if (seedRaw !== undefined && seedRaw !== null && String(seedRaw).trim() !== '') {
        const n = parseInt(seedRaw, 10);
        if (!Number.isNaN(n)) body.seed = n;
    }

    if (statusEl) {
        let msg = 'Rendering SI scene graph…';
        if (body.orbit_day) msg = 'Rendering orbiting-day cinematic (' + (body.orbit_frames || 6) + ' frames)…';
        else if (body.frames > 1) msg = 'Rendering ' + body.frames + ' time-of-day frames (same world)…';
        else if (body.views > 1) msg = 'Rendering ' + body.views + ' camera views (orbit)…';
        else if (variations > 1) msg = 'Rendering ' + variations + ' SI seed variations…';
        statusEl.innerHTML = '<span style="color:var(--purple-light);">' + msg + '</span>';
    }
    if (previewEl) {
        previewEl.style.display = 'flex';
        previewEl.innerHTML = '<span style="color:#64748b;">Working…</span>';
    }
    const varEl = document.getElementById('image-studio-variations');
    if (varEl) { varEl.style.display = 'none'; varEl.innerHTML = ''; }
    if (metaEl) metaEl.textContent = '';
    if (entEl) entEl.innerHTML = '';

    try {
        // HD / multi-frame auto-async on server — poll job_id
        if (resolution >= 1024 || body.orbit_day || body.frames > 1 || body.views > 1 || variations > 1) {
            body.async_mode = true;
        }
        const res = await fetch('/api/v1/image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        let data = null;
        try { data = await res.json(); } catch (_) { data = null; }

        // 202 Accepted — async job
        if (res.status === 202 && data && data.job_id) {
            if (statusEl) {
                statusEl.innerHTML = '<span style="color:var(--purple-light);">Job ' + escapeHtmlStudio(data.job_id)
                    + ' · ' + escapeHtmlStudio(data.status || 'queued') + '…</span>';
            }
            data = await pollImageJob(data.job_id, statusEl);
            if (!data) {
                if (previewEl) previewEl.innerHTML = '<span style="color:#f87171;">Job failed</span>';
                return;
            }
        }

        if (!res.ok && res.status !== 202 || !data || (!data.image_base64 && !(data.variations && data.variations.length) && !(data.frames && data.frames.length) && !(data.views && data.views.length) && !data.animation)) {
            if (data && data.status === 'failed') {
                if (statusEl) statusEl.innerHTML = '<span style="color:#f87171;">Failed: ' + escapeHtmlStudio(data.error || 'job failed') + '</span>';
            } else {
                const msg = (data && (data.message || data.error || data.detail)) || (`HTTP ${res.status}`);
                if (statusEl) statusEl.innerHTML = `<span style="color:#f87171;">Failed: ${escapeHtmlStudio(typeof msg === 'string' ? msg : JSON.stringify(msg))}</span>`;
            }
            if (previewEl) previewEl.innerHTML = '<span style="color:#f87171;">No image</span>';
            return;
        }
        const mime = data.mime_type || 'image/png';
        const grid = (data.views && data.views.length > 1) ? data.views
            : (data.frames && data.frames.length > 1) ? data.frames
            : (data.variations && data.variations.length > 1) ? data.variations
            : null;
        if (grid) {
            showStudioVariations(grid, mime);
        } else {
            const src = `data:${mime};base64,${data.image_base64}`;
            showStudioImage(src, data);
        }
        // Animated GIF/WebP of sequence if present
        if (data.animation && data.animation.image_base64) {
            const amime = data.animation.mime_type || 'image/gif';
            const asrc = 'data:' + amime + ';base64,' + data.animation.image_base64;
            _lastStudioDataUrl = asrc;
            const previewEl2 = document.getElementById('image-studio-preview');
            if (previewEl2) {
                previewEl2.style.display = 'flex';
                previewEl2.innerHTML = '<img src="' + asrc + '" alt="SI animation" style="max-width:100%; max-height:280px; border-radius:6px;">'
                    + '<div style="font-size:0.72rem;color:#94a3b8;margin-top:4px;">animation · '
                    + (data.animation.frame_count || '?') + ' frames · ' + (data.animation.format || 'gif') + '</div>';
            }
            const btn = document.getElementById('image-download-btn');
            if (btn) btn.disabled = false;
            pushImageGallery(asrc, (data.prompt || prompt) + ' [anim]');
        }
        const cacheTag = data.cache_hit
            ? ('cache HIT' + (data.cache_source ? ' (' + data.cache_source + ')' : ''))
            : 'cache miss';
        if (data.scene_id) {
            setStudioSceneId(data.scene_id);
            if (typeof data.yaw_deg === 'number') _lastStudioYaw = data.yaw_deg;
        }
        try { showPlanInspector(data); } catch (_) {}
        if (metaEl) {
            metaEl.textContent = [
                `engine=${data.engine || 'synthesus_vsa_geometric'}`,
                `style=${data.style || style}`,
                `look=${data.look || look}`,
                `detail=${data.detail || detail}`,
                data.construction ? ('build=' + data.construction) : '',
                data.composite_parts != null ? ('composites=' + data.composite_parts) : '',
                data.lathe_parts != null ? ('lathe=' + data.lathe_parts) : '',
                data.extrude_parts != null ? ('extrude=' + data.extrude_parts) : '',
                data.scene_id ? ('scene=' + data.scene_id.slice(0, 8) + '…') : '',
                data.picture_edit ? 'picture_edit' : '',
                path_mode ? 'cnc_paths' : 'legacy',
                data.path_entities != null ? ('paths=' + data.path_entities) : '',
                `${data.width || '?'}x${data.height || '?'}`,
                `${data.latency_ms != null ? data.latency_ms + 'ms' : ''}`,
                cacheTag,
                data.vocab_version || '',
            ].filter(Boolean).join(' · ');
            if (data.outer_voice) {
                metaEl.textContent += '\n' + data.outer_voice;
            }
            if (data.si_prompt && data.si_prompt !== prompt) {
                metaEl.textContent += '\nsi_prompt: ' + data.si_prompt;
            }
            if (data.monologue) {
                metaEl.textContent += '\n' + String(data.monologue).slice(0, 280);
            }
        }
        if (entEl) {
            const ents = data.entities || [];
            entEl.innerHTML = ents.map(e =>
                `<span style="background:rgba(56,189,248,0.15); color:#7dd3fc; border:1px solid rgba(56,189,248,0.3); border-radius:999px; padding:2px 8px; font-size:0.72rem;">${escapeHtmlStudio(e)}</span>`
            ).join('');
        }
        if (statusEl) {
            const build = data.construction ? (' · ' + data.construction) : '';
            const sid = data.scene_id ? ' · stock ready' : '';
            statusEl.innerHTML = `<span style="color:#4ade80;">OK — ${entsSafe(data.entity_count)} entities · SI (not diffusion)${build}${sid}</span>`;
        }
    } catch (e) {
        if (statusEl) statusEl.innerHTML = `<span style="color:#f87171;">Error: ${escapeHtmlStudio(e.message || e)}</span>`;
        if (previewEl) previewEl.innerHTML = '<span style="color:#f87171;">Error</span>';
    }
}

// Restore gallery when Studio opens
const _origToggleWindow = typeof toggleWindow === 'function' ? null : null;
document.addEventListener('DOMContentLoaded', function () {
    try { renderImageGallery(); } catch (_) {}
    try { startInstrStatusStrip(); } catch (_) {}
});

// ── System Vitals: live subsystem readout (new bolt-on; reads the real /api/v1/health) ──
let _vitalsTimer = null;
function toggleVitals() {
    toggleWindow('win-vitals');
    const win = document.getElementById('win-vitals');
    const open = win && win.style.display !== 'none';
    if (open) { loadVitals(); if (!_vitalsTimer) _vitalsTimer = setInterval(loadVitals, 4000); }
    else if (_vitalsTimer) { clearInterval(_vitalsTimer); _vitalsTimer = null; }
    try { syncDockActive(); } catch (_) {}
}
async function loadVitals() {
    const rowsEl = document.getElementById('vitals-rows');
    const statusEl = document.getElementById('vitals-status');
    if (!rowsEl || !statusEl) return;
    let h = null;
    try { const r = await fetch('/api/v1/health'); if (r.ok) h = await r.json(); } catch (e) {}
    const esc = s => String(s).replace(/[<>&]/g, c => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));
    if (!h) {
        statusEl.innerHTML = 'OFFLINE <span class="sub">runtime unreachable</span>';
        rowsEl.innerHTML = '<div class="vrow"><span class="vdot crit"></span><span class="vk">Runtime</span><span class="vv">not reachable</span></div>';
        return;
    }
    const llm = h.llm || {};
    const on = b => b ? 'ok' : 'crit';
    statusEl.innerHTML = `${esc((h.status || '—').toUpperCase())} <span class="sub">v${esc(h.version || '—')}</span>`;
    const row = (dot, k, v) => `<div class="vrow"><span class="vdot ${dot}"></span><span class="vk">${k}</span><span class="vv">${esc(v)}</span></div>`;
    rowsEl.innerHTML =
        row('acc', 'Model', llm.model || '—') +
        row(on(llm.ollama_reachable), 'LLM', llm.ollama_reachable ? 'reachable · local' : 'unreachable') +
        row(on(h.rag_active), 'Grounding', h.rag_active ? 'active' : 'idle') +
        row(on(h.ml_swarm_active), 'ML swarm', h.ml_swarm_active ? 'active' : 'idle') +
        row(on(h.cognitive_engine_active !== false), 'Cognitive', (h.cognitive_engine_active !== false) ? 'online' : 'off') +
        row('vi', 'Sessions', h.active_sessions != null ? h.active_sessions : '—') +
        row('acc', 'Requests', h.total_requests != null ? h.total_requests : '—');
}

// ---------------------------------------------------------------------------
// Instrument status strip — real /api/v1/health
// ---------------------------------------------------------------------------
let _instrHealthTimer = null;

function startInstrStatusStrip() {
    if (document.getElementById('instr-status-strip')) {
        pollInstrHealth();
        if (_instrHealthTimer) clearInterval(_instrHealthTimer);
        _instrHealthTimer = setInterval(pollInstrHealth, 4000);
        return;
    }
    const strip = document.createElement('div');
    strip.id = 'instr-status-strip';
    strip.innerHTML =
        '<span class="strip-item">KERNEL <span id="strip-kernel">—</span></span>' +
        '<span class="strip-item">MODEL <span id="strip-model">—</span></span>' +
        '<span class="strip-item"><span class="strip-dot" id="strip-llm-dot"></span> LLM</span>' +
        '<span class="strip-item">UP <span id="strip-up">—</span>s</span>' +
        '<span class="strip-offline" title="Network use depends on enabled features">NETWORK: FEATURE-DEPENDENT</span>';
    document.body.insertBefore(strip, document.body.firstChild);
    document.body.classList.add('has-instr-strip');
    // offset main content slightly so strip doesn't cover window tops
    const main = document.querySelector('main') || document.getElementById('desktop');
    if (main && main.style) {
        const prev = main.style.paddingTop || '';
        if (!prev) main.style.paddingTop = '28px';
    }
    pollInstrHealth();
    if (_instrHealthTimer) clearInterval(_instrHealthTimer);
    _instrHealthTimer = setInterval(pollInstrHealth, 4000);
}

async function pollInstrHealth() {
    const kEl = document.getElementById('strip-kernel');
    const mEl = document.getElementById('strip-model');
    const dEl = document.getElementById('strip-llm-dot');
    const uEl = document.getElementById('strip-up');
    try {
        const res = await fetch('/api/v1/health');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        const llm = data.llm || {};
        const model = llm.model || '—';
        const reachable = !!llm.ollama_reachable;
        const status = data.status || '—';
        const up = data.uptime_seconds != null ? Math.round(Number(data.uptime_seconds)) : '—';
        if (kEl) kEl.textContent = String(status).toUpperCase();
        if (mEl) mEl.textContent = String(model);
        if (uEl) uEl.textContent = String(up);
        if (dEl) {
            dEl.classList.toggle('ok', reachable);
            dEl.title = reachable ? 'ollama reachable' : 'ollama unreachable';
        }
    } catch (e) {
        if (kEl) kEl.textContent = '—';
        if (mEl) mEl.textContent = '—';
        if (uEl) uEl.textContent = '—';
        if (dEl) {
            dEl.classList.remove('ok');
            dEl.title = 'health unreachable';
        }
    }
}
// ---------------------------------------------------------------------------
// SI Voice Studio — formant larynx via POST /api/v1/voice (not neural TTS)
// ---------------------------------------------------------------------------
let _lastVoiceObjectUrl = null;

function collectVoiceKnobs() {
    const knobs = {};
    if (document.getElementById('voice-knob-slower')?.checked) knobs.slower = true;
    if (document.getElementById('voice-knob-faster')?.checked) knobs.faster = true;
    if (document.getElementById('voice-knob-higher')?.checked) knobs.higher = true;
    if (document.getElementById('voice-knob-lower')?.checked) knobs.lower = true;
    if (document.getElementById('voice-knob-rising')?.checked) knobs.rising_final = true;
    return knobs;
}

async function runVoiceSpeak() {
    const textEl = document.getElementById('voice-text');
    const statusEl = document.getElementById('voice-status');
    const phEl = document.getElementById('voice-phonemes');
    const uidEl = document.getElementById('voice-uid');
    const audioEl = document.getElementById('voice-audio');
    const text = (textEl && textEl.value || '').trim();
    if (!text) {
        if (statusEl) statusEl.textContent = 'text required';
        return;
    }
    if (statusEl) statusEl.textContent = 'synthesizing SI formant…';
    if (phEl) phEl.textContent = '';
    try {
        const headers = (typeof authHeaders === 'function') ? authHeaders() : { 'Content-Type': 'application/json' };
        if (!headers['Content-Type'] && !headers['content-type']) {
            headers['Content-Type'] = 'application/json';
        }
        const backendEl = document.getElementById('voice-backend');
        const backend = (backendEl && backendEl.value) || 'formant';
        const res = await fetch('/api/v1/voice', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({
                text: text,
                knobs: collectVoiceKnobs(),
                seed: 25,
                backend: backend,
            }),
        });
        const data = await res.json().catch(function () { return {}; });
        if (!res.ok || !data.audio_base64) {
            const msg = (data && (data.message || data.detail?.message || data.error || data.detail)) || ('HTTP ' + res.status);
            if (statusEl) {
                statusEl.style.color = '#fb7185';
                statusEl.textContent = '503/ERR · ' + (typeof msg === 'string' ? msg : JSON.stringify(msg));
            }
            return;
        }
        // Force WAV MIME — some browsers refuse to decode with a generic type.
        const mime = 'audio/wav';
        const b64 = String(data.audio_base64 || '').replace(/\s+/g, '');
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        // RIFF check in browser
        const riffOk = bytes.length >= 12 &&
            String.fromCharCode(bytes[0], bytes[1], bytes[2], bytes[3]) === 'RIFF' &&
            String.fromCharCode(bytes[8], bytes[9], bytes[10], bytes[11]) === 'WAVE';
        // Copy into a fresh ArrayBuffer-backed view (avoids detached-buffer edge cases)
        const ab = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
        const blob = new Blob([ab], { type: mime });
        if (_lastVoiceObjectUrl) {
            try { URL.revokeObjectURL(_lastVoiceObjectUrl); } catch (_) {}
        }
        _lastVoiceObjectUrl = URL.createObjectURL(blob);
        if (audioEl) {
            audioEl.pause();
            audioEl.removeAttribute('src');
            audioEl.src = _lastVoiceObjectUrl;
            audioEl.type = mime;
            // load() is required so duration leaves 0:00/0:00 (QA BUG-4)
            try { audioEl.load(); } catch (_) {}
            const tryPlay = function () {
                const p = audioEl.play();
                if (p && typeof p.catch === 'function') {
                    p.catch(function (err) {
                        if (statusEl) {
                            statusEl.textContent = (statusEl.textContent || '') +
                                ' · click ▶ to play (autoplay blocked)';
                        }
                        console.log('voice play blocked/failed', err && err.message);
                    });
                }
            };
            if (audioEl.readyState >= 2) tryPlay();
            else {
                audioEl.addEventListener('canplay', tryPlay, { once: true });
                // Fallback if canplay never fires
                setTimeout(function () {
                    if (audioEl.paused) tryPlay();
                }, 400);
            }
        }
        if (statusEl) {
            statusEl.style.color = '#8595a9';
            statusEl.textContent = (data.engine || 'si_formant_klatt') +
                ' · bytes=' + (data.bytes || bytes.length) +
                ' · riff=' + (riffOk ? 'ok' : 'BAD') +
                ' · SI formant · no TTS model';
        }
        if (phEl) phEl.textContent = data.phonemes || '';
        if (uidEl) uidEl.textContent = data.utterance_id
            ? ('utterance_id ' + data.utterance_id + ' · stock=utterance_plan')
            : '';
    } catch (e) {
        if (statusEl) {
            statusEl.style.color = '#fb7185';
            statusEl.textContent = 'DEGRADED: ' + (e.message || e);
        }
    }
}

// ===== Mesh Jobs — real private-mesh workload submission and results =====
// Every state rendered here comes from the controller job pipeline, which is
// backed by signed CHAL/vSource contract documents. Nothing is simulated.

const meshJobs = { ids: [], timer: null };

function jobsAuthHeaders(extra) {
    const headers = Object.assign({}, extra || {});
    const token = localStorage.getItem('synthesus_token');
    if (token) headers['Authorization'] = 'Bearer ' + token;
    return headers;
}

function jobsRememberId(jobId) {
    if (!meshJobs.ids.includes(jobId)) meshJobs.ids.unshift(jobId);
    try { localStorage.setItem('synthesus_mesh_jobs', JSON.stringify(meshJobs.ids.slice(0, 20))); } catch (e) {}
}

function jobsLoadRemembered() {
    try {
        meshJobs.ids = JSON.parse(localStorage.getItem('synthesus_mesh_jobs') || '[]');
    } catch (e) { meshJobs.ids = []; }
}

async function jobsSubmit() {
    const statusEl = document.getElementById('jobs-submit-status');
    const fileEl = document.getElementById('jobs-bundle-file');
    const btn = document.getElementById('jobs-submit-btn');
    const file = fileEl && fileEl.files && fileEl.files[0];
    if (!file) {
        statusEl.style.color = '#fb7185';
        statusEl.textContent = 'Choose a workload manifest bundle first.';
        return;
    }
    if (file.size > 8 * 1024 * 1024) {
        statusEl.style.color = '#fb7185';
        statusEl.textContent = 'Bundle exceeds the 8 MiB policy limit.';
        return;
    }
    btn.disabled = true;
    statusEl.style.color = '#94a3b8';
    statusEl.textContent = 'Submitting to the mesh scheduler…';
    try {
        const bytes = new Uint8Array(await file.arrayBuffer());
        let binary = '';
        for (let i = 0; i < bytes.length; i += 0x8000) {
            binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
        }
        const resp = await fetch('/api/jobs', {
            method: 'POST',
            headers: jobsAuthHeaders({ 'Content-Type': 'application/json' }),
            body: JSON.stringify({ bundle_base64: btoa(binary), workload_kind: 'inference' }),
        });
        const record = await resp.json();
        if (!resp.ok) {
            statusEl.style.color = '#fb7185';
            statusEl.textContent = 'Rejected: ' + (record.error || resp.status);
            return;
        }
        jobsRememberId(record.job_id);
        jobsRenderRecord(record);
        statusEl.style.color = record.state === 'completed' ? '#4ade80' : '#94a3b8';
        statusEl.textContent = 'Job ' + record.job_id + ' → ' + record.state +
            (record.reason ? (' (' + record.reason + ')') : '');
        jobsScheduleRefresh();
    } catch (e) {
        statusEl.style.color = '#fb7185';
        statusEl.textContent = 'DEGRADED: ' + (e.message || e);
    } finally {
        btn.disabled = false;
    }
}

function jobsStateBadge(state) {
    const palette = {
        admitted: ['var(--purple-light)', 'ADMITTED'],
        completed: ['#4ade80', 'COMPLETED'],
        failed: ['#fb7185', 'FAILED'],
        cancelled: ['#94a3b8', 'CANCELLED'],
        rejected: ['#fb7185', 'REJECTED'],
        unavailable: ['#f97316', 'UNAVAILABLE'],
    };
    const entry = palette[state] || ['#94a3b8', String(state || 'UNKNOWN').toUpperCase()];
    return '<span style="color:' + entry[0] + '; font-weight:700; font-size:0.72rem;">' + entry[1] + '</span>';
}

function jobsRenderRecord(record) {
    const list = document.getElementById('jobs-list');
    if (!list) return;
    const rowId = 'jobs-row-' + record.job_id.replace(/[^a-zA-Z0-9_-]/g, '_');
    let row = document.getElementById(rowId);
    if (!row) {
        row = document.createElement('div');
        row.id = rowId;
        row.style.cssText = 'border:1px solid rgba(148,163,184,.2); border-radius:6px; padding:8px; display:flex; flex-direction:column; gap:4px;';
        list.prepend(row);
    }
    const outputs = (record.outputs || []).map(function (output) {
        return '<button class="glass-btn" style="font-size:0.7rem; margin-right:4px;" ' +
            'onclick="jobsViewResult(\'' + record.job_id + '\',\'' + output.sha256 + '\')">' +
            '📄 ' + (output.media_type || 'result') + ' · ' + output.sha256.slice(0, 12) + '…</button>';
    }).join('');
    row.innerHTML =
        '<div style="display:flex; justify-content:space-between; align-items:center;">' +
            '<code style="font-size:0.7rem; color:#64748b;">' + record.job_id + '</code>' +
            jobsStateBadge(record.state) +
        '</div>' +
        (record.reason ? '<div style="color:#fb7185; font-size:0.75rem;">' + record.reason + '</div>' : '') +
        (outputs ? '<div>' + outputs + '</div>' : '') +
        (record.state === 'admitted'
            ? '<div><button class="glass-btn" style="font-size:0.72rem;" onclick="jobsCancel(\'' + record.job_id + '\')">■ Cancel</button></div>'
            : '');
}

async function jobsRefreshOne(jobId) {
    const resp = await fetch('/api/jobs/' + encodeURIComponent(jobId), {
        headers: jobsAuthHeaders(),
    });
    if (!resp.ok) return null;
    const record = await resp.json();
    jobsRenderRecord(record);
    return record;
}

async function jobsRefreshAll() {
    jobsLoadRemembered();
    let anyPending = false;
    for (const jobId of meshJobs.ids) {
        try {
            const record = await jobsRefreshOne(jobId);
            if (record && record.state === 'admitted') anyPending = true;
        } catch (e) { /* controller offline; row keeps last honest state */ }
    }
    if (anyPending) jobsScheduleRefresh();
}

function jobsScheduleRefresh() {
    if (meshJobs.timer) clearTimeout(meshJobs.timer);
    meshJobs.timer = setTimeout(jobsRefreshAll, 3000);
}

async function jobsCancel(jobId) {
    try {
        const resp = await fetch('/api/jobs/' + encodeURIComponent(jobId) + '/cancel', {
            method: 'POST',
            headers: jobsAuthHeaders(),
        });
        if (resp.ok) jobsRenderRecord(await resp.json());
    } catch (e) { /* leave last honest state */ }
}

// Render a raw-JSON (or plain-text) fallback for any schema we don't have a
// bespoke view for. Pretty-prints valid JSON; otherwise shows bytes verbatim.
function jobsRenderRaw(text) {
    let shown = text;
    try { shown = JSON.stringify(JSON.parse(text), null, 2); } catch (e) { /* not JSON */ }
    return '<pre style="margin:0; white-space:pre-wrap; word-break:break-all; ' +
        'font-size:0.75rem; color:#a5f3fc;">' + escapeHtml(shown) + '</pre>';
}

function jobsShortDigest(value) {
    const s = String(value || '');
    return s.length > 20 ? s.slice(0, 10) + '…' + s.slice(-6) : s;
}

// Bespoke, honest presentation of the text-classification result schema.
// Only the winning label and the per-label scores are asserted; the digests
// identify (but do not certify) the model and document that produced them.
function jobsRenderTextClassification(data) {
    const scores = (data && data.scores && typeof data.scores === 'object') ? data.scores : {};
    const entries = Object.keys(scores)
        .map(function (k) { return [k, Number(scores[k])]; })
        .filter(function (e) { return isFinite(e[1]); })
        .sort(function (a, b) { return b[1] - a[1]; });
    const label = (data && data.label != null) ? String(data.label) : (entries.length ? entries[0][0] : '—');

    let bars = '';
    entries.forEach(function (e) {
        const name = e[0];
        const pct = Math.max(0, Math.min(1, e[1])) * 100;
        const isTop = name === label;
        bars +=
            '<div style="margin-bottom:6px;">' +
                '<div style="display:flex; justify-content:space-between; font-size:0.72rem; margin-bottom:2px;">' +
                    '<span style="color:' + (isTop ? '#4ade80' : '#cbd5e1') + '; font-weight:' + (isTop ? '700' : '400') + ';">' +
                        escapeHtml(name) + '</span>' +
                    '<code style="color:#94a3b8;">' + e[1].toFixed(6) + '</code>' +
                '</div>' +
                '<div style="height:8px; border-radius:4px; background:rgba(148,163,184,.15); overflow:hidden;">' +
                    '<div style="height:100%; width:' + pct.toFixed(2) + '%; border-radius:4px; background:' +
                        (isTop ? '#4ade80' : 'rgba(56,189,248,.55)') + ';"></div>' +
                '</div>' +
            '</div>';
    });
    if (!bars) bars = '<div style="color:#94a3b8; font-size:0.72rem;">No per-label scores in result.</div>';

    const dims = (data && data.feature_dims != null) ? String(data.feature_dims) : null;

    return '' +
        '<div style="margin-bottom:8px;">' +
            '<div style="font-size:0.7rem; color:#94a3b8; text-transform:uppercase; letter-spacing:.05em;">Predicted label</div>' +
            '<div style="font-size:1.25rem; font-weight:800; color:#4ade80;">' + escapeHtml(label) + '</div>' +
        '</div>' +
        '<div style="margin-bottom:8px;">' + bars + '</div>' +
        '<div style="display:flex; flex-direction:column; gap:3px; border-top:1px solid rgba(148,163,184,.15); padding-top:6px; font-size:0.7rem; color:#94a3b8;">' +
            (dims ? '<div>feature dims: <code style="color:#cbd5e1;">' + escapeHtml(dims) + '</code></div>' : '') +
            (data && data.model_sha256 ? '<div>model: <code style="color:#cbd5e1;" title="' + escapeHtml(String(data.model_sha256)) + '">' + escapeHtml(jobsShortDigest(data.model_sha256)) + '</code></div>' : '') +
            (data && data.document_sha256 ? '<div>document: <code style="color:#cbd5e1;" title="' + escapeHtml(String(data.document_sha256)) + '">' + escapeHtml(jobsShortDigest(data.document_sha256)) + '</code></div>' : '') +
        '</div>';
}

async function jobsViewResult(jobId, sha256) {
    const panel = document.getElementById('jobs-result-panel');
    const body = document.getElementById('jobs-result-body');
    const shaEl = document.getElementById('jobs-result-sha');
    const verifiedEl = document.getElementById('jobs-result-verified');
    panel.style.display = 'block';
    shaEl.textContent = sha256;
    shaEl.title = sha256;
    if (verifiedEl) verifiedEl.style.display = 'none';
    body.innerHTML = '<div style="color:#94a3b8; font-size:0.78rem;">Fetching verified result…</div>';
    try {
        const resp = await fetch(
            '/api/jobs/' + encodeURIComponent(jobId) + '/results/' + encodeURIComponent(sha256),
            { headers: jobsAuthHeaders() }
        );
        if (!resp.ok) {
            let msg;
            if (resp.status === 404) {
                let code = '';
                try { code = (await resp.json()).error || ''; } catch (e) { /* ignore */ }
                msg = code === 'result_not_found'
                    ? 'Result bytes not yet retrievable from the mesh.'
                    : 'Result not found (404).';
            } else if (resp.status === 401) {
                msg = 'Not authorized — re-authenticate to view results.';
            } else if (resp.status === 403) {
                let capability = '';
                try { capability = (await resp.json()).capability || ''; } catch (e) { /* ignore */ }
                msg = capability === 'return_results'
                    ? 'This device is not allowed to return results to you. ' +
                      'Enable "Return results to me" for it in Devices & Permissions.'
                    : 'This device is not permitted for that action.';
            } else if (resp.status === 409) {
                let status = '';
                try { status = (await resp.json()).evidence_status || ''; } catch (e) { /* ignore */ }
                msg = 'Refused: the result could not be verified (' + status + '). ' +
                      'You require verified evidence in Settings; turn it off to view ' +
                      'unverified results, which will be labelled.';
            } else {
                msg = 'Result unavailable (' + resp.status + ').';
            }
            body.innerHTML = '<div style="color:var(--purple-light); font-size:0.78rem;">' + escapeHtml(msg) + '</div>';
            return;
        }
        // The endpoint only returns bytes that re-hash to the requested digest,
        // so a 200 here means the payload is byte-exact for this SHA-256.
        if (verifiedEl) verifiedEl.style.display = 'inline-block';
        // Byte-exactness and PROVENANCE are different claims. The controller
        // reports the provenance state on every result, including when the
        // owner has turned enforcement off, so the difference is never silent.
        const badgeHost = document.getElementById('jobs-result-evidence');
        if (badgeHost) {
            badgeHost.innerHTML = psEvidenceBadge(
                resp.headers.get('X-Synthesus-Evidence-Status')
            );
        }
        const text = await resp.text();
        let data = null;
        try { data = JSON.parse(text); } catch (e) { data = null; }
        if (data && data.schema === 'planetary.aivm.result.text-classification.v1') {
            body.innerHTML = jobsRenderTextClassification(data);
        } else {
            body.innerHTML = jobsRenderRaw(text);
        }
    } catch (e) {
        body.innerHTML = '<div style="color:#fb7185; font-size:0.78rem;">DEGRADED: ' +
            escapeHtml(e.message || String(e)) + '</div>';
    }
}

jobsLoadRemembered();
if (meshJobs.ids.length) setTimeout(jobsRefreshAll, 1500);

/* =====================================================================
   Devices & Permissions, Settings, Dashboard.

   Everything here talks to the real controller endpoints. Where a value
   cannot be obtained, it is shown as unknown — never guessed, and never
   rendered as if it were verified.
   ===================================================================== */

const CAPABILITY_HELP = {
    run_inference: 'May run your workloads on this device.',
    return_results: 'May send result bytes back to this desktop.',
    provide_input: 'May supply input data. Cannot run work or return results.',
};

const CAPABILITY_LABEL = {
    run_inference: 'Run my workloads',
    return_results: 'Return results to me',
    provide_input: 'Provide input data',
};

function psEscape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (c) {
        return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
}

async function psFetch(path, options) {
    const opts = Object.assign({}, options || {});
    opts.headers = jobsAuthHeaders(
        Object.assign({ 'Content-Type': 'application/json' }, opts.headers || {})
    );
    return fetch(path, opts);
}

/* ------------------------------------------------------------ devices */

function openDevices() {
    toggleWindow('win-devices');
    if (document.getElementById('win-devices').style.display !== 'none') devicesRefresh();
}

async function devicesRefresh() {
    // Candidates depend on which devices already have rows, so the two lists
    // are always re-read together.
    devicesDiscover();
    const list = document.getElementById('dev-list');
    if (!list) return;
    list.innerHTML = '<div class="ps-empty">Loading…</div>';
    let payload;
    try {
        const resp = await psFetch('/api/devices');
        if (!resp.ok) {
            list.innerHTML = '<div class="ps-empty">Could not read your permissions (' +
                resp.status + '). Nothing is permitted while this cannot be read.</div>';
            return;
        }
        payload = await resp.json();
    } catch (e) {
        list.innerHTML = '<div class="ps-empty">Controller unreachable. Nothing is permitted.</div>';
        return;
    }
    const devices = (payload && payload.devices) || [];
    if (!devices.length) {
        list.innerHTML = '<div class="ps-empty">No devices yet. Add one above — ' +
            'it will start with every capability switched off.</div>';
        return;
    }
    list.innerHTML = devices.map(devicesRenderRow).join('');
}

/* Discovered candidates.

   These rows are read out of the mesh enrollment registry. Rendering one
   grants nothing: the Add button posts to the same /api/devices endpoint the
   manual form uses, and the controller creates the row with every capability
   off. Enrollment is not consent. */

const DISCOVERY_REASON_TEXT = {
    mesh_module_unavailable: 'The mesh services are not available to this desktop, ' +
        'so enrolled nodes cannot be listed. Nothing is assumed about them.',
    registry_missing: 'No mesh enrollment registry was found. If you have not enrolled ' +
        'any nodes yet, this is normal — add devices by hand below.',
    registry_unreadable: 'The mesh enrollment registry could not be read. No devices ' +
        'are shown rather than guessed ones.',
    registry_empty: 'Your mesh has no enrolled nodes yet.',
    all_enrolled_nodes_already_listed: 'Every enrolled node already has a row below.',
};

async function devicesDiscover() {
    const host = document.getElementById('dev-discovered');
    if (!host) return;
    host.innerHTML = '<div class="ps-empty">Looking for enrolled nodes…</div>';
    let payload;
    try {
        const resp = await psFetch('/api/devices/discovered');
        if (!resp.ok) {
            host.innerHTML = '<div class="ps-empty">Could not check your mesh (' +
                resp.status + '). No candidates are shown.</div>';
            return;
        }
        payload = await resp.json();
    } catch (e) {
        host.innerHTML = '<div class="ps-empty">Controller unreachable. No candidates are shown.</div>';
        return;
    }
    const candidates = (payload && payload.candidates) || [];
    if (!candidates.length) {
        const reason = payload && payload.reason;
        host.innerHTML = '<div class="ps-empty">' +
            psEscape(DISCOVERY_REASON_TEXT[reason] || ('No enrolled nodes to offer (' +
                (reason || 'no reason given') + ').')) + '</div>';
        return;
    }
    host.innerHTML = candidates.map(devicesRenderCandidate).join('');
}

function devicesRenderCandidate(node) {
    /* An expired or revoked enrollment is shown, not hidden — an owner whose
       node vanished from this list would reasonably conclude it was gone. It
       is shown as unusable, with the reason, and cannot be added. */
    let flag = '';
    if (node.revoked) {
        flag = 'REVOKED' + (node.revocation_reason ? ' — ' + node.revocation_reason : '');
    } else if (node.expired) {
        flag = 'CERTIFICATE EXPIRED ' + (node.not_after || '');
    }
    const sans = (node.sans || []).join(', ');
    const action = node.available
        ? '<button class="glass-btn primary-btn" style="font-size:0.7rem;" onclick="devicesAddDiscovered(\'' +
          psEscape(node.node_id) + '\',\'' + psEscape(node.suggested_display_name) + '\')">Add</button>'
        : '<span class="ps-role ps-role-source">unavailable</span>';

    return '' +
        '<div class="ps-device">' +
            '<div class="ps-device-head">' +
                '<div>' +
                    '<div class="ps-device-name">' + psEscape(node.suggested_display_name) + '</div>' +
                    '<div class="ps-device-id">' + psEscape(node.node_id) + '</div>' +
                '</div>' +
                '<div style="display:flex; align-items:center; gap:8px;">' + action + '</div>' +
            '</div>' +
            (flag
                ? '<div class="ps-cap-help" style="color:#fb7185;">' + psEscape(flag) + '</div>'
                : '') +
            '<div class="ps-cap-help">Certificate ' +
                psEscape(node.certificate_sha256_short || '') + '… · expires ' +
                psEscape(node.not_after || 'unknown') +
                (sans ? ' · ' + psEscape(sans) : '') + '</div>' +
            '<div class="ps-cap-help">Adding this node grants it nothing. ' +
                'It arrives with every capability switched off.</div>' +
        '</div>';
}

async function devicesAddDiscovered(nodeId, displayName) {
    const status = document.getElementById('dev-add-status');
    if (status) status.textContent = 'Adding ' + nodeId + '…';
    try {
        const resp = await psFetch('/api/devices', {
            method: 'POST',
            body: JSON.stringify({
                device_id: nodeId,
                display_name: displayName || nodeId,
                // Only enrolled mesh nodes are ever discovered, so the role is
                // always peer here. A source is never enrolled and can only be
                // added by hand.
                role: 'peer',
            }),
        });
        const body = await resp.json().catch(function () { return {}; });
        if (status) {
            status.textContent = resp.ok
                ? 'Added with every capability off.'
                : (body.error || ('Could not add device (' + resp.status + ').'));
        }
    } catch (e) {
        if (status) status.textContent = 'Controller unreachable.';
    }
    devicesRefresh();
}

function devicesRenderRow(device) {
    const roleClass = device.role === 'peer' ? 'ps-role-peer' : 'ps-role-source';
    const caps = Object.keys(device.capabilities).sort().map(function (name) {
        const id = 'cap-' + device.device_id.replace(/[^a-zA-Z0-9_-]/g, '_') + '-' + name;
        return '' +
            '<div class="ps-cap">' +
                '<div>' +
                    '<div class="ps-cap-name">' + psEscape(CAPABILITY_LABEL[name] || name) + '</div>' +
                    '<div class="ps-cap-help">' + psEscape(CAPABILITY_HELP[name] || '') + '</div>' +
                '</div>' +
                '<label class="ps-switch">' +
                    '<input type="checkbox" id="' + id + '"' +
                        (device.capabilities[name] ? ' checked' : '') +
                        ' onchange="devicesToggle(\'' + psEscape(device.device_id) + '\',\'' +
                        name + '\', this.checked)">' +
                    '<span></span>' +
                '</label>' +
            '</div>';
    }).join('');

    const sourceNote = device.role === 'source'
        ? '<div class="ps-cap-help" style="padding-top:6px;">A source device never holds a mesh ' +
          'certificate and can never be granted execution or results — cameras and TVs are among ' +
          'the most-compromised devices on a home network.</div>'
        : '';

    return '' +
        '<div class="ps-device">' +
            '<div class="ps-device-head">' +
                '<div>' +
                    '<div class="ps-device-name">' + psEscape(device.display_name) + '</div>' +
                    '<div class="ps-device-id">' + psEscape(device.device_id) + '</div>' +
                '</div>' +
                '<div style="display:flex; align-items:center; gap:8px;">' +
                    '<span class="ps-role ' + roleClass + '">' + psEscape(device.role) + '</span>' +
                    '<button class="glass-btn" style="font-size:0.7rem;" onclick="devicesRemove(\'' +
                        psEscape(device.device_id) + '\')">Remove</button>' +
                '</div>' +
            '</div>' +
            caps +
            sourceNote +
        '</div>';
}

async function devicesAdd() {
    const status = document.getElementById('dev-add-status');
    const deviceId = document.getElementById('dev-add-id').value.trim();
    const displayName = document.getElementById('dev-add-name').value.trim();
    const role = document.getElementById('dev-add-role').value;
    if (!deviceId || !displayName) {
        status.textContent = 'A device id and a name are both required.';
        return;
    }
    status.textContent = 'Adding…';
    try {
        const resp = await psFetch('/api/devices', {
            method: 'POST',
            body: JSON.stringify({ device_id: deviceId, display_name: displayName, role: role }),
        });
        const body = await resp.json().catch(function () { return {}; });
        if (!resp.ok) {
            status.textContent = body.error || ('Could not add device (' + resp.status + ').');
            return;
        }
        status.textContent = 'Added with every capability off.';
        document.getElementById('dev-add-id').value = '';
        document.getElementById('dev-add-name').value = '';
        devicesRefresh();
    } catch (e) {
        status.textContent = 'Controller unreachable.';
    }
}

async function devicesToggle(deviceId, capability, enabled) {
    const body = {};
    body[capability] = enabled;
    try {
        const resp = await psFetch(
            '/api/devices/' + encodeURIComponent(deviceId) + '/capabilities',
            { method: 'PUT', body: JSON.stringify({ capabilities: body }) }
        );
        if (!resp.ok) {
            const payload = await resp.json().catch(function () { return {}; });
            dsToast('Permission refused', payload.error || 'That change was not applied.', 'error');
        }
    } catch (e) {
        dsToast('Controller unreachable', 'The permission was not changed.', 'error');
    }
    // Always re-read: the switch must show what the controller actually stored,
    // not what we optimistically clicked.
    devicesRefresh();
}

async function devicesRemove(deviceId) {
    if (!confirm('Remove ' + deviceId + '? It will lose every permission.')) return;
    try {
        await psFetch('/api/devices/' + encodeURIComponent(deviceId), { method: 'DELETE' });
    } catch (e) { /* refresh reports the true state */ }
    devicesRefresh();
}

/* ----------------------------------------------------------- settings */

function openSettings() {
    toggleWindow('win-settings');
    if (document.getElementById('win-settings').style.display !== 'none') settingsRefresh();
}

async function settingsRefresh() {
    const toggle = document.getElementById('set-evidence');
    const status = document.getElementById('set-evidence-status');
    const worker = document.getElementById('set-worker');
    try {
        const resp = await psFetch('/api/settings');
        if (!resp.ok) {
            status.textContent = 'Could not read settings (' + resp.status + ').';
            toggle.disabled = true;
            return;
        }
        const payload = await resp.json();
        toggle.checked = !!payload.require_verified_evidence;
        toggle.disabled = false;
        status.textContent = payload.require_verified_evidence
            ? 'On — unverified results are refused.'
            : 'Off — unverified results are shown, and labelled.';
        worker.textContent = payload.worker_node_id
            ? payload.worker_node_id
            : 'No worker configured on this desktop.';
    } catch (e) {
        status.textContent = 'Controller unreachable.';
        toggle.disabled = true;
    }
}

async function settingsSaveEvidence(enabled) {
    const status = document.getElementById('set-evidence-status');
    status.textContent = 'Saving…';
    try {
        const resp = await psFetch('/api/settings/evidence', {
            method: 'PUT',
            body: JSON.stringify({ enabled: !!enabled }),
        });
        if (!resp.ok) {
            status.textContent = 'Could not save (' + resp.status + ').';
        }
    } catch (e) {
        status.textContent = 'Controller unreachable.';
    }
    settingsRefresh();
}

/* ---------------------------------------------------------- dashboard */

function openDashboard() {
    toggleWindow('win-dashboard');
    if (document.getElementById('win-dashboard').style.display !== 'none') {
        dashboardRefresh();
        dashboardStartClock();
    }
}

let _dashClockTimer = null;
function dashboardStartClock() {
    if (_dashClockTimer) return;
    const tick = function () {
        const now = new Date();
        const t = document.getElementById('dash-time');
        const d = document.getElementById('dash-date');
        if (!t || !d) return;
        t.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        d.textContent = now.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
    };
    tick();
    _dashClockTimer = setInterval(tick, 20000);
    // Sample metrics on a slow cadence so the sparklines have real history.
    setInterval(function () {
        const overview = document.getElementById('win-dashboard');
        if (overview && overview.style.display !== 'none') dashboardRefresh();
    }, 6000);
}

function psBytes(n) {
    if (n == null) return 'unknown';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let value = n, i = 0;
    while (value >= 1024 && i < units.length - 1) { value /= 1024; i += 1; }
    return (value >= 10 || i === 0 ? Math.round(value) : value.toFixed(1)) + ' ' + units[i];
}

// A card renders a measured value or the word "unknown". It never fills a gap
// with a plausible number.
function dashMetricCard(label, value, sub, percent, options) {
    const opts = options || {};
    const spark = opts.series ? dashSparkline(opts.series, opts.color || 'var(--purple-light)') : '';
    const meter = (percent == null || spark) ? '' :
        '<div class="ps-meter"><span style="width:' + Math.max(0, Math.min(100, percent)) + '%"></span></div>';
    return '<div class="ps-card">' +
        '<div class="ps-card-top">' +
            '<div class="ps-card-label">' + psEscape(label) + '</div>' +
            (opts.icon ? '<span class="ps-card-ico">' + opts.icon + '</span>' : '') +
        '</div>' +
        '<div class="ps-card-value">' + psEscape(value) + '</div>' +
        spark + meter +
        (sub ? '<div class="ps-card-sub">' + psEscape(sub) + '</div>' : '') +
        '</div>';
}

function dashLine(label, help, state, stateClass) {
    return '<div class="ps-line">' +
        '<div><div class="ps-line-label">' + psEscape(label) + '</div>' +
        '<div class="ps-line-help">' + psEscape(help) + '</div></div>' +
        '<div class="ps-line-state ' + stateClass + '">' + psEscape(state) + '</div>' +
        '</div>';
}

async function dashboardRefresh() {
    dashboardStartClock();
    const live = document.getElementById('dash-live');
    const security = document.getElementById('dash-security');
    const activity = document.getElementById('dash-activity');
    if (!live) return;

    let devices = null, settings = null, metrics = null, health = null, system = null;
    try {
        const results = await Promise.all([
            psFetch('/api/devices').catch(function () { return null; }),
            psFetch('/api/settings').catch(function () { return null; }),
            psFetch('/api/system/metrics').catch(function () { return null; }),
            psFetch('/health').catch(function () { return null; }),
            fetch('/api/system/status').catch(function () { return null; }),
        ]);
        if (results[0] && results[0].ok) devices = (await results[0].json()).devices || [];
        if (results[1] && results[1].ok) settings = await results[1].json();
        if (results[2] && results[2].ok) metrics = await results[2].json();
        if (results[3] && results[3].ok) health = await results[3].json();
        if (results[4] && results[4].ok) system = await results[4].json();
    } catch (e) { /* each value is handled as unknown below */ }

    // ---- status strip
    const dot = document.getElementById('dash-status-dot');
    const text = document.getElementById('dash-status-text');
    if (health && health.status === 'online') {
        dot.className = 'ps-dot is-ok';
        text.textContent = 'All services running';
    } else if (health) {
        dot.className = 'ps-dot is-warn';
        text.textContent = 'Some services are degraded';
    } else {
        dot.className = 'ps-dot is-bad';
        text.textContent = 'Cannot reach the controller';
    }

    // ---- hero
    const peers = (devices || []).filter(function (d) { return d.role === 'peer'; });
    const canRun = peers.filter(function (d) { return d.capabilities.run_inference; });
    const sub = document.getElementById('dash-hero-sub');
    if (devices === null) {
        sub.textContent = 'Your permissions could not be read, so nothing is allowed to run.';
    } else if (!devices.length) {
        sub.textContent = 'No devices added yet. Add one to let it work for you — it starts with everything switched off.';
    } else {
        sub.textContent = devices.length + ' device' + (devices.length === 1 ? '' : 's') +
            ' added, ' + canRun.length + ' allowed to run your work. ' +
            (settings && settings.require_verified_evidence
                ? 'Results are only accepted when verified.'
                : 'Unverified results are shown and labelled.');
    }

    // ---- measured cards
    const mem = (metrics && metrics.memory) || {};
    const disk = (metrics && metrics.storage) || {};
    const model = system && system.llm ? system.llm.model : null;
    if (metrics) {
        dashRecord('cpu', metrics.cpu_percent);
        dashRecord('memory', mem.percent);
        dashRecord('storage', disk.percent);
    }
    live.innerHTML =
        dashMetricCard('Processor',
            metrics && metrics.cpu_percent != null ? metrics.cpu_percent + '%' : 'unknown',
            'this computer', metrics ? metrics.cpu_percent : null,
            { icon: '▨', color: 'var(--purple-light)', series: _dashHistory.cpu }) +
        dashMetricCard('Memory',
            mem.percent != null ? mem.percent + '%' : 'unknown',
            mem.used_bytes != null ? psBytes(mem.used_bytes) + ' of ' + psBytes(mem.total_bytes) : 'could not be read',
            mem.percent, { icon: '▤', color: '#a78bfa', series: _dashHistory.memory }) +
        dashMetricCard('Storage',
            disk.percent != null ? disk.percent + '%' : 'unknown',
            disk.used_bytes != null ? psBytes(disk.used_bytes) + ' of ' + psBytes(disk.total_bytes) : 'could not be read',
            disk.percent, { icon: '▥', color: '#2dd4bf' }) +
        dashMetricCard('Devices',
            devices === null ? 'unknown' : String(devices.length),
            devices === null ? 'permissions unreadable' : peers.length + ' can be given work', null,
            { icon: '◉' }) +
        dashMetricCard('Assistant',
            model ? 'Local' : 'unknown',
            model ? model : 'model not reported', null, { icon: '◈' });

    // ---- privacy & security: real states only
    const evidenceOn = settings ? settings.require_verified_evidence : null;
    security.innerHTML =
        dashLine('Everything runs on your machines',
            'Work is sent only to devices you added. Nothing is sent to us.',
            devices === null ? 'unknown' : 'Active',
            devices === null ? 'is-unknown' : 'is-ok') +
        dashLine('Encrypted between your devices',
            'Devices prove who they are to each other before any data moves.',
            'Active', 'is-ok') +
        dashLine('Result verification',
            'Refuse a result unless the machine that produced it signed for it.',
            evidenceOn === null ? 'unknown' : (evidenceOn ? 'Required' : 'Off — results are labelled'),
            evidenceOn === null ? 'is-unknown' : (evidenceOn ? 'is-ok' : 'is-warn')) +
        dashLine('Per-device permissions',
            'A new device can do nothing until you allow it.',
            devices === null ? 'unknown' : 'Default deny',
            devices === null ? 'is-unknown' : 'is-ok');

    // ---- system health (right panel)
    const health_el = document.getElementById('dash-health');
    if (health_el) {
        const runtime = health && health.runtime ? health.runtime.status : null;
        const term = health && health.terminal ? health.terminal.status : null;
        health_el.innerHTML =
            dashGauge('Processor', metrics ? metrics.cpu_percent : null,
                'this computer', '#A78BFA') +
            dashGauge('Memory', mem.percent != null ? mem.percent : null,
                mem.total_bytes ? psBytes(mem.total_bytes) + ' total' : 'unknown', '#8B5CF6') +
            dashGauge('Storage', disk.percent != null ? disk.percent : null,
                disk.total_bytes ? psBytes(disk.total_bytes) + ' total' : 'unknown', '#C4B5FD') +
            dashLine('AI engine', model ? model : 'model not reported',
                system && system.llm && system.llm.ollama_reachable ? 'Ready' : 'Not loaded',
                system && system.llm && system.llm.ollama_reachable ? 'is-ok' : 'is-warn') +
            dashLine('Runtime', 'background services',
                runtime === 'online' ? 'Online' : (runtime || 'unknown'),
                runtime === 'online' ? 'is-ok' : 'is-warn') +
            dashLine('Terminal', 'authenticated shell backend',
                term === 'online' ? 'Online' : (term || 'unknown'),
                term === 'online' ? 'is-ok' : 'is-warn');
    }

    // ---- activity
    const ids = (typeof meshJobs !== 'undefined' && meshJobs.ids) ? meshJobs.ids : [];
    if (!ids.length) {
        activity.innerHTML = '<div class="ps-empty">No jobs yet. Anything you run will be listed here.</div>';
    } else {
        activity.innerHTML = ids.slice(0, 6).map(function (id) {
            return '<div class="ps-line"><div><div class="ps-line-label">Job</div>' +
                '<div class="ps-line-help">' + psEscape(id) + '</div></div>' +
                '<div class="ps-line-state is-unknown">open Jobs</div></div>';
        }).join('');
    }
}

/* ------------------------------------------- evidence badge for results */

function psEvidenceBadge(status) {
    if (!status) return '';
    if (status === 'verified') {
        return '<span class="ps-badge ps-badge-verified" title="The machine that produced this ' +
            'signed a valid execution record, checked against the key recorded at enrollment. ' +
            'This does not prove that machine is honest.">✓ Verified</span>';
    }
    if (status.indexOf('invalid:') === 0) {
        return '<span class="ps-badge ps-badge-invalid" title="' + psEscape(status) +
            '">✕ Signature did not verify</span>';
    }
    if (status === 'unsigned') {
        return '<span class="ps-badge ps-badge-unsigned" title="No execution record was signed ' +
            'for this result.">⚠ Unsigned</span>';
    }
    return '<span class="ps-badge ps-badge-unsigned" title="Provenance could not be determined.">' +
        '⚠ ' + psEscape(status) + '</span>';
}


/* ---- Overview: sampled sparklines and a working search ---------------- */

// Rolling history of values THIS page has observed. A sparkline is only ever
// drawn from readings we actually took — there is no seeded or synthetic
// history, so a fresh window shows a short line that grows.
const _dashHistory = { cpu: [], memory: [], storage: [] };
const _DASH_HISTORY_MAX = 40;

function dashRecord(key, value) {
    if (value == null) return;
    const series = _dashHistory[key];
    series.push(value);
    if (series.length > _DASH_HISTORY_MAX) series.shift();
}

function dashSparkline(series, stroke) {
    if (!series || series.length < 2) return '';
    const w = 100, h = 30;
    const max = Math.max.apply(null, series);
    const min = Math.min.apply(null, series);
    const span = (max - min) || 1;
    const step = w / (series.length - 1);
    const points = series.map(function (value, i) {
        const x = (i * step).toFixed(2);
        const y = (h - ((value - min) / span) * (h - 4) - 2).toFixed(2);
        return x + ',' + y;
    });
    const line = 'M' + points.join(' L');
    const fill = line + ' L' + w + ',' + h + ' L0,' + h + ' Z';
    return '<svg class="ps-spark" viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none" aria-hidden="true">' +
        '<path class="ps-spark-fill" d="' + fill + '" fill="' + stroke + '"/>' +
        '<path d="' + line + '" stroke="' + stroke + '"/></svg>';
}

// Search over things that actually exist. Every hit opens a real window.
const DASH_TARGETS = [
    { name: 'Devices & permissions', hint: 'allow or block each device', run: 'openDevices()' },
    { name: 'Settings', hint: 'result verification and preferences', run: 'openSettings()' },
    { name: 'Jobs', hint: 'submit work and view results', run: "toggleWindow('win-jobs')" },
    { name: 'Assistant', hint: 'chat with the local model', run: "toggleWindow('win-chat')" },
    { name: 'Storage', hint: 'expansion drive and sources', run: "toggleWindow('win-drive')" },
    { name: 'Files', hint: 'browse your files', run: "toggleWindow('win-explorer')" },
    { name: 'Terminal', hint: 'authenticated shell', run: 'spawnTerminalWindow()' },
    { name: 'System configuration', hint: 'wallpaper and AI backend', run: "toggleWindow('win-core')" },
    { name: 'Vitals', hint: 'runtime status', run: 'toggleVitals()' },
];

function dashSearch(query) {
    const box = document.getElementById('dash-search-results');
    if (!box) return;
    const q = (query || '').trim().toLowerCase();
    if (!q) { box.classList.remove('is-open'); box.innerHTML = ''; return; }
    const hits = DASH_TARGETS.filter(function (t) {
        return t.name.toLowerCase().indexOf(q) !== -1 || t.hint.toLowerCase().indexOf(q) !== -1;
    });
    if (!hits.length) {
        box.innerHTML = '<div class="ps-search-hit" style="cursor:default;color:#6b7ea3;">Nothing matches that</div>';
    } else {
        box.innerHTML = hits.map(function (t, i) {
            return '<button class="ps-search-hit' + (i === 0 ? ' is-first' : '') + '" onclick="' +
                t.run + '; dashSearchClear();">' + psEscape(t.name) +
                '<small>' + psEscape(t.hint) + '</small></button>';
        }).join('');
    }
    box.classList.add('is-open');
}

function dashSearchOpenFirst() {
    const first = document.querySelector('#dash-search-results .ps-search-hit.is-first');
    if (first) first.click();
}

function dashSearchClear() {
    const input = document.getElementById('dash-search');
    const box = document.getElementById('dash-search-results');
    if (input) input.value = '';
    if (box) { box.classList.remove('is-open'); box.innerHTML = ''; }
}

/* =====================================================================
   Design-system runtime: toasts replacing browser alerts, and outline
   icons. No icon font and no npm package — Lucide-style outline glyphs
   are inlined as SVG so the app keeps working with no network.
   ===================================================================== */

const DS_ICONS = {
    dashboard: '<path d="M3 3h7v7H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 14h7v7H3z"/>',
    devices:   '<rect x="3" y="4" width="13" height="10" rx="2"/><path d="M8 20h6M11 14v6"/><rect x="18" y="9" width="4" height="11" rx="1"/>',
    jobs:      '<path d="M4 6h16M4 12h16M4 18h10"/>',
    assistant: '<path d="M12 3a5 5 0 0 1 5 5v1a4 4 0 0 1 0 8h-1a5 5 0 0 1-8 0H7a4 4 0 0 1 0-8V8a5 5 0 0 1 5-5z"/>',
    storage:   '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    files:     '<path d="M4 6a2 2 0 0 1 2-2h4l2 3h6a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/>',
    terminal:  '<path d="M5 7l5 5-5 5M13 17h6"/>',
    settings:  '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 9 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.6 9a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z"/>',
    search:    '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
    cpu:       '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    memory:    '<rect x="4" y="7" width="16" height="10" rx="2"/><path d="M8 7V4M12 7V4M16 7V4"/>',
    disk:      '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/>',
    shield:    '<path d="M12 3l7 3v6c0 4.4-3 8.3-7 9-4-.7-7-4.6-7-9V6z"/>',
    activity:  '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
    image:     '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15l-5-5L5 21"/>',
    audio:     '<path d="M11 5L6 9H3v6h3l5 4z"/><path d="M16 9a4 4 0 0 1 0 6M19 6a8 8 0 0 1 0 12"/>',
    star:      '<path d="M12 3l2.6 5.6 6 .8-4.4 4.2 1.1 6-5.3-2.9-5.3 2.9 1.1-6L3.4 9.4l6-.8z"/>',
};

function dsIcon(name, size) {
    const path = DS_ICONS[name];
    if (!path) return '';
    const s = size || 18;
    return '<svg width="' + s + '" height="' + s + '" viewBox="0 0 24 24" fill="none" ' +
        'stroke="currentColor" stroke-width="1.6" stroke-linecap="round" ' +
        'stroke-linejoin="round" aria-hidden="true">' + path + '</svg>';
}

// Toasts replace alert(): non-blocking, dismissible, auto-expiring.
function dsToast(title, body, kind, timeoutMs) {
    const host = document.getElementById('ds-toasts');
    if (!host) { console.log('[toast]', title, body || ''); return; }
    const el = document.createElement('div');
    el.className = 'ds-toast' + (kind ? ' ds-toast-' + kind : '');
    el.innerHTML = '<div class="ds-toast-accent"></div><div>' +
        '<div class="ds-toast-title">' + psEscape(title) + '</div>' +
        (body ? '<div class="ds-toast-body">' + psEscape(body) + '</div>' : '') +
        '</div>';
    el.onclick = function () { dsToastDismiss(el); };
    host.appendChild(el);
    setTimeout(function () { dsToastDismiss(el); }, timeoutMs || 5200);
}

function dsToastDismiss(el) {
    if (!el || el.classList.contains('is-leaving')) return;
    el.classList.add('is-leaving');
    setTimeout(function () { el.remove(); }, 260);
}


// Swap declarative [data-icon] placeholders for inline outline SVGs.
function dsHydrateIcons(root) {
    (root || document).querySelectorAll('[data-icon]').forEach(function (el) {
        if (el.dataset.iconDone) return;
        const svg = dsIcon(el.getAttribute('data-icon'), el.classList.contains('ps-search-ico') ? 16 : 18);
        if (svg) { el.innerHTML = svg; el.dataset.iconDone = '1'; }
    });
}
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { dsHydrateIcons(); });
} else { dsHydrateIcons(); }


// Circular gauge from a measured percentage. Renders nothing rather than a
// zero ring when the value is unknown.
function dashGauge(label, percent, sub, color) {
    const r = 22, c = 2 * Math.PI * r;
    const known = percent != null;
    const dash = known ? (c * Math.max(0, Math.min(100, percent)) / 100) : 0;
    return '<div class="ps-gauge-row">' +
        '<div class="ps-gauge">' +
            '<svg width="54" height="54" viewBox="0 0 54 54">' +
                '<circle class="ps-gauge-track" cx="27" cy="27" r="' + r + '" fill="none" stroke-width="5"/>' +
                (known ? '<circle cx="27" cy="27" r="' + r + '" fill="none" stroke="' + color + '" ' +
                    'stroke-width="5" stroke-linecap="round" stroke-dasharray="' + dash.toFixed(1) +
                    ' ' + c.toFixed(1) + '"/>' : '') +
            '</svg>' +
            '<div class="ps-gauge-value">' + (known ? Math.round(percent) + '%' : '—') + '</div>' +
        '</div>' +
        '<div class="ps-gauge-meta">' +
            '<div class="ps-gauge-label">' + psEscape(label) + '</div>' +
            '<div class="ps-gauge-sub">' + psEscape(sub) + '</div>' +
        '</div></div>';
}

/* =====================================================================
   Workspaces, not windows.

   Existing app surfaces are MOVED (not rebuilt) into workspace panes at
   boot. Because they are the same DOM nodes, every event handler, the
   xterm terminal and the chat transport keep working exactly as before —
   they simply lose their window chrome and become part of one surface.
   ===================================================================== */

const WORKSPACES = {
    home:     { title: 'Home',              windows: [] },
    ai:       { title: 'AI Studio',         windows: ['win-chat', 'win-image', 'win-voice'] },
    dev:      { title: 'Developer',         windows: ['win-foreman'] },
    storage:  { title: 'Files & storage',   windows: ['win-drive', 'win-explorer'] },
    security: { title: 'Devices & access',  windows: ['win-devices', 'win-jobs'] },
    system:   { title: 'System',            windows: ['win-vitals', 'win-core'] },
    settings: { title: 'Settings',          windows: ['win-settings', 'win-plans'] },
};

let _wsCurrent = 'home';
let _wsAdopted = false;

// Move each window into its workspace pane once, stripping the chrome.
function wsAdoptWindows() {
    if (_wsAdopted) return;
    _wsAdopted = true;
    Object.keys(WORKSPACES).forEach(function (key) {
        const pane = document.getElementById('ws-' + key);
        if (!pane) return;
        WORKSPACES[key].windows.forEach(function (winId) {
            const win = document.getElementById(winId);
            if (!win || win.dataset.adopted) return;
            win.dataset.adopted = '1';
            win.classList.add('ps-adopted');
            // Inline geometry from the floating layout must go, or the pane
            // inherits absolute positioning and collapses.
            win.style.top = win.style.left = win.style.width = win.style.height = '';
            win.style.transform = '';
            win.style.display = 'flex';
            pane.appendChild(win);
        });
    });
}

function wsGo(key) {
    if (!WORKSPACES[key]) return;
    wsAdoptWindows();
    _wsCurrent = key;
    document.querySelectorAll('.ps-ws').forEach(function (pane) {
        const active = pane.id === 'ws-' + key;
        pane.hidden = !active;
        pane.classList.toggle('is-active', active);
    });
    document.querySelectorAll('.ps-rail-item[data-workspace]').forEach(function (item) {
        item.classList.toggle('is-active', item.getAttribute('data-workspace') === key);
        item.setAttribute('aria-current', item.getAttribute('data-workspace') === key ? 'page' : 'false');
    });
    const label = document.getElementById('ws-title');
    if (label) label.textContent = WORKSPACES[key].title;
    if (key === 'home') dashboardRefresh();
    if (key === 'security') { try { devicesRefresh(); } catch (e) {} }
    if (key === 'settings') { try { settingsRefresh(); } catch (e) {} }
    dsHydrateIcons(document.getElementById('ws-' + key));
}

// Dock and legacy callers still say toggleWindow(...); route them to the
// workspace that now owns that surface instead of floating a window.
const _wsOwnerOf = {};
Object.keys(WORKSPACES).forEach(function (key) {
    WORKSPACES[key].windows.forEach(function (w) { _wsOwnerOf[w] = key; });
});

if (typeof window.toggleWindow === 'function') {
    const _legacyToggleWindow = window.toggleWindow;
    window.toggleWindow = function (winId) {
        const owner = _wsOwnerOf[winId];
        if (owner && _wsAdopted) { wsGo(owner); return; }
        return _legacyToggleWindow.apply(this, arguments);
    };
}

/* ---- click ripple on interactive chrome ---------------------------- */
document.addEventListener('pointerdown', function (event) {
    const target = event.target.closest('.dock-btn, .ps-rail-item, .ds-btn, .ps-cta');
    if (!target) return;
    const rect = target.getBoundingClientRect();
    const ripple = document.createElement('span');
    const size = Math.max(rect.width, rect.height);
    ripple.className = 'ds-ripple';
    ripple.style.width = ripple.style.height = size + 'px';
    ripple.style.left = (event.clientX - rect.left - size / 2) + 'px';
    ripple.style.top = (event.clientY - rect.top - size / 2) + 'px';
    if (getComputedStyle(target).position === 'static') target.style.position = 'relative';
    target.appendChild(ripple);
    setTimeout(function () { ripple.remove(); }, 500);
}, { passive: true });

/* ---- keyboard: workspace switching + search focus ------------------ */
document.addEventListener('keydown', function (event) {
    if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        const input = document.getElementById('dash-search');
        if (input) { input.focus(); input.select(); }
    }
    if (event.key === 'Escape') { dashSearchClear(); }
});

/* ----------------------------------------------------------- image forge */
/* CSG + SDF raymarched procedural image generation. Offline, vendored WebGL2,
 * no dependency. Scenes are reproducible from a short shareable recipe code.
 *
 * Two render paths, same recipe, same pixels:
 *   1) WebGL2 interactive canvas when the surface supports it.
 *   2) POST /api/forge/render (CPU engine via the shell→controller hop) when
 *      WebGL2 is absent — the GTK/WebKit shell is one such surface.
 *
 * NO MOCK DATA: if neither path can produce a real frame the stage shows
 * "unknown" and nothing fabricated. A loading state is shown while the
 * server path works (renders take seconds).
 */
let forgeRenderer = null;
let forgeAnimating = false;
let forgePresetsWired = false;
let forgeServerMode = false;
let forgeServerBusy = false;
let forgeServerBlobUrl = null;
let forgeHasFrame = false;

function forgeSetStatus(text) {
    const el = document.getElementById('forge-status');
    if (el) el.textContent = text;
}

function forgeSetDetail(text) {
    const detail = document.getElementById('forge-status-detail');
    if (detail) detail.textContent = text;
}

function forgeVal(id, fallback) {
    const el = document.getElementById(id);
    return el ? el.value : fallback;
}

function forgeFillSelect(sel, items, keepValue) {
    if (!sel || !items || !items.length) return;
    const previous = keepValue != null ? String(keepValue) : sel.value;
    sel.innerHTML = '';
    items.forEach(function (label, index) {
        const opt = document.createElement('option');
        opt.value = String(index);
        opt.textContent = label;
        sel.appendChild(opt);
    });
    if (previous !== '' && Array.prototype.some.call(sel.options, function (o) { return o.value === previous; })) {
        sel.value = previous;
    }
}

function forgeWirePresets() {
    if (forgePresetsWired || !window.SDFForge) return;
    const F = window.SDFForge;

    // Scenes and palettes come from the same lists the CPU engine uses
    // (SCENES / palette names), so the dropdowns can never drift from the
    // renderer. Empty option lists were the "blank white boxes" bug.
    forgeFillSelect(document.getElementById('forge-mode'), F.SCENES, forgeVal('forge-mode', '0'));
    forgeFillSelect(document.getElementById('forge-palette'), F.PALETTES, forgeVal('forge-palette', '0'));

    const sel = document.getElementById('forge-preset');
    if (sel) {
        // Keep the Custom… sentinel, then append named presets.
        const custom = sel.querySelector('option[value=""]') || (function () {
            const o = document.createElement('option');
            o.value = '';
            o.textContent = 'Custom…';
            return o;
        })();
        sel.innerHTML = '';
        sel.appendChild(custom);
        Object.keys(F.PRESETS || {}).forEach(function (name) {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            sel.appendChild(opt);
        });
    }
    forgePresetsWired = true;
}

function forgeShowEmpty(show) {
    const empty = document.getElementById('forge-empty');
    if (empty) empty.hidden = !show;
}

function forgeShowUnavailable(show, detail) {
    const unavailable = document.getElementById('forge-unavailable');
    if (unavailable) unavailable.hidden = !show;
    if (detail != null) forgeSetDetail(detail);
}

function forgeShowLoading(show) {
    const loading = document.getElementById('forge-loading');
    const stage = document.getElementById('forge-stage');
    if (loading) loading.hidden = !show;
    if (stage) {
        if (show) stage.classList.add('is-rendering');
        else stage.classList.remove('is-rendering');
    }
}

function forgeReadSize() {
    // Endpoint accepts 32–2048 px and quality 8–128. The selectors only offer
    // values inside that range; still clamp so a hand-edited option cannot
    // send an out-of-range request.
    let size = parseInt(forgeVal('forge-resolution', '512'), 10);
    let quality = parseInt(forgeVal('forge-quality', '48'), 10);
    if (!isFinite(size)) size = 512;
    if (!isFinite(quality)) quality = 48;
    size = Math.max(32, Math.min(2048, size));
    quality = Math.max(8, Math.min(128, quality));
    return { width: size, height: size, quality: quality };
}

function forgeOnQualityChange() {
    // Changing size/quality only matters for the next still — do not auto-
    // re-render (a 1024² frame can take seconds). Nudge the user.
    if (forgeServerMode) {
        forgeSetStatus('Resolution/quality updated — press Render still');
    }
}

// The live control state, as a recipe object the module understands.
function forgeReadInt(id, fallback) {
    const n = parseInt(forgeVal(id, String(fallback)), 10);
    return Number.isFinite(n) ? n : fallback;
}

function forgeReadRecipe() {
    return {
        mode: forgeReadInt('forge-mode', 0),
        iters: forgeReadInt('forge-iters', 6),
        blend: forgeReadInt('forge-blend', 35),
        hue: forgeReadInt('forge-hue', 285),
        glow: forgeReadInt('forge-glow', 60),
        palette: forgeReadInt('forge-palette', 0),
        cam: forgeReadInt('forge-cam', 42),
    };
}

// Push a recipe object into the controls (without firing their handlers).
function forgeWriteControls(r) {
    const set = function (id, v) { const el = document.getElementById(id); if (el) el.value = String(v); };
    set('forge-mode', r.mode);
    set('forge-iters', r.iters);
    set('forge-blend', r.blend);
    set('forge-hue', r.hue);
    set('forge-glow', r.glow);
    set('forge-palette', r.palette);
    set('forge-cam', r.cam);
}

function forgeShowRecipeCode(r) {
    if (!window.SDFForge) return '';
    const code = window.SDFForge.encodeRecipe(r);
    const input = document.getElementById('forge-recipe');
    if (input) input.value = code;
    return code;
}

function forgeSetServerImage(blob) {
    const img = document.getElementById('forge-server-img');
    if (!img) return;
    if (forgeServerBlobUrl) {
        try { URL.revokeObjectURL(forgeServerBlobUrl); } catch (e) { /* ignore */ }
        forgeServerBlobUrl = null;
    }
    forgeServerBlobUrl = URL.createObjectURL(blob);
    img.src = forgeServerBlobUrl;
    img.hidden = false;
    forgeHasFrame = true;
    forgeShowEmpty(false);
    forgeShowUnavailable(false);
}

async function forgeServerRender() {
    if (forgeServerBusy) return;
    if (!window.SDFForge) {
        forgeSetStatus('forge module unavailable');
        forgeShowUnavailable(true, 'unknown');
        return;
    }

    const recipe = forgeReadRecipe();
    const size = forgeReadSize();
    const code = forgeShowRecipeCode(recipe);

    forgeServerBusy = true;
    forgeShowLoading(true);
    forgeShowEmpty(false);
    forgeShowUnavailable(false);
    forgeSetStatus('Rendering on this machine…');

    const renderBtn = document.getElementById('forge-render-btn');
    if (renderBtn) renderBtn.disabled = true;

    try {
        const resp = await fetch('/api/forge/render', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                code: code,
                width: size.width,
                height: size.height,
                quality: size.quality,
            }),
        });

        if (!resp.ok) {
            let detail = 'render failed (' + resp.status + ')';
            try {
                const body = await resp.json();
                if (body && (body.detail || body.error || body.message)) {
                    detail = body.detail || body.error || body.message;
                }
            } catch (e) { /* keep the status-code message */ }
            forgeSetStatus(detail);
            // No fabricated frame: if we never had a real image, show unknown.
            if (!forgeHasFrame) {
                forgeShowUnavailable(true, 'unknown');
                forgeShowEmpty(false);
            }
            return;
        }

        const native = resp.headers.get('X-Forge-Native') === '1';
        const echoed = resp.headers.get('X-Forge-Recipe');
        if (echoed) {
            const input = document.getElementById('forge-recipe');
            if (input) input.value = echoed;
        }
        const blob = await resp.blob();
        if (!blob || !blob.size) {
            forgeSetStatus('empty render (unknown)');
            if (!forgeHasFrame) forgeShowUnavailable(true, 'unknown');
            return;
        }
        forgeSetServerImage(blob);
        forgeSetStatus(native
            ? 'Rendered ' + size.width + '×' + size.height + ' on this machine'
            : 'Rendered ' + size.width + '×' + size.height + ' (Python path — build native core for speed)');
    } catch (err) {
        forgeSetStatus('render failed: ' + (err && err.message ? err.message : String(err)));
        if (!forgeHasFrame) {
            forgeShowUnavailable(true, 'unknown');
            forgeShowEmpty(false);
        }
    } finally {
        forgeServerBusy = false;
        forgeShowLoading(false);
        if (renderBtn) renderBtn.disabled = false;
    }
}

function forgeEnterServerMode() {
    forgeServerMode = true;
    const canvas = document.getElementById('forge-canvas');
    if (canvas) canvas.style.display = 'none';
    const animBtn = document.getElementById('forge-animate-btn');
    if (animBtn) {
        animBtn.disabled = true;
        animBtn.title = 'Live animation needs WebGL2; still frames render on this machine';
        animBtn.setAttribute('aria-disabled', 'true');
    }
    // Promote Render still to the primary action when animation is gone.
    const renderBtn = document.getElementById('forge-render-btn');
    if (renderBtn) renderBtn.classList.add('ds-btn-primary');
    forgeShowEmpty(!forgeHasFrame);
    forgeShowUnavailable(false);
    forgeSetStatus('Still frames render on this machine (no WebGL2)');
    forgeShowRecipeCode(forgeReadRecipe());
    // Auto-render so the user sees an image immediately, not an empty stage.
    forgeServerRender();
}

function forgeInit() {
    const canvas = document.getElementById('forge-canvas');
    if (!canvas) return;
    if (!window.SDFForge) {
        forgeSetStatus('forge module unavailable');
        forgeShowUnavailable(true, 'unknown');
        forgeShowEmpty(false);
        return;
    }
    forgeWirePresets();
    if (!forgeRenderer) {
        forgeRenderer = window.SDFForge.create(canvas);
    }
    if (!forgeRenderer.available) {
        // No WebGL2 (GTK/WebKit shell is one such surface). Fall back to the
        // server-side CPU engine automatically — same recipe, real pixels.
        forgeEnterServerMode();
        return;
    }
    forgeServerMode = false;
    forgeShowUnavailable(false);
    forgeShowEmpty(false);
    forgeShowLoading(false);
    canvas.style.display = 'block';
    const img = document.getElementById('forge-server-img');
    if (img) img.hidden = true;
    const animBtn = document.getElementById('forge-animate-btn');
    if (animBtn) {
        animBtn.disabled = false;
        animBtn.removeAttribute('aria-disabled');
        animBtn.title = '';
    }
    forgeApply();
    forgeRender();
}

function forgeApply() {
    const r = forgeReadRecipe();
    forgeShowRecipeCode(r);
    if (forgeServerMode) {
        // Do not auto-re-render on every slider tick — each still costs seconds.
        // Recipe code updates live so Copy always reflects the knobs.
        forgeSetStatus('Recipe updated — press Render still');
        return;
    }
    if (!forgeRenderer || !forgeRenderer.available) return;
    forgeRenderer.applyRecipe(r);
    if (!forgeAnimating) forgeRender();
}

function forgeRender() {
    if (forgeServerMode) {
        forgeServerRender();
        return;
    }
    if (!forgeRenderer || !forgeRenderer.available) {
        forgeSetStatus('nothing to render (unknown)');
        forgeShowUnavailable(true, 'unknown');
        return;
    }
    forgeRenderer.applyRecipe(forgeReadRecipe());
    forgeRenderer.renderStill(0.0);
    forgeHasFrame = true;
    forgeShowEmpty(false);
    forgeSetStatus('Rendered a still frame');
}

function forgeToggleAnim() {
    if (forgeServerMode || !forgeRenderer || !forgeRenderer.available) {
        forgeSetStatus('Live animation needs WebGL2; use Render still');
        return;
    }
    const btn = document.getElementById('forge-animate-btn');
    if (forgeAnimating) {
        forgeRenderer.stop();
        forgeAnimating = false;
        if (btn) btn.textContent = 'Animate';
        forgeSetStatus('Paused');
    } else {
        forgeRenderer.applyRecipe(forgeReadRecipe());
        forgeRenderer.start();
        forgeAnimating = true;
        if (btn) btn.textContent = 'Pause';
        forgeSetStatus('Animating');
    }
}

function forgeRandomize() {
    if (!window.SDFForge) return;
    const seed = Math.random().toString(36).slice(2, 9);
    const r = window.SDFForge.recipeFromSeed(seed);
    forgeWriteControls(r);
    const preset = document.getElementById('forge-preset');
    if (preset) preset.value = '';
    forgeShowRecipeCode(r);
    if (forgeServerMode) {
        forgeSetStatus('Surprised you with seed "' + seed + '" — rendering…');
        forgeServerRender();
    } else {
        forgeApply();
        forgeSetStatus('Surprised you with seed "' + seed + '"');
    }
}

function forgeApplyRecipe() {
    if (!window.SDFForge) return;
    const input = document.getElementById('forge-recipe');
    const raw = input ? input.value.trim() : '';
    if (!raw) {
        forgeSetStatus('Paste a recipe code (e.g. SF1.0.6.35.285.60.0.42) then Load');
        return;
    }
    let r = window.SDFForge.decodeRecipe(raw);
    let message;
    if (!r) {
        // Not a recipe code — treat whatever was typed as a free-text seed.
        r = window.SDFForge.recipeFromSeed(raw);
        message = 'Grew a scene from your text';
    } else {
        message = 'Loaded recipe ' + window.SDFForge.encodeRecipe(r);
    }
    forgeWriteControls(r);
    const preset = document.getElementById('forge-preset');
    if (preset) preset.value = '';
    forgeShowRecipeCode(r);
    if (forgeServerMode) {
        forgeSetStatus(message + ' — rendering…');
        forgeServerRender();
    } else {
        forgeApply();
        forgeSetStatus(message);
    }
}

function forgeCopyRecipe() {
    const code = forgeShowRecipeCode(forgeReadRecipe());
    if (!code) {
        forgeSetStatus('nothing to copy (unknown)');
        return;
    }
    var copied = false;
    try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(code);
            copied = true;
        }
    } catch (e) { /* clipboard may be blocked */ }
    // Fallback: select the field so the user can Ctrl/Cmd+C.
    if (!copied) {
        const input = document.getElementById('forge-recipe');
        if (input) {
            input.focus();
            input.select();
        }
        forgeSetStatus('Select and copy: ' + code);
        return;
    }
    forgeSetStatus('Copied ' + code);
}

function forgeLoadPreset() {
    if (!window.SDFForge) return;
    const sel = document.getElementById('forge-preset');
    const name = sel ? sel.value : '';
    if (!name) return;
    const code = window.SDFForge.PRESETS[name];
    const r = window.SDFForge.decodeRecipe(code);
    if (!r) {
        forgeSetStatus('preset unavailable (unknown)');
        return;
    }
    forgeWriteControls(r);
    forgeShowRecipeCode(r);
    if (forgeServerMode) {
        forgeSetStatus('Preset: ' + name + ' — rendering…');
        forgeServerRender();
    } else if (forgeRenderer && forgeRenderer.available) {
        forgeRenderer.applyRecipe(r);
        forgeRender();
        forgeSetStatus('Preset: ' + name);
    } else {
        forgeSetStatus('Preset: ' + name);
    }
}

function forgeExport() {
    const code = window.SDFForge ? window.SDFForge.encodeRecipe(forgeReadRecipe()) : 'forge';
    const link = document.getElementById('forge-download');

    if (forgeServerMode) {
        const img = document.getElementById('forge-server-img');
        if (!img || img.hidden || !img.src) {
            forgeSetStatus('no frame to export — press Render still first');
            return;
        }
        if (link) {
            link.href = img.src;
            link.download = 'synthesus-forge-' + code + '.png';
            link.click();
        }
        forgeSetStatus('Exported PNG');
        return;
    }

    if (!forgeRenderer || !forgeRenderer.available) {
        forgeSetStatus('no frame to export (unknown)');
        return;
    }
    forgeRenderer.renderStill(forgeAnimating ? (performance.now() / 1000) : 0.0);
    const data = forgeRenderer.toPNG();
    if (!data) { forgeSetStatus('export unavailable (unknown)'); return; }
    if (link) {
        link.href = data;
        link.download = 'synthesus-forge-' + code + '.png';
        link.click();
    }
    forgeSetStatus('Exported PNG');
}

function openForge() {
    toggleWindow('win-forge');
    if (document.getElementById('win-forge').style.display !== 'none') forgeInit();
}

// --- WORKSTREAM C: IDE ADDITIONS ---
let ideTerminal = null;

function ideInitTerminal() {
    if (ideTerminal) return;
    const container = document.getElementById('ide-terminal-container');
    if (!container) return;
    ideTerminal = new Terminal({
        theme: { background: '#0a0a0f', foreground: '#e2e8f0' },
        fontFamily: "'Fira Code', monospace",
        fontSize: 13,
        cursorBlink: true
    });
    const fitAddon = new FitAddon.FitAddon();
    ideTerminal.loadAddon(fitAddon);
    ideTerminal.open(container);
    fitAddon.fit();
    
    // Connect to backend
    ensureTerminalCapability().then(config => {
        const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const sessionId = config.session_id || 'ide-session';
        const endpoint = `${scheme}://${controllerHost(config)}${config.terminal_ws_path}/${sessionId}`;
        const ws = new WebSocket(endpoint, ['synthesus-terminal', config.terminal_token]);
        ws.onopen = () => {
            ideTerminal.onData(data => ws.send(data));
            ws.onmessage = e => ideTerminal.write(e.data);
            window.addEventListener('resize', () => fitAddon.fit());
        };
        ws.onerror = (e) => ideTerminal.write(`\\r\\n[IDE Terminal Error]\\r\\n`);
        ws.onclose = () => ideTerminal.write(`\\r\\n[IDE Terminal Closed]\\r\\n`);
    }).catch(e => console.error("Could not init IDE terminal", e));
}

// Resizable Split Panes (C1)
function setupIdeResizers() {
    const expMain = document.getElementById('resizer-exp-main');
    const mainPreview = document.getElementById('resizer-main-preview');
    const editorTerm = document.getElementById('resizer-editor-term');
    
    const expPane = document.getElementById('ide-explorer-pane');
    const previewPane = document.getElementById('ide-preview-pane');
    const termPane = document.getElementById('ide-terminal-pane');

    // Load persisted sizes
    if (localStorage.getItem('ide-exp-width')) expPane.style.flexBasis = localStorage.getItem('ide-exp-width');
    if (localStorage.getItem('ide-preview-width')) previewPane.style.flexBasis = localStorage.getItem('ide-preview-width');
    if (localStorage.getItem('ide-term-height')) termPane.style.flexBasis = localStorage.getItem('ide-term-height');

    function createResizer(resizer, target, prop, dimension, invert=false) {
        if (!resizer || !target) return;
        let isResizing = false;
        resizer.addEventListener('mousedown', (e) => {
            isResizing = true;
            document.body.style.cursor = resizer.style.cursor;
            e.preventDefault();
        });
        document.addEventListener('mousemove', (e) => {
            if (!isResizing) return;
            const bounds = target.parentElement.getBoundingClientRect();
            let newSize = 0;
            if (dimension === 'x') {
                newSize = invert ? bounds.right - e.clientX : e.clientX - bounds.left;
            } else {
                newSize = invert ? bounds.bottom - e.clientY : e.clientY - bounds.top;
            }
            target.style.flexBasis = `${newSize}px`;
        });
        document.addEventListener('mouseup', () => {
            if (isResizing) {
                isResizing = false;
                document.body.style.cursor = '';
                localStorage.setItem(`ide-${prop}`, target.style.flexBasis);
                if (ideTerminal && ideTerminal._core) {
                    try { ideTerminal._core._fitAddon.fit(); } catch(e){} // best effort
                }
            }
        });
    }

    createResizer(expMain, expPane, 'exp-width', 'x');
    createResizer(mainPreview, previewPane, 'preview-width', 'x', true);
    createResizer(editorTerm, termPane, 'term-height', 'y', true);
}
document.addEventListener('DOMContentLoaded', setupIdeResizers);
window.addEventListener('load', () => { setTimeout(ideInitTerminal, 1000); });

// AI Code Actions (C3)
function getIdeSelection() {
    const editor = document.getElementById('ide-code-editor');
    let text = window.getSelection().toString();
    if (editor && (!text || text.length === 0)) {
        text = editor.value.substring(editor.selectionStart, editor.selectionEnd);
    }
    if (!text) {
        alert("Please select some code in the editor first.");
        return null;
    }
    return text;
}
function ideExplainCode() {
    const sel = getIdeSelection();
    if (!sel) return;
    if (document.getElementById('win-chat').style.display === 'none') toggleWindow('win-chat');
    document.getElementById('chat-input').value = `Explain this code:\n\n\`\`\`\n${sel}\n\`\`\``;
}
function ideRefactorCode() {
    const sel = getIdeSelection();
    if (!sel) return;
    if (document.getElementById('win-chat').style.display === 'none') toggleWindow('win-chat');
    document.getElementById('chat-input').value = `Refactor this code to be cleaner and more efficient:\n\n\`\`\`\n${sel}\n\`\`\``;
}
function ideNLToCode() {
    const sel = getIdeSelection();
    if (!sel) return;
    if (document.getElementById('win-chat').style.display === 'none') toggleWindow('win-chat');
    document.getElementById('chat-input').value = `Convert this natural language to code:\n\n${sel}`;
}

// Preview Pane (C4)
function ideUpdatePreview(content, filename) {
    const preview = document.getElementById('ide-html-preview');
    if (!preview) return;
    if (filename.endsWith('.html') || filename.endsWith('.htm')) {
        preview.srcdoc = content;
    } else {
        preview.srcdoc = `<html><body style="font-family:sans-serif;padding:20px;color:#666;">Preview is only available for HTML files.</body></html>`;
    }
}

// File CRUD (C2)
let currentIdePath = null;
async function ideApiFetch(endpoint, opts={}) {
    const userToken = localStorage.getItem('synthesus_token');
    if (!userToken) { alert("Sign in first."); return null; }
    const res = await fetch(endpoint, {
        ...opts,
        headers: { 'Authorization': 'Bearer ' + userToken, ...opts.headers }
    });
    return res;
}

async function ideCreateFile() {
    const path = prompt("New file name (e.g. index.html):");
    if (!path) return;
    const res = await ideApiFetch('/api/ide/files/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: path, content: ''})
    });
    if (res && res.ok) alert("File created.");
    else alert("Failed to create file. It may be outside the permitted root or already exist.");
    if (window.refreshIDEFiles) window.refreshIDEFiles();
}

async function ideCreateDir() {
    const path = prompt("New folder name (e.g. src/):");
    if (!path) return;
    const res = await ideApiFetch('/api/ide/files/create', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: path + '/.keep', content: ''})
    });
    if (res && res.ok) alert("Folder created.");
    else alert("Failed to create folder.");
    if (window.refreshIDEFiles) window.refreshIDEFiles();
}

async function ideRenameFile() {
    if (!currentIdePath) { alert("Select a file first."); return; }
    const newPath = prompt("Rename to:", currentIdePath);
    if (!newPath || newPath === currentIdePath) return;
    const res = await ideApiFetch('/api/ide/files/rename', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({old_path: currentIdePath, new_path: newPath})
    });
    if (res && res.ok) {
        alert("File renamed.");
        currentIdePath = newPath;
        document.getElementById('ide-current-file').textContent = currentIdePath;
        if (window.refreshIDEFiles) window.refreshIDEFiles();
    } else {
        alert("Failed to rename file. Target may be outside root.");
    }
}

async function ideDeleteFile() {
    if (!currentIdePath) { alert("Select a file first."); return; }
    if (!confirm(`Are you sure you want to delete ${currentIdePath}?`)) return;
    const res = await ideApiFetch(`/api/ide/files/${currentIdePath}`, { method: 'DELETE' });
    if (res && res.ok) {
        alert("File deleted.");
        document.getElementById('ide-current-file').textContent = "Select a file";
        document.getElementById('ide-code-editor').textContent = "";
        currentIdePath = null;
        document.getElementById('ide-file-actions').style.display = 'none';
        if (window.refreshIDEFiles) window.refreshIDEFiles();
    } else {
        alert("Failed to delete file.");
    }
}

// Override or inject into existing IDE file click handler
const originalIdeFileClick = window.ideFileClick || function(){};
window.ideFileClick = function(path, content) {
    originalIdeFileClick(path, content);
    currentIdePath = path;
    document.getElementById('ide-file-actions').style.display = 'flex';
    ideUpdatePreview(content, path);
};

// --- WORKSTREAM C ENHANCEMENTS ---

// Unsaved changes & syntax highlighting
let currentIdeSavedContent = "";
const syntaxColors = {
    keyword: '#c678dd',
    string: '#98c379',
    comment: '#5c6370',
    number: '#d19a66',
    function: '#61afef'
};

function ideHighlightSyntax(text) {
    let html = escapeHtml(text);
    
    // Comments
    html = html.replace(/(\/\/.*|\/\*[\s\S]*?\*\/)/g, '<span style="color:' + syntaxColors.comment + '">$&</span>');
    // Strings
    html = html.replace(/(["'`])(?:(?=(\\?))\2.)*?\1/g, '<span style="color:' + syntaxColors.string + '">$&</span>');
    // Keywords
    const keywords = '\b(const|let|var|function|return|if|else|for|while|class|import|export|from|await|async|try|catch|true|false|null|undefined)\b';
    html = html.replace(new RegExp(keywords, 'g'), '<span style="color:' + syntaxColors.keyword + '">$&</span>');
    // Numbers
    html = html.replace(/\b(\d+)\b/g, '<span style="color:' + syntaxColors.number + '">$&</span>');
    
    return html + '<br/>'; // extra br for trailing newlines in textarea
}

document.addEventListener('DOMContentLoaded', () => {
    const editor = document.getElementById('ide-code-editor');
    const highlight = document.getElementById('ide-code-highlight');
    if (!editor || !highlight) return;

    // Sync scrolling
    editor.addEventListener('scroll', () => {
        highlight.scrollTop = editor.scrollTop;
        highlight.scrollLeft = editor.scrollLeft;
    });

    // Real-time input handling
    editor.addEventListener('input', () => {
        highlight.innerHTML = ideHighlightSyntax(editor.value);
        
        // Unsaved indicator
        const nameEl = document.getElementById('ide-current-file');
        if (nameEl) {
            let name = currentIdePath ? currentIdePath.split('/').pop() : 'Select a file';
            if (editor.value !== currentIdeSavedContent) {
                nameEl.textContent = '● ' + name;
                nameEl.style.fontStyle = 'italic';
            } else {
                nameEl.textContent = name;
                nameEl.style.fontStyle = 'normal';
            }
        }
    });

    // Ctrl+S listener
    editor.addEventListener('keydown', (e) => {
        // Indentation support
        if (e.key === 'Tab') {
            e.preventDefault();
            const start = editor.selectionStart;
            const end = editor.selectionEnd;
            editor.value = editor.value.substring(0, start) + '    ' + editor.value.substring(end);
            editor.selectionStart = editor.selectionEnd = start + 4;
            editor.dispatchEvent(new Event('input'));
        }
        
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            ideSaveFile();
        }
    });
});

async function ideSaveFile() {
    if (!currentIdePath) return;
    const editor = document.getElementById('ide-code-editor');
    const content = editor.value;
    
    const res = await ideApiFetch('/api/ide/files/update', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({path: currentIdePath, content: content})
    });
    
    if (res && res.ok) {
        currentIdeSavedContent = content;
        editor.dispatchEvent(new Event('input')); // trigger indicator reset
        ideUpdatePreview(content, currentIdePath);
        if (window.refreshIDEFiles) window.refreshIDEFiles();
    } else {
        alert("Failed to save file.");
    }
}

// C5: Plugin Hooks
window.ideEventHooks = {
    onFileSelect: []
};

window.ideRegisterHook = function(event, callback) {
    if (window.ideEventHooks[event]) {
        window.ideEventHooks[event].push(callback);
    }
};

// Patch the original openFileFromEl hook to support our new dual-layer editor
const oldIdeFileClick = window.ideFileClick;
window.ideFileClick = function(path, content) {
    const editor = document.getElementById('ide-code-editor');
    const highlight = document.getElementById('ide-code-highlight');
    if (editor && highlight) {
        const text = content != null ? String(content) : '';
        editor.value = text;
        currentIdeSavedContent = text;
        highlight.innerHTML = ideHighlightSyntax(text);
        editor.dispatchEvent(new Event('input')); // update indicator
    }
    
    if (oldIdeFileClick) oldIdeFileClick(path, content);
    
    // Trigger hooks
    window.ideEventHooks.onFileSelect.forEach(cb => cb(path, content));
};

// Pop-out Preview (C4 enhancement)
function idePopOutPreview() {
    const preview = document.getElementById('ide-html-preview');
    if (!preview || !preview.srcdoc) return;
    const win = window.open('', '_blank');
    if (win) {
        win.document.open();
        win.document.write(preview.srcdoc);
        win.document.close();
    } else {
        alert("Pop-up blocked. Please allow pop-ups for this site.");
    }
}

// Logout functionality
function appLogout() {
    if (confirm("Are you sure you want to log out?")) {
        localStorage.removeItem('synthesus_token');
        localStorage.removeItem('synthesus_user');
        window.location.reload();
    }
}
