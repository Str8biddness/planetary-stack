import { useEffect, useRef } from 'react';
import type { CHALTelemetry, ChatMessage } from '../types';

interface ChatWindowProps {
  messages: ChatMessage[];
  loading: boolean;
}

function getCHALTelemetry(message: ChatMessage): CHALTelemetry | null {
  const telemetry = message.debug?.cognitive_hypervisor;
  if (!telemetry || typeof telemetry !== 'object') return null;
  return telemetry as CHALTelemetry;
}

function formatNumber(value: unknown, suffix = '') {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${value.toFixed(1)}${suffix}`
    : 'n/a';
}

function formatToken(value: string | undefined | null) {
  return value ? value.replaceAll('_', ' ') : 'n/a';
}

function TraceStat({ label, value }: { label: string; value: string | number | boolean }) {
  return (
    <div className="chal-trace-stat">
      <span className="chal-trace-label">{label}</span>
      <span className="chal-trace-value">{String(value)}</span>
    </div>
  );
}

function CHALTracePanel({ telemetry }: { telemetry: CHALTelemetry }) {
  const budget = telemetry.budget ?? {};
  const device = telemetry.device_isolation ?? {};
  const degraded = telemetry.degraded_state ?? null;
  const guard = telemetry.template_guard;
  const quadBrain = telemetry.quad_brain;
  const writeback = telemetry.memory_writeback;
  const writebackDecision = writeback?.decision;
  const writebackAccepted = writebackDecision?.accepted ?? writeback?.accepted;
  const writebackReason = writebackDecision?.reason ?? writeback?.reason;
  const writebackMount = writebackDecision?.target_mount ?? writeback?.target_mount;

  return (
    <details className="chal-trace-panel">
      <summary>
        <span>CHAL Trace</span>
        <span className={`chal-route-pill ${telemetry.degraded ? 'degraded' : ''}`}>
          {formatToken(telemetry.route)}
        </span>
      </summary>

      <div className="chal-trace-grid">
        <TraceStat label="Trace" value={telemetry.trace_id ?? 'n/a'} />
        <TraceStat label="Mode" value={formatToken(telemetry.hemisphere_mode)} />
        <TraceStat label="Preset" value={formatToken(telemetry.runtime_preset)} />
        <TraceStat label="Latency" value={formatNumber(telemetry.latency_ms, 'ms')} />
        <TraceStat label="Device" value={formatToken(device.status)} />
        <TraceStat label="Budget" value={telemetry.budget_exhausted ? 'exhausted' : 'ok'} />
        <TraceStat label="Template Guard" value={guard?.rewritten ? 'rewritten' : guard?.allowed === false ? 'blocked' : 'clear'} />
        <TraceStat label="Writeback" value={writebackAccepted ? 'accepted' : writebackReason ?? 'not reported'} />
      </div>

      <div className="chal-trace-section">
        <span className="chal-trace-section-title">Budget</span>
        <div className="chal-trace-chips">
          <span>{formatNumber(budget.latency_ms, 'ms')}</span>
          <span>{budget.retrieval_depth ?? 0} retrieval</span>
          <span>{budget.candidate_count ?? 0} candidates</span>
          <span>{budget.critic_passes ?? 0} critic</span>
        </div>
      </div>

      {telemetry.reasons && telemetry.reasons.length > 0 && (
        <div className="chal-trace-section">
          <span className="chal-trace-section-title">Route Reasons</span>
          <div className="chal-trace-chips">
            {telemetry.reasons.map((reason) => (
              <span key={reason}>{formatToken(reason)}</span>
            ))}
          </div>
        </div>
      )}

      {quadBrain && (
        <div className="chal-trace-section">
          <span className="chal-trace-section-title">Quad Brain</span>
          <div className="chal-trace-chips">
            <span>{formatToken(quadBrain.state_contract?.topology)}</span>
            <span>{formatToken(quadBrain.selected_source)}</span>
            <span>{quadBrain.state_contract?.integrity?.ok === false ? 'integrity warning' : 'integrity ok'}</span>
            <span>{formatNumber(quadBrain.latency_ms, 'ms')}</span>
          </div>
          {quadBrain.serial_order && (
            <div className="chal-trace-order">
              {quadBrain.serial_order.map((role) => (
                <span key={role}>{formatToken(role)}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {degraded && (
        <div className="chal-trace-section warning">
          <span className="chal-trace-section-title">Degraded State</span>
          <div className="chal-trace-chips">
            <span>{formatToken(degraded.reason)}</span>
            <span>{formatToken(degraded.device_status)}</span>
            <span>template leak: {degraded.legacy_template_leakage_allowed ? 'allowed' : 'blocked'}</span>
          </div>
        </div>
      )}

      {writeback && (
        <div className="chal-trace-section">
          <span className="chal-trace-section-title">Memory Writeback</span>
          <div className="chal-trace-chips">
            <span>{writebackAccepted ? 'accepted' : 'rejected'}</span>
            <span>{formatToken(writebackReason)}</span>
            <span>{writebackMount ?? '/mnt/mem/writeback'}</span>
          </div>
        </div>
      )}
    </details>
  );
}

export default function ChatWindow({ messages, loading }: ChatWindowProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  if (messages.length === 0 && !loading) {
    return (
      <div className="chat-window">
        <div className="chat-empty">
          <div className="chat-empty-icon">✦</div>
          <h2>Welcome to Synthesus</h2>
          <p>Select a character and start a conversation.</p>
          <p className="chat-empty-hint">
            Dual-hemisphere NPC intelligence — cognitive engine + ML swarm
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="chat-window">
      <div className="chat-messages">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`chat-msg ${msg.role} ${msg.error ? 'error' : ''}`}
          >
            <div className="chat-msg-header">
              <span className="chat-msg-role">
                {msg.role === 'user' ? 'You' : msg.character || 'Synthesus'}
              </span>
              {msg.source && msg.role === 'assistant' && (
                <span className="chat-msg-source">{msg.source}</span>
              )}
              {msg.emotion && msg.role === 'assistant' && (
                <span className="chat-msg-emotion">{msg.emotion}</span>
              )}
              {typeof msg.confidence === 'number' && msg.role === 'assistant' && (
                <span className="chat-msg-confidence">
                  {Math.round(msg.confidence * 100)}%
                </span>
              )}
            </div>
            <div className="chat-msg-body">{msg.content}</div>
            {msg.latency_ms != null && msg.role === 'assistant' && (
              <div className="chat-msg-meta">
                {msg.latency_ms.toFixed(1)}ms
              </div>
            )}
            {msg.role === 'assistant' && getCHALTelemetry(msg) && (
              <CHALTracePanel telemetry={getCHALTelemetry(msg)!} />
            )}
            
            {/* KAL & Generative Diagnostics */}
            {msg.debug && msg.role === 'assistant' && (
              <div className="kal-diagnostics">
                {msg.debug.kal_context && (
                  <div className="kal-stat">
                    <span className="kal-label">Knowledge Activation Layer (V4)</span>
                    <span className="kal-val">
                      {msg.debug.kal_context.cache_hit ? '⚡ L1 Cache' : '🧠 Semantic Search'} 
                      ({msg.debug.kal_context.results?.length || 0} nodes)
                    </span>
                  </div>
                )}
                {msg.source === 'pattern_engine' && msg.debug.generative_debug && (
                  <div className="kal-stat generative">
                    <span className="kal-label">Synthesis:</span>
                    <span className="kal-val">
                      Seed: "{msg.debug.generative_debug.seed}" | 
                      {msg.debug.generative_debug.generation_latency_ms}ms
                    </span>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div className="chat-msg assistant loading">
            <div className="chat-msg-body">
              <span className="typing-indicator">
                <span></span><span></span><span></span>
              </span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
