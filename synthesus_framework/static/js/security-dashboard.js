/**
 * GHOSTKEY Security Dashboard — Client-Side Logic
 * Synthesus 4.0 Cybersecurity Agent
 *
 * Handles:
 * - WebSocket connection for live alert updates
 * - REST API calls to /api/v1/security endpoints
 * - Dashboard state rendering and interaction
 */

const API_BASE = '/api/v1/security';
let ws = null;
let dashboardState = {};
let autoRefreshInterval = null;

// ═══════════════════════════════════════════════════════════════════
//  INITIALIZATION
// ═══════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    refreshDashboard();
    startAutoRefresh();

    // Filter handlers
    document.getElementById('severity-filter').addEventListener('change', refreshAlerts);
    document.getElementById('status-filter').addEventListener('change', refreshAlerts);
});

function startAutoRefresh() {
    autoRefreshInterval = setInterval(refreshDashboard, 10000); // Every 10s
}

// ═══════════════════════════════════════════════════════════════════
//  WEBSOCKET
// ═══════════════════════════════════════════════════════════════════

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${location.host}/ws/security`;

    try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log('[GhostKey] WebSocket connected');
            setActionStatus('Live connection established', 'success');
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleLiveUpdate(data);
            } catch (e) {
                console.error('[GhostKey] WS parse error:', e);
            }
        };

        ws.onclose = () => {
            console.log('[GhostKey] WebSocket disconnected, retrying...');
            setActionStatus('Reconnecting...', 'warning');
            setTimeout(connectWebSocket, 3000);
        };

        ws.onerror = () => {
            // Silent — onclose will handle reconnection
        };
    } catch (e) {
        console.error('[GhostKey] WebSocket error:', e);
        setTimeout(connectWebSocket, 5000);
    }
}

function handleLiveUpdate(data) {
    if (data.type === 'alert') {
        prependAlert(data.alert);
        updateStats(data.stats);
    } else if (data.type === 'scan_complete') {
        refreshDashboard();
        setActionStatus(`Scan complete: ${data.findings_count} findings`, 'success');
    } else if (data.type === 'status') {
        updateOverallStatus(data);
    }
}

// ═══════════════════════════════════════════════════════════════════
//  REST API CALLS
// ═══════════════════════════════════════════════════════════════════

async function apiCall(endpoint, method = 'GET', body = null) {
    const opts = {
        method,
        headers: { 'Content-Type': 'application/json' },
    };
    if (body) opts.body = JSON.stringify(body);

    try {
        const resp = await fetch(`${API_BASE}${endpoint}`, opts);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return await resp.json();
    } catch (e) {
        console.error(`[GhostKey] API error ${endpoint}:`, e);
        setActionStatus(`Error: ${e.message}`, 'error');
        return null;
    }
}

async function refreshDashboard() {
    const status = await apiCall('/status');
    if (status) {
        dashboardState = status;
        renderDashboard(status);
    }
}

async function refreshAlerts() {
    const severity = document.getElementById('severity-filter').value;
    const status = document.getElementById('status-filter').value;
    let endpoint = '/alerts?limit=50';
    if (severity) endpoint += `&severity=${severity}`;
    if (status) endpoint += `&status=${status}`;

    const data = await apiCall(endpoint);
    if (data) renderAlertList(data.alerts);
}

// ═══════════════════════════════════════════════════════════════════
//  ACTION HANDLERS
// ═══════════════════════════════════════════════════════════════════

async function triggerScan() {
    const btn = document.getElementById('btn-full-scan');
    btn.disabled = true;
    setActionStatus('Running full scan...', 'active');

    const result = await apiCall('/scan', 'POST');
    btn.disabled = false;

    if (result) {
        setActionStatus(`Scan complete: ${result.findings_count} findings in ${result.elapsed_ms}ms`, 'success');
        refreshDashboard();
    }
}

async function triggerBreach() {
    const btn = document.getElementById('btn-breach');
    btn.disabled = true;
    setActionStatus('Running Breach exercise...', 'active');

    const result = await apiCall('/scan/breach', 'POST', {});
    btn.disabled = false;

    if (result) {
        setActionStatus(`Breach complete: ${result.vectors_found} vectors found`, 'success');
        refreshDashboard();
    }
}

async function triggerBrute() {
    const btn = document.getElementById('btn-brute');
    btn.disabled = true;
    setActionStatus('Running brute-force simulation (10s)...', 'active');

    const result = await apiCall('/scan/brute', 'POST', {
        pattern: 'dictionary',
        duration_seconds: 10,
        requests_per_second: 5.0,
    });
    btn.disabled = false;

    if (result) {
        setActionStatus(`Simulation: ${result.total_attempts} attempts, pattern: ${result.detected_pattern || 'none'}`, 'success');
        refreshDashboard();
    }
}

async function exportReport() {
    setActionStatus('Generating report...', 'active');
    const report = await apiCall('/report');
    if (report) {
        const blob = new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `ghostkey-report-${new Date().toISOString().slice(0,10)}.json`;
        a.click();
        URL.revokeObjectURL(url);
        setActionStatus('Report exported', 'success');
    }
}

async function acknowledgeAlert(alertId) {
    await apiCall(`/alerts/${alertId}/acknowledge`, 'POST');
    refreshAlerts();
    refreshDashboard();
}

async function resolveAlert(alertId) {
    await apiCall(`/alerts/${alertId}/resolve`, 'POST');
    refreshAlerts();
    refreshDashboard();
}

// ═══════════════════════════════════════════════════════════════════
//  RENDERING
// ═══════════════════════════════════════════════════════════════════

function renderDashboard(state) {
    // Overall status
    updateOverallStatus(state);

    // Alert stats
    const stats = state.alert_stats || {};
    updateStats(stats);

    // Subsystems
    const subs = state.subsystems || {};
    document.getElementById('integrity-value').textContent = subs.immune_system || '—';
    document.getElementById('baseline-value').textContent = subs.baseliner || '0';
    document.getElementById('ghostnet-value').textContent = subs.ghostnet || '—';
    document.getElementById('breach-value').textContent = subs.breach_engine || '—';

    // Last scan time
    if (state.last_scan_time) {
        const d = new Date(state.last_scan_time * 1000);
        document.getElementById('last-scan-label').textContent = `Last scan: ${formatTimeAgo(d)}`;
    }

    // Alerts
    renderAlertList(state.recent_alerts || []);

    // Scans
    renderScanList(state.recent_scans || []);

    // Threats
    renderThreatFeed(state.ghostnet_threats || []);
}

function updateOverallStatus(state) {
    const indicator = document.getElementById('status-indicator');
    const text = document.getElementById('status-text');
    const statusMap = {
        'secure': { text: 'SECURE', class: 'status-secure' },
        'monitoring': { text: 'MONITORING', class: 'status-monitoring' },
        'warning': { text: 'WARNING', class: 'status-warning' },
        'critical': { text: 'CRITICAL', class: 'status-critical' },
    };

    const s = state.overall_status || 'secure';
    const config = statusMap[s] || statusMap['secure'];

    indicator.className = `status-badge ${config.class}`;
    text.textContent = config.text;

    // Active threats count
    const active = (state.alert_stats || {}).active || 0;
    document.getElementById('threat-count').textContent = active;
}

function updateStats(stats) {
    const bySev = stats.by_severity || {};
    const total = stats.total || 1;

    ['critical', 'high', 'medium', 'low'].forEach(sev => {
        const count = bySev[sev] || 0;
        const pct = Math.min((count / Math.max(total, 1)) * 100, 100);
        const bar = document.getElementById(`bar-${sev}`);
        const counter = document.getElementById(`count-${sev}`);
        if (bar) bar.style.width = `${pct}%`;
        if (counter) counter.textContent = count;
    });
}

function renderAlertList(alerts) {
    const container = document.getElementById('alert-list');
    if (!alerts || alerts.length === 0) {
        container.innerHTML = '<div class="empty-state">No alerts match current filters.</div>';
        return;
    }

    container.innerHTML = alerts.map(alert => `
        <div class="alert-card severity-${alert.severity}" onclick="toggleAlert(this, ${alert.id})">
            <div class="alert-header">
                <span class="alert-title">${escapeHtml(alert.title)}</span>
                <span class="alert-severity ${alert.severity}">${alert.severity}</span>
            </div>
            <div class="alert-desc">${escapeHtml(alert.description || '').slice(0, 120)}</div>
            <div class="alert-meta">
                <span>${alert.source}</span>
                <span>${alert.status}</span>
                <span>${alert.created_at ? formatTimeAgo(new Date(alert.created_at)) : ''}</span>
            </div>
            <div class="alert-actions">
                ${alert.status === 'new' ? `<button class="alert-action-btn" onclick="event.stopPropagation(); acknowledgeAlert(${alert.id})">✓ Acknowledge</button>` : ''}
                ${alert.status !== 'resolved' ? `<button class="alert-action-btn" onclick="event.stopPropagation(); resolveAlert(${alert.id})">✕ Resolve</button>` : ''}
            </div>
        </div>
    `).join('');
}

function renderScanList(scans) {
    const container = document.getElementById('scan-list');
    if (!scans || scans.length === 0) {
        container.innerHTML = '<div class="empty-state">No scans recorded yet.</div>';
        return;
    }

    container.innerHTML = scans.map(scan => `
        <div class="scan-entry">
            <span class="scan-type">${scan.scan_type}</span>
            <span class="scan-findings">${scan.findings_count} findings</span>
            <span class="scan-time">${scan.completed_at ? formatTimeAgo(new Date(scan.completed_at)) : '—'}</span>
        </div>
    `).join('');
}

function renderThreatFeed(threats) {
    const container = document.getElementById('threat-feed');
    if (!threats || threats.length === 0) {
        container.innerHTML = '<div class="empty-state">No active threats detected.</div>';
        return;
    }

    // Threats might be strings or objects
    container.innerHTML = threats.map(t => {
        const desc = typeof t === 'string' ? t : (t.threat || t.description || JSON.stringify(t));
        const source = typeof t === 'object' ? (t.source || 'ghostnet') : 'ghostnet';
        return `
            <div class="threat-entry">
                <div class="threat-source">${escapeHtml(source)}</div>
                <div class="threat-desc">${escapeHtml(desc)}</div>
            </div>
        `;
    }).join('');
}

// ═══════════════════════════════════════════════════════════════════
//  UTILITIES
// ═══════════════════════════════════════════════════════════════════

function toggleAlert(el, id) {
    el.classList.toggle('expanded');
}

function setActionStatus(text, type) {
    const el = document.getElementById('action-status-text');
    const colors = {
        'success': '#00ffcc',
        'error': '#ff3b5c',
        'warning': '#ffc23d',
        'active': '#3db4ff',
    };
    el.style.color = colors[type] || '#8892a4';
    el.textContent = text;

    if (type !== 'active') {
        setTimeout(() => { el.textContent = ''; }, 5000);
    }
}

function formatTimeAgo(date) {
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);

    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function prependAlert(alert) {
    const container = document.getElementById('alert-list');
    const empty = container.querySelector('.empty-state');
    if (empty) empty.remove();

    const html = `
        <div class="alert-card severity-${alert.severity}" onclick="toggleAlert(this, ${alert.id})">
            <div class="alert-header">
                <span class="alert-title">${escapeHtml(alert.title)}</span>
                <span class="alert-severity ${alert.severity}">${alert.severity}</span>
            </div>
            <div class="alert-desc">${escapeHtml(alert.description || '').slice(0, 120)}</div>
            <div class="alert-meta">
                <span>${alert.source}</span>
                <span>${alert.status}</span>
                <span>just now</span>
            </div>
            <div class="alert-actions">
                <button class="alert-action-btn" onclick="event.stopPropagation(); acknowledgeAlert(${alert.id})">✓ Acknowledge</button>
                <button class="alert-action-btn" onclick="event.stopPropagation(); resolveAlert(${alert.id})">✕ Resolve</button>
            </div>
        </div>
    `;
    container.insertAdjacentHTML('afterbegin', html);
}
