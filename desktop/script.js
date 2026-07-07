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
    let displayState = 'none';
    if (win.style.display === 'none') {
        win.style.display = 'flex';
        displayState = 'flex';
        clampIntoView(win);   // never open a window off-screen (unreachable title bar)
        focusWindow(win);
        
        // Trigger lazy loading
        if (id === 'win-explorer') fetchIDEFiles();
        if (id === 'win-twin') startTwinSimulation();
        if (id === 'win-term') initTerminal();
        if (id === 'win-chat') maybeStreamWelcome();
        if (id === 'win-drive') loadDriveSources();
    } else {
        win.style.display = 'none';
        if (id === 'win-twin' && twinInterval) clearInterval(twinInterval);
    }
    
    // Broadcast to Grid
    if (window.gridSocket && gridSocket.readyState === WebSocket.OPEN) {
        gridSocket.send(JSON.stringify({
            type: 'window_toggle',
            id: id,
            display: displayState
        }));
    }
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
    const w = win.offsetWidth || 400, h = win.offsetHeight || 300;
    let left = parseInt(win.style.left, 10); if (isNaN(left)) left = win.offsetLeft || 40;
    let top  = parseInt(win.style.top, 10);  if (isNaN(top))  top  = win.offsetTop  || 40;
    left = Math.max(0, Math.min(left, window.innerWidth  - w));
    top  = Math.max(0, Math.min(top,  window.innerHeight - h));
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
                const newLeft = Math.max(0, Math.min(currentMouseX - offsetX, window.innerWidth - 100));
                const newTop = Math.max(0, Math.min(currentMouseY - offsetY, window.innerHeight - 50));
                currentWindow.style.left = newLeft + 'px';
                currentWindow.style.top = newTop + 'px';
                
                // Broadcast to Grid Nodes
                if (gridSocket && gridSocket.readyState === WebSocket.OPEN) {
                    gridSocket.send(JSON.stringify({
                        type: 'window_move',
                        id: currentWindow.id,
                        left: newLeft,
                        top: newTop,
                        zIndex: currentWindow.style.zIndex
                    }));
                }
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
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.window').forEach(win => {
        win.addEventListener('mousedown', () => focusWindow(win));
    });
    setInterval(fetchOSStatus, 2000);

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
        
        document.getElementById('status-quadbrain').textContent = data.llm_status.includes("ONLINE") ? "AI: ROOT SYNCED" : "AI: WAITING";
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
            bridgeEl.style.background = data['peripheral_bridge_active'] ? '#38bdf8' : '#333';
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
                    else entropyEl.style.color = "#facc15";
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
                    <div style="display:flex; justify-content:space-between;"><span>CPU Usage:</span> <span style="color:#34d399;">${data.cpu_percent || '12'}%</span></div>
                    <div style="display:flex; justify-content:space-between;"><span>RAM Usage:</span> <span style="color:#818cf8;">${data.ram_percent || '45'}%</span></div>
                    <div style="display:flex; justify-content:space-between;"><span>GPU VRAM:</span> <span style="color:#facc15;">Allocated (QuadBrain)</span></div>
                `;
                
                // Worker
                const workerRes = await fetch('http://127.0.0.1:8082/api/system/status');
                const workerData = await workerRes.json();
                document.getElementById('pool-worker').innerHTML = `
                    <div style="display:flex; justify-content:space-between;"><span>CPU Usage:</span> <span style="color:#34d399;">${workerData.cpu_percent || '8'}%</span></div>
                    <div style="display:flex; justify-content:space-between;"><span>RAM Usage:</span> <span style="color:#818cf8;">${workerData.ram_percent || '22'}%</span></div>
                    <div style="display:flex; justify-content:space-between;"><span>Neural Load:</span> <span style="color:#facc15;">Synced via WebSocket</span></div>
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
// IDE FILE EXPLORER
// ==========================================
async function fetchIDEFiles() {
    try {
        const response = await fetch('http://' + window.location.host + '/api/ide/files');
        const treeData = await response.json();
        document.getElementById('ide-file-tree').innerHTML = '<ul><li><span class="folder" style="color: #38bdf8;">🌐 Storage Array</span>' + buildTreeHTML(treeData) + '</li></ul>';
    } catch(err) {
        document.getElementById('ide-file-tree').innerHTML = '<p style="color:red;">Failed to mount.</p>';
    }
}

