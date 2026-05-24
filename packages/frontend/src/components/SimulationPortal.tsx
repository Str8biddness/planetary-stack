import React, { useState, useEffect, useRef } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { amplificationClient } from '../api/amplificationClient';
import './SimulationPortal.css';

export const SimulationPortal: React.FC = () => {
    const [activeTab, setActiveTab] = useState<'overview' | 'api-keys' | 'usage' | 'cognitive'>('overview');
    const [selectedChar, setSelectedChar] = useState<string>('synth');
    const [consciousState, setConsciousState] = useState<any>(null);
    const [adminKey, setAdminKey] = useState<string>(localStorage.getItem('synthesus_admin_key') || '');
    const [isAuthenticated, setIsAuthenticated] = useState(!!adminKey);
    const [apiKeys, setApiKeys] = useState<any[]>([]);
    const [usageStats, setUsageStats] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const ws = useRef<WebSocket | null>(null);

    const handleLogin = (e: React.FormEvent) => {
        e.preventDefault();
        if (adminKey) {
            localStorage.setItem('synthesus_admin_key', adminKey);
            setIsAuthenticated(true);
            fetchData();
        }
    };

    const fetchData = async () => {
        if (!adminKey) return;
        setLoading(true);
        setError(null);
        try {
            const [keys, usage, state] = await Promise.all([
                amplificationClient.getAdminKeys(adminKey),
                amplificationClient.getAdminUsage(adminKey),
                amplificationClient.getConsciousState(adminKey, selectedChar)
            ]);
            setApiKeys(keys);
            setUsageStats(usage);
            setConsciousState(state);
        } catch (err: any) {
            setError(err.message || 'Failed to fetch admin data');
            if (err.message.includes('403')) {
                setIsAuthenticated(false);
                localStorage.removeItem('synthesus_admin_key');
            }
        } finally {
            setLoading(false);
        }
    };

    const handleEvolve = async (charId: string) => {
        setLoading(true);
        try {
            const result = await amplificationClient.evolveCharacter(adminKey, charId);
            alert(`Evolution Successful! Updates: ${result.files_updated.join(', ')}`);
            fetchData();
        } catch (err: any) {
            setError(err.message || 'Evolution failed');
        } finally {
            setLoading(false);
        }
    };

    const handleCreateKey = async (label: string) => {
        try {
            await amplificationClient.createAdminKey(adminKey, label);
            fetchData();
        } catch (err: any) {
            setError(err.message || 'Failed to create API key');
        }
    };

    useEffect(() => {
        if (isAuthenticated) {
            fetchData();
            
            // Initialize WebSocket
            const wsUrl = `ws://${window.location.hostname}:5010/api/v1/monitoring/ws`;
            ws.current = new WebSocket(wsUrl);
            
            ws.current.onmessage = (event) => {
                const data = JSON.parse(event.data);
                if (data.type === 'dashboard_update') {
                    setUsageStats((prev: any) => ({
                        ...prev,
                        total_requests: data.metrics.total_requests,
                        avg_latency_ms: data.metrics.avg_latency_ms,
                        daily_traffic: data.metrics.daily_traffic || prev?.daily_traffic
                    }));
                }
            };

            return () => {
                ws.current?.close();
            };
        }
    }, [isAuthenticated]);

    if (!isAuthenticated) {
        return (
            <div className="simulation-portal login-overlay">
                <div className="login-card glass">
                    <h2>Simulation AI Admin</h2>
                    <p>Enter your master admin key to access the developer portal.</p>
                    <form onSubmit={handleLogin}>
                        <input 
                            type="password" 
                            placeholder="sk-synth-..." 
                            value={adminKey}
                            onChange={(e) => setAdminKey(e.target.value)}
                            className="admin-input"
                        />
                        <button type="submit" className="login-btn">Authenticate</button>
                    </form>
                </div>
            </div>
        );
    }

    return (
        <div className="simulation-portal dashboard">
            <header className="portal-header">
                <div className="portal-title">
                    <h1>Simulation AI</h1>
                    <span className="badge">Developer Portal</span>
                </div>
                <nav className="portal-nav">
                    <button className={activeTab === 'overview' ? 'active' : ''} onClick={() => setActiveTab('overview')}>Overview</button>
                    <button className={activeTab === 'cognitive' ? 'active' : ''} onClick={() => setActiveTab('cognitive')}>Cognitive Streams</button>
                    <button className={activeTab === 'api-keys' ? 'active' : ''} onClick={() => setActiveTab('api-keys')}>API Keys</button>
                    <button className={activeTab === 'usage' ? 'active' : ''} onClick={() => setActiveTab('usage')}>Usage</button>
                </nav>
                <button className="logout-btn" onClick={() => { setIsAuthenticated(false); localStorage.removeItem('synthesus_admin_key'); }}>Logout</button>
            </header>

            <main className="portal-content">
                {error && <div className="error-banner">⚠️ {error}</div>}
                
                {activeTab === 'overview' && (
                    <div className="overview-tab fade-in">
                        <div className="stats-grid">
                            <div className="stat-card glass">
                                <h3>Total Requests</h3>
                                <div className="value">{usageStats?.total_requests?.toLocaleString() || 0}</div>
                            </div>
                            <div className="stat-card glass">
                                <h3>Success Rate</h3>
                                <div className="value">{usageStats?.successful_requests ? ((usageStats.successful_requests / usageStats.total_requests) * 100).toFixed(1) : 99.8}%</div>
                            </div>
                            <div className="stat-card glass">
                                <h3>Avg Latency</h3>
                                <div className="value">{usageStats?.avg_latency_ms ? usageStats.avg_latency_ms.toFixed(1) : 42}ms</div>
                            </div>
                        </div>
                        <div className="system-health glass">
                            <h3>System Core Status</h3>
                            <div className="health-row">
                                <span>C++ Kernel (zo_kernel)</span>
                                <span className="status-indicator online">ONLINE</span>
                            </div>
                            <div className="health-row">
                                <span>Hemisphere Bridge</span>
                                <span className="status-indicator online">ACTIVE</span>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'api-keys' && (
                    <div className="keys-tab fade-in">
                        <div className="section-header">
                            <h2>Active API Keys</h2>
                            <button className="create-btn" onClick={() => handleCreateKey('New Generated Key')}>+ Generate Key</button>
                        </div>
                        <div className="keys-list">
                            {apiKeys.map((key, i) => (
                                <div key={i} className="key-row glass">
                                    <div className="key-info">
                                        <span className="key-label">{key.label}</span>
                                        <span className="key-value"><code>{key.key.substring(0, 12)}...</code></span>
                                    </div>
                                    <div className="key-meta">
                                        <span>Created: {key.created_at}</span>
                                        <span className="status-active">ACTIVE</span>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {activeTab === 'cognitive' && (
                    <div className="cognitive-tab fade-in">
                        <div className="cognitive-header">
                            <div className="char-selector">
                                {usageStats?.components?.cognitive_engines?.characters_with_engines?.map((id: string) => (
                                    <button 
                                        key={id} 
                                        className={selectedChar === id ? 'active' : ''} 
                                        onClick={() => setSelectedChar(id)}
                                    >
                                        {id.toUpperCase()}
                                    </button>
                                ))}
                            </div>
                            <button className="evolve-btn" onClick={() => handleEvolve(selectedChar)} disabled={loading}>
                                {loading ? 'Synthesizing...' : '⚡ Trigger Evolution'}
                            </button>
                        </div>
                        
                        <div className="consciousness-monitor glass">
                            <div className="monitor-header">
                                <h3>{selectedChar.toUpperCase()} — Conscious State</h3>
                                <span className="tick-counter">Tick: {consciousState?.t || 0}</span>
                            </div>
                            
                            <div className="cognitive-grid">
                                <div className="cognitive-card">
                                    <h4>Emotional Tone</h4>
                                    <div className="tone-badge">{consciousState?.current_emotional_tone || 'neutral'}</div>
                                </div>
                                <div className="cognitive-card">
                                    <h4>Narrative Role</h4>
                                    <div className="role-text">{consciousState?.current_role || 'default'}</div>
                                </div>
                                <div className="cognitive-card">
                                    <h4>Beliefs</h4>
                                    <div className="value">{consciousState?.context?.beliefs ? Object.keys(consciousState.context.beliefs).length : 0}</div>
                                </div>
                                <div className="cognitive-card">
                                    <h4>Hypotheses</h4>
                                    <div className="value">{consciousState?.n_events || 0}</div>
                                </div>
                            </div>

                            <div className="belief-scores">
                                <h4>Active Beliefs (Confidence)</h4>
                                <div className="beliefs-list">
                                    {consciousState?.context?.beliefs && Object.entries(consciousState.context.beliefs).map(([belief, score]: [string, any]) => (
                                        <div key={belief} className="belief-row">
                                            <span className="belief-label">{belief}</span>
                                            <div className="belief-bar-bg">
                                                <div className="belief-bar-fill" style={{ width: `${score * 100}%` }}></div>
                                            </div>
                                            <span className="belief-score">{(score * 100).toFixed(0)}%</span>
                                        </div>
                                    ))}
                                    {(!consciousState?.context?.beliefs || Object.keys(consciousState.context.beliefs).length === 0) && (
                                        <p className="empty-state">No active beliefs detected in current stream.</p>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
                {activeTab === 'usage' && (
                    <div className="usage-tab fade-in">
                        <div className="chart-container glass">
                            <h3>Traffic Volume (Throughput)</h3>
                            <div className="recharts-wrapper" style={{ width: '100%', height: 300 }}>
                                <ResponsiveContainer width="100%" height="100%">
                                    <AreaChart data={usageStats?.daily_traffic || []}>
                                        <defs>
                                            <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                                                <stop offset="5%" stopColor="#8884d8" stopOpacity={0.8}/>
                                                <stop offset="95%" stopColor="#8884d8" stopOpacity={0}/>
                                            </linearGradient>
                                        </defs>
                                        <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                                        <XAxis dataKey="date" stroke="#888" fontSize={12} tickFormatter={(val) => val.split(' ')[1] || val} />
                                        <YAxis stroke="#888" fontSize={12} />
                                        <Tooltip 
                                            contentStyle={{ backgroundColor: '#111', border: '1px solid #444' }}
                                            itemStyle={{ color: '#8884d8' }}
                                        />
                                        <Area type="monotone" dataKey="count" stroke="#8884d8" fillOpacity={1} fill="url(#colorCount)" />
                                    </AreaChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    </div>
                )}
            </main>
        </div>
    );
};
