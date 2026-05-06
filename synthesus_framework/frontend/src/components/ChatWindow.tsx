import { useEffect, useRef } from 'react';
import type { ChatMessage } from '../types';

interface ChatWindowProps {
  messages: ChatMessage[];
  loading: boolean;
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
