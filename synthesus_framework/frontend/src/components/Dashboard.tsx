// frontend/src/components/Dashboard.tsx
// Real-time system monitoring dashboard

import { useState, useEffect, useCallback, useRef } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { amplificationClient } from '../api/amplificationClient';
import type { DashboardData, AmplificationMetrics } from '../api/amplificationClient';

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [metrics, setMetrics] = useState<AmplificationMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [trafficHistory, setTrafficHistory] = useState<Array<{time: string, rpm: number}>>([]);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const fetchData = useCallback(async () => {
    try {
      const metricsData = await amplificationClient.getAmplificationMetrics().catch(() => null);
      if (metricsData) setMetrics(metricsData);
    } catch (err) {
      console.warn('Failed to fetch amplification metrics', err);
    }
  }, []);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let fallbackInterval: number | null = null;

    if (autoRefresh) {
      // Connect to WebSocket
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host; 
      ws = new WebSocket(`${protocol}//${host}/api/v1/monitoring/ws`);

      ws.onmessage = (event) => {
        try {
          const dashboardData = JSON.parse(event.data);
          setData(dashboardData);
          setLastUpdate(new Date());
          setLoading(false);
          setError(null);
        } catch (e) {
          console.error("Failed to parse websocket message", e);
        }
      };

      ws.onerror = () => {
        console.warn('WebSocket connection error. Falling back to polling.');
      };

      // Poll fetching metrics separate
      fetchData();
      fallbackInterval = window.setInterval(fetchData, 30000); 

    } else {
      // Manual fetch
      amplificationClient.getDashboard()
        .then(dashboardData => {
          setData(dashboardData);
          setLastUpdate(new Date());
          setLoading(false);
          setError(null);
        })
        .catch(err => {
          setError('Failed to fetch dashboard data: ' + (err as Error).message);
          setLoading(false);
        });
      fetchData();
    }
    
    return () => {
      if (ws) ws.close();
      if (fallbackInterval) clearInterval(fallbackInterval);
    };
  }, [autoRefresh, fetchData]);

  // Update history buffer
  useEffect(() => {
    if (data?.traffic) {
      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      setTrafficHistory(prev => {
        // Prevent duplicate consecutive entries with same time to keep chart clean
        if (prev.length > 0 && prev[prev.length - 1].time === timeStr) return prev;
        return [...prev, { time: timeStr, rpm: data.traffic.requests_per_minute }].slice(-30);
      });
    }
  }, [data?.traffic]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [data?.recent_logs]);

  if (loading) {
    return (
      <div className="dashboard loading">
        <div className="spinner"></div>
        <p>Loading dashboard...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="dashboard error">
        <h2>Dashboard Error</h2>
        <p>{error}</p>
        <button onClick={fetchData}>Retry</button>
      </div>
    );
  }

  if (!data) {
    return <div className="dashboard">No data available</div>;
  }

  const { system, components, traffic, alerts } = data;

  return (
    <div className="dashboard">
      <header className="dashboard-header">
        <h1>Synthesus 3.0 System Dashboard</h1>
        <div className="controls">
          <label>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh (30s)
          </label>
          <button onClick={fetchData} className="refresh-btn">
            Refresh Now
          </button>
          <span className="last-update">
            Last updated: {lastUpdate.toLocaleTimeString()}
          </span>
        </div>
      </header>

      {/* System Status */}
      <section className="dashboard-section">
        <h2>System Status</h2>
        <div className="metrics-grid">
          <div className="metric-card">
            <span className="metric-label">Status</span>
            <span className={`metric-value status-${system.status}`}>
              {system.status}
            </span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Version</span>
            <span className="metric-value">{system.version}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Uptime</span>
            <span className="metric-value">{system.uptime_human}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Requests/min</span>
            <span className="metric-value">{traffic.requests_per_minute.toFixed(1)}</span>
          </div>
        </div>
      </section>

      {/* Components Status */}
      <section className="dashboard-section">
        <h2>Components</h2>
        <div className="components-grid">
          {Object.entries(components).map(([name, infoVal]) => {
            const info = infoVal as any;
            return (
              <div key={name} className={`component-card status-${info.status || 'active'}`}>
                <h3>{name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</h3>
                {info.status && (
                  <span className={`status-badge ${info.status}`}>{info.status}</span>
                )}
                {info.vectors !== undefined && (
                  <p>Vectors: {info.vectors.toLocaleString()}</p>
                )}
                {info.domains && (
                  <p>Domains: {info.domains.join(', ')}</p>
                )}
                {info.active !== undefined && (
                  <p>Active: {info.active}</p>
                )}
                {name === 'parameter_cloud_v2' && info.total_parameters && (
                  <div className="parameter-count">
                    <p>Scale: <strong>{(info.total_parameters / 1000000000).toFixed(2)}B</strong> Params</p>
                    <p>Hemispheres: {info.hemispheres.join(' | ')}</p>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* Amplification Metrics */}
      {metrics && (
        <section className="dashboard-section">
          <h2>Amplification Plane Metrics</h2>
          <div className="metrics-grid">
            <div className="metric-card">
              <span className="metric-label">Avg Risk</span>
              <span className="metric-value">{(metrics.triad_scores.avg_risk * 100).toFixed(1)}%</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Avg Confidence</span>
              <span className="metric-value">{(metrics.triad_scores.avg_confidence * 100).toFixed(1)}%</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">PROCEED</span>
              <span className="metric-value">{metrics.execution_recommendations.PROCEED}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">REQUEST_CONFIRMATION</span>
              <span className="metric-value">{metrics.execution_recommendations.REQUEST_CONFIRMATION}</span>
            </div>
          </div>

          {/* Organ Usage */}
          <h3>ML Organ Usage</h3>
          <div className="organ-usage">
            {Object.entries(metrics.organ_usage).map(([organ, count]) => (
              <div key={organ} className="organ-bar">
                <span className="organ-name">{organ.replace(/_/g, ' ')}</span>
                <div className="bar-container">
                  <div 
                    className="bar-fill" 
                    style={{ width: `${Math.min(100, (count / 200) * 100)}%` }}
                  />
                </div>
                <span className="organ-count">{count}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Traffic Stats & Graph */}
      <section className="dashboard-section">
        <h2>Traffic & Performance</h2>
        <div className="metrics-grid" style={{ marginBottom: '20px' }}>
          <div className="metric-card">
            <span className="metric-label">Total Requests</span>
            <span className="metric-value">{traffic.total_requests.toLocaleString()}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Active Sessions</span>
            <span className="metric-value">{traffic.active_sessions}</span>
          </div>
          <div className="metric-card">
            <span className="metric-label">Characters Loaded</span>
            <span className="metric-value">{traffic.characters_loaded}</span>
          </div>
        </div>
        
        <div className="chart-container" style={{ height: '300px', background: '#1a1a1a', padding: '20px', borderRadius: '8px', border: '1px solid #333' }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={trafficHistory}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="time" stroke="#888" tick={{fontSize: 12}} />
              <YAxis stroke="#888" tick={{fontSize: 12}} />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1a1a1a', border: '1px solid #333', borderRadius: '8px' }}
                itemStyle={{ color: '#00ff88' }}
              />
              <Line type="monotone" dataKey="rpm" name="Req/Min" stroke="#00ff88" strokeWidth={2} dot={false} activeDot={{ r: 6 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </section>

      {/* Cognitive State Inspector */}
      {data.cognitive_state && (
        <section className="dashboard-section">
          <h2>Cognitive State Inspector</h2>
          <div className="metrics-grid">
            <div className="metric-card">
              <span className="metric-label">Current Domain</span>
              <span className="metric-value" style={{ color: '#00d2ff' }}>
                {data.cognitive_state.current_domain}
              </span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Belief Nodes</span>
              <span className="metric-value">{data.cognitive_state.belief_count}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">Active Hypotheses</span>
              <span className="metric-value">{data.cognitive_state.hypothesis_count}</span>
            </div>
            <div className="metric-card">
              <span className="metric-label">State Time (t)</span>
              <span className="metric-value">{data.cognitive_state.t}</span>
            </div>
          </div>
        </section>
      )}

      {/* System Logs Stream */}
      <section className="dashboard-section">
        <h2>System Logs (Live)</h2>
        <div className="logs-terminal">
          {(!data.recent_logs || data.recent_logs.length === 0) ? (
            <div className="log-line empty">No recent warnings or errors.</div>
          ) : (
            data.recent_logs.map((log, i) => (
              <div key={i} className={`log-line log-${log.level.toLowerCase()}`}>
                <span className="log-time">{new Date(log.timestamp).toLocaleTimeString()}</span>
                <span className="log-level">[{log.level}]</span>
                <span className="log-component">[{log.component}]</span>
                <span className="log-message">{log.message}</span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </section>

      {/* Alerts */}
      {alerts.length > 0 && (
        <section className="dashboard-section alerts">
          <h2>Alerts</h2>
          {alerts.map((alert, index) => (
            <div key={index} className={`alert alert-${alert.level}`}>
              <strong>{alert.component}:</strong> {alert.message}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