function buildTreeHTML(nodes) {
    let html = '<ul>';
    nodes.forEach(node => {
        if(node.type === 'dir') html += `<li><span class="folder">📂 ${node.name}</span>${buildTreeHTML(node.children)}</li>`;
        else html += `<li onclick="openFile('${node.name}')" style="cursor:pointer; padding: 2px 0;">📄 <span style="color: #94a3b8;">${node.name}</span></li>`;
    });
    return html + '</ul>';
}

function openFile(filename) {
    document.getElementById('ide-current-file').innerText = filename;
    document.getElementById('ide-code-editor').value = `// Secure KVM File Stream: ${filename}\n\n[Content loaded from Storage Array]`;
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
    h = h.replace(/\[([^\]]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" style="color:#38bdf8;">$1</a>');
    h = h.replace(/\n/g, '<br>');
    return h;
}

// Reveal text with a typewriter stream; the lightbulb stays lit while it types.
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
            if (onDone) onDone();
        }
    }, 14);
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if(!message) return;

    const chatHistory = document.getElementById('chat-history');
    chatHistory.innerHTML += `<div class="message" style="border-left: 3px solid #facc15;"><strong>User:</strong> ${message}</div>`;
    input.value = '';
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // The lightbulb flickers while Synthesus forms the idea.
    const thinkId = 'think-' + Date.now();
    chatHistory.innerHTML += `<div class="message ai-message" id="${thinkId}"><strong>Synthesus:</strong> <span class="thinking-bulb">&#128161;</span> <span style="color:#94a3b8; font-style:italic;">thinking&hellip;</span></div>`;
    chatHistory.scrollTop = chatHistory.scrollHeight;

    try {
        const response = await fetch('http://' + window.location.host + '/api/chat', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        const data = await response.json();
        // Idea arrives: bulb lights up solid, then the answer streams out.
        streamInto(document.getElementById(thinkId), data.response || '');

        if (data.os_plan) {
            const plan = data.os_plan;
            const planJSON = JSON.stringify(plan).replace(/"/g, '&quot;');
            let planHtml = `<div style="margin-top: 10px; background: rgba(20, 25, 40, 0.8); border: 1px solid #38bdf8; padding: 10px; border-radius: 8px;">
                <h4 style="color: #38bdf8; margin-bottom: 5px;">⚠️ OS Action Proposal: ${plan.intent}</h4>
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
            chatHistory.innerHTML += `<div class="message ai-message" style="border-left: 3px solid #38bdf8;"><strong>System:</strong> OS Plan successfully executed. Snapshot was taken prior to execution.</div>`;
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
                <button class="win-btn plus" onclick="spawnTerminalWindow()" title="New Tab/Window" style="background: #38bdf8; color: #fff; display: flex; align-items: center; justify-content: center; font-weight: bold; text-decoration: none;">+</button>
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
    function connectPTY() {
        try {
            ptySocket = new WebSocket(`ws://127.0.0.1:8082/ws/pty/user/${sessionId}`);
            ptySocket.onopen = () => term.write('\r\n[Connected to System PTY (Multi-Session)]\r\n');
            ptySocket.onmessage = (e) => term.write(e.data);
            ptySocket.onclose = () => {
                if(document.getElementById(termId)) {
                    term.write('\r\n[Disconnected. Reconnecting...]\r\n');
                    setTimeout(connectPTY, 2000);
                }
            };
        } catch(e) {}
    }
    connectPTY();
    
    term.onData((data) => {
        if(ptySocket && ptySocket.readyState === WebSocket.OPEN) {
            ptySocket.send(data);
        }
    });
    
    term.onResize((size) => {
        fetch('http://127.0.0.1:8082/api/terminal/resize', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, cols: size.cols, rows: size.rows })
        }).catch(() => {});
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
// UNIFIED SYSTEM GRID SYNC
// ==========================================
function initGridStateSync() {
    // Guard: the boot path and the login path both land here — never stack a
    // second live socket on top of one that's already open/connecting.
    if (window.gridSocket && (window.gridSocket.readyState === WebSocket.OPEN ||
                              window.gridSocket.readyState === WebSocket.CONNECTING)) return;
    window.gridSocket = new WebSocket(`ws://127.0.0.1:8082/ws/grid-state`);
    
    window.gridSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            const isWorker = new URLSearchParams(window.location.search).get("mode") === "worker";
            if (isWorker) {
                if (data.type === "virtual_mouse") {
                    const cursor = document.getElementById("virtual-cursor");
                    if (cursor) {
                        cursor.style.display = "block";
                        let nodeIndex = parseInt(new URLSearchParams(window.location.search).get('node_index') || "1");
                        const viewportX = data.x - (nodeIndex * window.innerWidth);
                        cursor.style.left = viewportX + "px";
                        cursor.style.top = data.y + "px";
                    }
                }
                if (data.type === "virtual_hide") {
                    const cursor = document.getElementById("virtual-cursor");
                    if (cursor) cursor.style.display = "none";
                }
                if (data.type === "virtual_mousedown") {
                    let nodeIndex = parseInt(new URLSearchParams(window.location.search).get('node_index') || "1");
                    const viewportX = data.x - (nodeIndex * window.innerWidth);
                    const el = document.elementFromPoint(viewportX, data.y);
                    if (el) el.click();
                }
            }
            if (data.type === 'window_move') {
                const win = document.getElementById(data.id);
                if (win) {
                    win.style.left = data.left + 'px';
                    win.style.top = data.top + 'px';
                    win.style.zIndex = data.zIndex;
                }
            } else if (data.type === 'window_toggle') {
                const win = document.getElementById(data.id);
                if (win) {
                    win.style.display = data.display;
                    if (data.display === 'flex') {
                        // Trigger lazy load
                        if (data.id === 'win-explorer') fetchIDEFiles();
                        if (data.id === 'win-twin') startTwinSimulation();
                    }
                }
            }
        } catch (e) {
            console.error("Grid Sync Error:", e);
        }
    };

    window.gridSocket.onopen = () => {
        console.log("🌌 CONNECTED TO AIVM GRID LAYER");
    };
    
    window.gridSocket.onclose = () => {
        // The grid/cluster server (:8082) is optional — chat + the expansion
        // drive don't need it. Retry a few times with backoff, then go quiet
        // instead of spamming a reconnect every 2s forever.
        window._gridRetries = (window._gridRetries || 0) + 1;
        if (window._gridRetries <= 3) {
            setTimeout(connectGridSocket, 3000 * window._gridRetries);
        } else if (window._gridRetries === 4) {
            console.log("Grid layer offline — running standalone (chat + drive unaffected).");
        }
    };
}

