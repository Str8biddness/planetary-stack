// Developer Portal JavaScript
const BASE = window.location.origin;

// Tab Navigation
document.querySelectorAll('.dev-nav-item').forEach(item => {
    item.addEventListener('click', () => {
        const tabId = item.dataset.tab;
        
        // Update active nav item
        document.querySelectorAll('.dev-nav-item').forEach(nav => nav.classList.remove('active'));
        item.classList.add('active');
        
        // Show corresponding tab content
        document.querySelectorAll('.tab-content').forEach(content => content.classList.add('hidden'));
        document.getElementById(`tab-${tabId}`).classList.remove('hidden');
        
        // Load tab-specific data
        if (tabId === 'keys') loadApiKeys();
        if (tabId === 'analytics') loadAnalytics();
    });
});

// API Key Management
const createKeyBtn = document.getElementById('createKeyBtn');
const createKeyForm = document.getElementById('createKeyForm');
const cancelKeyBtn = document.getElementById('cancelKeyBtn');
const submitKeyBtn = document.getElementById('submitKeyBtn');
const keyResultCard = document.getElementById('keyResultCard');
const doneKeyBtn = document.getElementById('doneKeyBtn');

if (createKeyBtn) {
    createKeyBtn.addEventListener('click', () => {
        createKeyForm.classList.remove('hidden');
        createKeyBtn.classList.add('hidden');
        document.getElementById('keysTableContainer').classList.add('hidden');
    });
}

if (cancelKeyBtn) {
    cancelKeyBtn.addEventListener('click', () => {
        createKeyForm.classList.add('hidden');
        createKeyBtn.classList.remove('hidden');
        document.getElementById('keysTableContainer').classList.remove('hidden');
    });
}

if (submitKeyBtn) {
    submitKeyBtn.addEventListener('click', async () => {
        const name = document.getElementById('newKeyName').value.trim();
        const tier = document.getElementById('newKeyTier').value;
        const expiresDays = document.getElementById('newKeyExpires').value;
        
        if (!name) {
            alert('Please enter a key name');
            return;
        }
        
        const adminKey = prompt('Enter your admin API key:');
        if (!adminKey) return;
        
        try {
            const response = await fetch(`${BASE}/api/v1/admin/api-keys`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-API-Key': adminKey
                },
                body: JSON.stringify({
                    name,
                    tier,
                    expires_days: expiresDays ? parseInt(expiresDays) : null,
                    rate_limit_per_minute: tier === 'enterprise' ? 1000 : tier === 'premium' ? 300 : 60
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to create key');
            }
            
            const data = await response.json();
            
            createKeyForm.classList.add('hidden');
            keyResultCard.classList.remove('hidden');
            document.getElementById('newKeyDisplay').textContent = data.api_key;
            
        } catch (error) {
            alert('Error creating key: ' + error.message);
        }
    });
}

if (doneKeyBtn) {
    doneKeyBtn.addEventListener('click', () => {
        keyResultCard.classList.add('hidden');
        createKeyBtn.classList.remove('hidden');
        document.getElementById('keysTableContainer').classList.remove('hidden');
        document.getElementById('newKeyName').value = '';
        document.getElementById('newKeyExpires').value = '';
        loadApiKeys();
    });
}

async function loadApiKeys() {
    const adminKey = prompt('Enter your admin API key to view keys:');
    if (!adminKey) {
        document.getElementById('keysTableBody').innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                    Admin key required to view API keys
                </td>
            </tr>
        `;
        return;
    }
    
    try {
        const response = await fetch(`${BASE}/api/v1/admin/api-keys`, {
            headers: { 'X-API-Key': adminKey }
        });
        
        if (!response.ok) {
            throw new Error('Failed to load keys');
        }
        
        const data = await response.json();
        const tbody = document.getElementById('keysTableBody');
        
        if (data.keys.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">
                        No API keys found. Create one to get started.
                    </td>
                </tr>
            `;
            return;
        }
        
        tbody.innerHTML = data.keys.map(key => `
            <tr>
                <td>${key.name}</td>
                <td><span class="tier-badge tier-${key.tier}">${key.tier}</span></td>
                <td>${new Date(key.created_at).toLocaleDateString()}</td>
                <td>${key.request_count.toLocaleString()}</td>
                <td>${key.is_active ? 
                    '<span style="color: var(--accent-green);">Active</span>' : 
                    '<span style="color: var(--accent-red);">Inactive</span>'}</td>
            </tr>
        `).join('');
        
    } catch (error) {
        document.getElementById('keysTableBody').innerHTML = `
            <tr>
                <td colspan="5" style="text-align: center; color: var(--accent-red); padding: 2rem;">
                    Error loading keys: ${error.message}
                </td>
            </tr>
        `;
    }
}

async function loadAnalytics() {
    const adminKey = prompt('Enter your admin API key to view analytics:');
    if (!adminKey) {
        document.getElementById('statActiveKeys').textContent = '—';
        document.getElementById('statRequestsHour').textContent = '—';
        document.getElementById('statAvgLatency').textContent = '—';
        return;
    }
    
    try {
        const response = await fetch(`${BASE}/api/v1/admin/usage`, {
            headers: { 'X-API-Key': adminKey }
        });
        
        if (!response.ok) {
            throw new Error('Failed to load analytics');
        }
        
        const data = await response.json();
        
        document.getElementById('statActiveKeys').textContent = data.active_keys || 0;
        document.getElementById('statRequestsHour').textContent = (data.requests_last_hour || 0).toLocaleString();
        document.getElementById('statAvgLatency').textContent = Math.round(data.avg_response_time_ms || 0);
        
    } catch (error) {
        document.getElementById('statActiveKeys').textContent = 'Err';
        document.getElementById('statRequestsHour').textContent = 'Err';
        document.getElementById('statAvgLatency').textContent = 'Err';
    }
}

// Load keys on page load if on keys tab
if (document.getElementById('tab-keys') && !document.getElementById('tab-keys').classList.contains('hidden')) {
    loadApiKeys();
}
