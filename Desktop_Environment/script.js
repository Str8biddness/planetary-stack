// ==========================================
// WINDOW MANAGER LOGIC
// ==========================================
let highestZIndex = 100;
let isDragging = false;
let currentWindow = null;
let offsetX = 0, offsetY = 0;

function toggleWindow(id) {
    const win = document.getElementById(id);
    if (win.style.display === 'none') {
        win.style.display = 'flex';
        focusWindow(win);
        
        // Trigger lazy loading
        if (id === 'win-ide') fetchIDEFiles();
        if (id === 'win-twin') startTwinSimulation();
    } else {
        win.style.display = 'none';
        if (id === 'win-twin' && twinInterval) clearInterval(twinInterval);
    }
}

function focusWindow(win) {
    document.querySelectorAll('.window').forEach(w => w.classList.remove('focused'));
    highestZIndex++;
    win.style.zIndex = highestZIndex;
    win.classList.add('focused');
}

function dragWindow(e, id) {
    currentWindow = document.getElementById(id);
    focusWindow(currentWindow);
    
    isDragging = true;
    offsetX = e.clientX - currentWindow.offsetLeft;
    offsetY = e.clientY - currentWindow.offsetTop;
    
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
}

function onMouseMove(e) {
    if (!isDragging || !currentWindow) return;
    currentWindow.style.left = (e.clientX - offsetX) + 'px';
    currentWindow.style.top = (e.clientY - offsetY) + 'px';
}

function onMouseUp() {
    isDragging = false;
    currentWindow = null;
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
}

// Attach focus events to window bodies
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.window').forEach(win => {
        win.addEventListener('mousedown', () => focusWindow(win));
    });
    setInterval(fetchOSStatus, 2000);
});

// ==========================================
// OS BACKEND LOGIC
// ==========================================
let twinInterval;

async function fetchOSStatus() {
    try {
        const response = await fetch('http://127.0.0.1:8080/api/system/status');
        const data = await response.json();
        const driveEl = document.getElementById('sys-drive');
        if(driveEl) {
            driveEl.innerText = data['3way_drive_active'] ? '● Planetary Drive Mounted' : '○ Drive Offline';
            driveEl.style.color = data['3way_drive_active'] ? '#4ade80' : '#94a3b8';
        }
        const bridgeEl = document.getElementById('sys-bridge');
        if(bridgeEl) {
            bridgeEl.innerText = data['peripheral_bridge_active'] ? 'ACTIVE' : 'INACTIVE';
            bridgeEl.style.background = data['peripheral_bridge_active'] ? '#38bdf8' : '#333';
            bridgeEl.style.color = data['peripheral_bridge_active'] ? '#000' : '#fff';
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
        const response = await fetch('http://127.0.0.1:8080/api/ide/files');
        const treeData = await response.json();
        document.getElementById('ide-file-tree').innerHTML = '<ul><li><span class="folder" style="color: #38bdf8;">🌐 Planetary Drive</span>' + buildTreeHTML(treeData) + '</li></ul>';
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
    document.getElementById('ide-code-editor').value = `// Secure KVM File Stream: ${filename}\n\n[Content loaded from 3-Way Drive]`;
}

// ==========================================
// CHAT IPC
// ==========================================
async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();
    if(!message) return;
    
    const chatHistory = document.getElementById('chat-history');
    chatHistory.innerHTML += `<div class="message" style="border-left: 3px solid #facc15;"><strong>User:</strong> ${message}</div>`;
    input.value = '';
    chatHistory.scrollTop = chatHistory.scrollHeight;
    
    try {
        const response = await fetch('http://127.0.0.1:8080/api/chat', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message })
        });
        const data = await response.json();
        chatHistory.innerHTML += `<div class="message ai-message"><strong>Synthesus (Ring-0):</strong> ${data.response}</div>`;
        chatHistory.scrollTop = chatHistory.scrollHeight;
    } catch(err) {}
}

function handleChatKey(event) { if(event.key === 'Enter') sendChatMessage(); }

// ==========================================
// TWIN SIMULATION
// ==========================================
async function startTwinSimulation() {
    if(twinInterval) clearInterval(twinInterval);
    const log = document.getElementById('twin-log');
    let iter = 0;
    
    twinInterval = setInterval(() => {
        iter++;
        document.getElementById('stat-pt').innerText = (20 + (Math.random()*5)).toFixed(1) + ' s';
        document.getElementById('stat-pcv').innerText = (25 + (Math.random()*5)).toFixed(1) + ' %';
        document.getElementById('stat-toxin').innerText = (60 + (Math.random()*10)).toFixed(1) + ' %';
        document.getElementById('stat-pain').innerText = Math.floor(Math.random()*3 + 5) + '/10';
        
        const phase = iter % 2 === 0 ? "SYNTHESIZING VITAMIN K1" : "SEALING MICRO-VASCULATURE";
        const color = iter % 2 === 0 ? "#ef4444" : "#4ade80"; 
        log.innerHTML += `<div><span style="color:${color};">${phase}</span></div>`;
        log.scrollTop = log.scrollHeight;
    }, 2000);
}