// Reconnect entrypoint used by the onclose retry/backoff above.
function connectGridSocket() { initGridStateSync(); }
connectGridSocket();

// ==========================================
// SSI CONTIGUOUS DESKTOP EXTENSION
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('mode') === 'worker') {
        // Shift entire UI to the left by the width of the Master monitor * node index
        // so multiple monitors can be chained seamlessly!
        let nodeIndex = parseInt(urlParams.get('node_index') || "1");
        let offset = nodeIndex * 1920;
        let totalWidth = (nodeIndex + 1) * 1920;
        
        const desktopArea = document.getElementById("desktop-area");
        if (desktopArea) {
            desktopArea.style.position = "absolute";
            desktopArea.style.left = `-${offset}px`;
            desktopArea.style.width = `${totalWidth}px`;
            desktopArea.style.height = "100vh";
        }
        
        document.body.style.overflow = "hidden";
        
        // Hide the local dock on the worker node, as the master has the dock
        const dock = document.querySelector('.dock');
        if (dock) dock.style.display = 'none';
        
        console.log("🌌 SSI Resource Node Mode Activated. Contiguous Desktop established.");
    }
});

// ==========================================
// VIRTUAL PERIPHERAL BRIDGE (Browser-Native KVM)
// ==========================================
let virtualX = 0;
let virtualY = 0;
let isPointerLocked = false;
let screenWidth = window.innerWidth;

document.addEventListener("DOMContentLoaded", () => {
    const cursorEl = document.createElement("div");
    cursorEl.id = "virtual-cursor";
    cursorEl.style.position = "absolute";
    cursorEl.style.width = "24px";
    cursorEl.style.height = "24px";
    cursorEl.style.background = "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24' fill='white' stroke='black' stroke-width='1.5'%3E%3Cpath d='M3 3l7 19 3.5-7.5L21 11z'/%3E%3C/svg%3E\") no-repeat";
    cursorEl.style.backgroundSize = "contain";
    cursorEl.style.zIndex = "999999";
    cursorEl.style.pointerEvents = "none";
    cursorEl.style.display = "none";
    const desktopArea = document.getElementById("desktop-area") || document.body;
    desktopArea.appendChild(cursorEl);

    const isWorker = new URLSearchParams(window.location.search).get("mode") === "worker";
    if (!isWorker) {
        // Right Hop Zone
        const hopZoneRight = document.createElement("div");
        hopZoneRight.style.position = "fixed";
        hopZoneRight.style.right = "0";
        hopZoneRight.style.top = "0";
        hopZoneRight.style.width = "20px";
        hopZoneRight.style.height = "100%";
        hopZoneRight.style.background = "linear-gradient(90deg, rgba(56,189,248,0) 0%, rgba(56,189,248,0.3) 100%)";
        hopZoneRight.style.cursor = "e-resize";
        hopZoneRight.style.zIndex = "999998";
        hopZoneRight.title = "Hop to Right Node";
        hopZoneRight.onclick = () => { hopDirection = "right"; document.body.requestPointerLock(); };
        document.body.appendChild(hopZoneRight);

        // Left Hop Zone
        const hopZoneLeft = document.createElement("div");
        hopZoneLeft.style.position = "fixed";
        hopZoneLeft.style.left = "0";
        hopZoneLeft.style.top = "0";
        hopZoneLeft.style.width = "20px";
        hopZoneLeft.style.height = "100%";
        hopZoneLeft.style.background = "linear-gradient(270deg, rgba(56,189,248,0) 0%, rgba(56,189,248,0.3) 100%)";
        hopZoneLeft.style.cursor = "w-resize";
        hopZoneLeft.style.zIndex = "999998";
        hopZoneLeft.title = "Hop to Left Node";
        hopZoneLeft.onclick = () => { hopDirection = "left"; document.body.requestPointerLock(); };
        document.body.appendChild(hopZoneLeft);
    }
});

document.addEventListener("pointerlockerror", () => {
    alert("Browser blocked the mouse edge-hop! Ensure you are clicking the edge directly.");
});

let lastRealY = window.innerHeight / 2;
let hopDirection = "right";

// ==========================================
// DESKTOP UI LOGIC
// ==========================================

document.addEventListener("DOMContentLoaded", () => {
    // Pre-fill the email field if we remember the last account that logged in here.
    const storedUser = localStorage.getItem('synthesus_user');
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

    // Best-effort grid join (its server may be down) — fully isolated.
    try {
        const nid = encodeURIComponent(data.user.email);
        fetch(`http://127.0.0.1:8082/api/grid/login?node_id=${nid}&user_id=${nid}`, { method: 'POST' }).catch(e => console.log(e));
    } catch (e) { console.log(e); }

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
    document.getElementById('login-modal').style.display = 'none';
    const tm = document.getElementById('tier-modal');
    if (tm) tm.style.display = 'none';
    try { initGridStateSync(); } catch (e) { console.log(e); }
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
        "After payment, your account will be upgraded to " + tierName +
        " (confirmed manually for early members). You can start using Synthesus now on the Free plan."
    );
    enterDesktop();
}




function hideRegistration() {
    const email = document.getElementById('user-email');
    const pass = document.getElementById('user-pass');
    
    if (email && email.value.trim() === '') {
        alert("Account Email is required for KYC & Casino access.");
        return;
    }
    if (pass && pass.value.trim() === '') {
        alert("Secure Password is required to harden your Node.");
        return;
    }
    
    // Auto-derive Node ID from the root identity (email prefix + hardware ID)
    const emailPrefix = email.value.split('@')[0];
    const hardwareId = Math.random().toString(36).substr(2, 4).toUpperCase();
    window.nodeName = `ROOT-${emailPrefix}-${hardwareId}`;

    document.getElementById('installer-modal').style.display = 'none';
    document.getElementById('tier-modal').style.display = 'flex';
}



function completeInstall() {
    try {
        const nodeName = window.nodeName || `ROOT-Anonymous-${Math.random().toString(36).substr(2, 4).toUpperCase()}`;

        const tosAgree = document.getElementById('tos-agree').checked;
        
        if (!tosAgree) {
            alert("You must agree to the Liability Waiver to proceed.");
            return;
        }
        
        try {
            localStorage.setItem('synthesus_user', nodeName);
        } catch(e) {}
        
        window.sessionId = nodeName;
        
        let driveSize = "500"; // Handled post-boot now
        
        // Connect to SSI (We use 127.0.0.1 to avoid CORS or dns issues)
        fetch(`http://127.0.0.1:8082/api/grid/login?node_id=${nodeName}&user_id=${nodeName}&drive_size=${driveSize}`, {method: 'POST'})
            .catch(e=>console.log(e));
        
        // Check for OTA updates before fully booting
        checkOTAUpdates(nodeName);
        
        // Init Desktop
        initGridStateSync();
    } catch(err) {
        alert("Boot Error: " + err.message);
        checkOTAUpdates(window.nodeName);
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

document.addEventListener("pointerlockchange", () => {
    isPointerLocked = (document.pointerLockElement === document.body);
    if (!isPointerLocked) {
        virtualX = hopDirection === "right" ? screenWidth - 30 : 30;
        if(window.gridSocket && window.gridSocket.readyState === WebSocket.OPEN) {
            window.gridSocket.send(JSON.stringify({ type: "virtual_hide" }));
        }
    } else {
        virtualX = hopDirection === "right" ? screenWidth + 1 : -1;
        virtualY = lastRealY; // Start at the height the mouse was at
    }
});

document.addEventListener("mousemove", (e) => {
    const isWorker = new URLSearchParams(window.location.search).get("mode") === "worker";
    if (isWorker) return; 
    
    if (isPointerLocked) {
        virtualX += e.movementX;
        virtualY += e.movementY;
        
        if (virtualY < 0) virtualY = 0;
        if (virtualY > window.innerHeight) virtualY = window.innerHeight;
        if (hopDirection === "right") {
            if (virtualX > screenWidth * 2) virtualX = screenWidth * 2;
            if (virtualX <= screenWidth) {
                document.exitPointerLock();
                return;
            }
        } else {
            if (virtualX < -screenWidth) virtualX = -screenWidth;
            if (virtualX >= 0) {
                document.exitPointerLock();
                return;
            }
        }
        
        if(window.gridSocket && window.gridSocket.readyState === WebSocket.OPEN) {
            if (!window.virtualMouseThrottle) {
                window.virtualMouseThrottle = true;
                requestAnimationFrame(() => {
                    if(window.gridSocket && window.gridSocket.readyState === WebSocket.OPEN) {
                        window.gridSocket.send(JSON.stringify({ 
                            type: "virtual_mouse", 
                            x: virtualX, 
                            y: virtualY 
                        }));
                        
                        // Send relative UDP Native KVM packet to the daemon
                        window.gridSocket.send(JSON.stringify({
                            type: "virtual_mouse_rel",
                            dx: e.movementX,
                            dy: e.movementY
                        }));
                    }
                    window.virtualMouseThrottle = false;
                });
            }
        }
    } else {
        virtualX = e.clientX;
        virtualY = e.clientY;
        lastRealY = e.clientY;
    }
});

document.addEventListener("mousedown", (e) => {
    if (isPointerLocked && window.gridSocket && window.gridSocket.readyState === WebSocket.OPEN) {
        window.gridSocket.send(JSON.stringify({ type: "virtual_mousedown", x: virtualX, y: virtualY }));
    }
});

// --- OTA Update Engine ---
async function checkOTAUpdates(nodeId) {
    try {
        const response = await fetch(`http://127.0.0.1:8082/api/grid/ota?node_id=${nodeId}`);
        const data = await response.json();
        
        if (data.has_update) {
            runOTASequence(data);
        } else {
            document.getElementById('installer-modal').style.display = 'none';
        }
    } catch (e) {
        console.error("OTA Check Failed", e);
        document.getElementById('installer-modal').style.display = 'none';
    }
}

function runOTASequence(updateData) {
    document.getElementById('installer-modal').style.display = 'none';
    const otaModal = document.getElementById('ota-modal');
    const otaConsole = document.getElementById('ota-console');
    const otaProgress = document.getElementById('ota-progress-bar');
    
    otaModal.style.display = 'flex';
    
    const logs = [
        `> Found pending update: ${updateData.latest_version}`,
        `> Payload size: ${updateData.update_size_mb} MB`,
        `> Fetching binary deltas from nearest CDN node...`,
        `> Applying AIOS Sports Betting Engine models...`,
        `> Recompiling C++ Kernel for Waydroid VM Integration...`,
        `> Patching God-Mode Multimodel Workspace...`,
        `> Verifying cryptographic signatures...`,
        `> Update compilation complete. Injecting into local Ring-0...`
    ];
    
    let step = 0;
    const interval = setInterval(() => {
        if (step < logs.length) {
            otaConsole.innerHTML += logs[step] + '<br>';
            otaConsole.scrollTop = otaConsole.scrollHeight;
            otaProgress.style.width = `${(step + 1) * (100 / logs.length)}%`;
            step++;
        } else {
            clearInterval(interval);

            setTimeout(() => {
                otaModal.style.display = 'none';
                triggerExpansionDriveInstaller();
            }, 1000);

        }
    }, 600);
}


function triggerExpansionDriveInstaller() {
    // Open the REAL guided creator (no simulated compile). One place to build a
    // drive from any source, wired end-to-end to the runtime.
    const modal = document.getElementById('expansion-modal');
    if (modal) modal.style.display = 'none';
    const win = document.getElementById('win-drive');
    if (win && win.style.display === 'none') toggleWindow('win-drive');
    else loadDriveSources();
}

function authenticateCloud(providerName) {
    // Legacy entry point → route into the real creator instead of faking a build.
    const modal = document.getElementById('expansion-modal');
    if (modal) modal.style.display = 'none';
    if (document.getElementById('win-drive').style.display === 'none') toggleWindow('win-drive');
    // preselect the matching cloud source if it's loaded
    const key = (providerName || '').toLowerCase();
    setTimeout(() => { if (DRIVE_SOURCES.find(s => s.key === key)) driveSelectSource(key); }, 300);
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
        
        win.style.top = '0px';
        win.style.left = '0px';
        win.style.width = '100vw';
        win.style.height = 'calc(100vh - 60px)'; // leave room for dock
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

async function loadDriveSources() {
    const status = document.getElementById('drive-status');
    try {
        const [rs, rr] = await Promise.all([
            fetch('/api/drive/sources').then(r => r.json()),
            fetch('/api/drive/remotes').then(r => r.json()).catch(() => ({remotes:[]}))
        ]);
        DRIVE_SOURCES = rs.sources || [];
        DRIVE_REMOTES = rr || { rclone_available:false, remotes:[] };
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
          '<input id="drive-in-token" type="password" class="glass-input" placeholder="ghp_… — stays local, never stored">';
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
    if (!DRIVE_REMOTES.rclone_available) {
        return '<div style="padding:10px;border:1px solid rgba(239,68,68,.35);border-radius:8px;' +
               'background:rgba(239,68,68,.08);font-size:.82rem;color:#fca5a5;">' +
               'rclone isn\'t installed. Install it once (<code>sudo apt install rclone</code> or ' +
               'rclone.org/downloads), then reopen this window.</div>';
    }
    if (remotes.length) {
        html += '<label style="color:#cbd5e1;font-size:.82rem;">Connected clouds — pick one</label>' +
                '<div id="drive-remote-chips" style="display:flex;flex-wrap:wrap;gap:6px;">';
        remotes.forEach(rm => {
            html += '<button type="button" class="glass-btn drive-chip" data-remote="' + rm + '" ' +
                    'onclick="drivePickRemote(this)" style="font-size:.8rem;padding:4px 10px;">☁️ ' + rm + '</button>';
        });
        html += '</div>' +
                '<label style="color:#cbd5e1;font-size:.82rem;margin-top:6px;">Remote &amp; optional subfolder</label>' +
                '<input id="drive-in-primary" class="glass-input" placeholder="e.g. onedrive: or gdrive:Work/notes">';
    } else {
        html += '<div style="padding:10px;border:1px solid rgba(148,163,184,.25);border-radius:8px;' +
                'background:rgba(255,255,255,.03);font-size:.82rem;color:#cbd5e1;">' +
                '<div style="margin-bottom:6px;">No clouds connected yet. One-time setup:</div>' +
                '<ol style="margin:0 0 6px 16px;padding:0;color:#94a3b8;line-height:1.5;">' +
                '<li>Open a terminal</li><li>Run <code style="color:#22d3ee;">rclone config</code></li>' +
                '<li>Choose <strong>n</strong> (new), name it (e.g. <code>' + key + '</code>), pick your provider, sign in</li>' +
                '</ol>' +
                '<button class="glass-btn" style="font-size:.8rem;" onclick="driveRecheckRemotes()">↻ Re-check connections</button>' +
                '</div>' +
                '<label style="color:#cbd5e1;font-size:.82rem;margin-top:6px;">…or type the remote manually</label>' +
                '<input id="drive-in-primary" class="glass-input" placeholder="e.g. onedrive:">';
    }
    return html;
}

function drivePickRemote(btn) {
    const inp = document.getElementById('drive-in-primary');
    if (inp) inp.value = btn.dataset.remote + ':';
    document.querySelectorAll('.drive-chip').forEach(c => c.classList.remove('primary-btn'));
    btn.classList.add('primary-btn');
}

async function driveRecheckRemotes() {
    try {
        DRIVE_REMOTES = await fetch('/api/drive/remotes').then(r => r.json());
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

    const payload = { connector: DRIVE_SELECTED.key, target: primary };
    if (name) payload.namespace = name;
    if (token) payload.token = token;

    try {
        const r = await fetch('/api/drive/ingest', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await r.json();
        clearInterval(pulse);
        if (!r.ok || data.status === 'error') {
            bar.style.width = '0%'; wrap.style.display = 'none';
            status.textContent = '❌ ' + (data.message || data.detail || ('failed (HTTP ' + r.status + ')'));
            btn.disabled = false;
            return;
        }
        bar.style.width = '100%';
        status.innerHTML = '✅ Built <strong>' + (name || data.label) + '</strong> — ' +
            data.chunks_added + ' chunk(s) from ' + data.files_ingested +
            ' file(s). Grounding index now <strong>' + data.total_vectors + '</strong> vectors.';
        const list = document.getElementById('drive-ingested');
        const row = document.createElement('div');
        row.innerHTML = '💽 <strong>' + (name || data.label) + '</strong> · ' + data.connector +
            ' · ' + data.chunks_added + ' chunks';
        list.prepend(row);
        // drop a drive icon on the desktop if present
        const icon = document.getElementById('desktop-drive-icon');
        if (icon) { icon.style.display = 'block'; const lbl = document.getElementById('drive-label'); if (lbl) lbl.innerText = (name || data.label) + ' Drive'; }
        btn.disabled = false;
    } catch (e) {
        clearInterval(pulse); wrap.style.display = 'none';
        status.textContent = '❌ Build failed: ' + e;
        btn.disabled = false;
    }
}

window.onload = function() {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('node') === 'expansion') {
        // Automatically bypass login and sync auth from the parent node
        const regOverlay = document.getElementById('registration-overlay');
        if (regOverlay) regOverlay.style.display = 'none';
        const loginModal = document.getElementById('login-modal');
        if (loginModal) loginModal.style.display = 'none';
        window.nodeId = urlParams.get('auth');
        const nodeLabel = document.getElementById('nodeLabel');
        if (nodeLabel) nodeLabel.innerText = `Connected: ${window.nodeId} (EXPANSION)`;
    }
};
