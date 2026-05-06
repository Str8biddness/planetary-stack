import { useState, useCallback } from 'react';
import ChatWindow from './components/ChatWindow';
import MessageInput from './components/MessageInput';
import CharacterSidebar from './components/CharacterSidebar';
import { Dashboard } from './components/Dashboard';
import { SimulationPortal } from './components/SimulationPortal';
import { MultimodalInput } from './components/MultimodalInput';
import { CharacterStudio } from './components/CharacterStudio';
import type { ChatMessage, QueryResponse } from './types';
import './App.css';

type ViewMode = 'chat' | 'dashboard' | 'simulator' | 'studio';

function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [selectedCharacter, setSelectedCharacter] = useState('synth');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [mode, setMode] = useState('auto');
  const [viewMode, setViewMode] = useState<ViewMode>('chat');
  const [error, setError] = useState<string | null>(null);

  const handleSend = useCallback(async (text: string) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    setError(null);

    try {
      const body: Record<string, unknown> = {
        query: text,
        character: selectedCharacter,
        mode,
        include_debug: true,
      };
      if (sessionId) body.session_id = sessionId;

      const res = await fetch('/api/v1/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        let errorDetail = `HTTP ${res.status}`;
        try {
          const errData = await res.json();
          errorDetail = errData.detail?.message || errData.detail || errorDetail;
        } catch { /* ignore parse error */ }

        const errorMsg: ChatMessage = {
          id: crypto.randomUUID(),
          role: 'assistant',
          content: `Error: ${errorDetail}`,
          timestamp: new Date().toISOString(),
          character: selectedCharacter,
          error: true,
        };
        setMessages((prev) => [...prev, errorMsg]);
        return;
      }

      const data: QueryResponse = await res.json();
      if (data.session_id) setSessionId(data.session_id);

      const assistantMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: data.response,
        timestamp: new Date().toISOString(),
        confidence: data.confidence,
        source: data.source,
        emotion: data.emotion ?? undefined,
        character: data.character,
        latency_ms: data.latency_ms,
        debug: data.debug,
        amplificationInfo: data.amplification_info ? {
          riskScore: data.amplification_info.risk_score,
          confidenceMargin: data.amplification_info.confidence_margin,
          attentionSensitivity: data.amplification_info.attention_sensitivity,
          executionRecommendation: data.amplification_info.execution_recommendation,
          organScores: data.amplification_info.organ_scores,
        } : undefined,
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Connection error: ${err instanceof Error ? err.message : 'Failed to reach Synthesus backend'}`,
        timestamp: new Date().toISOString(),
        character: selectedCharacter,
        error: true,
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  }, [selectedCharacter, sessionId, mode]);

  // Handle multimodal response
  const handleMultimodalResponse = useCallback((response: { text: string; amplificationInfo?: any }) => {
    const assistantMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: response.text,
      timestamp: new Date().toISOString(),
      character: selectedCharacter,
      amplificationInfo: response.amplificationInfo,
    };
    setMessages((prev) => [...prev, assistantMsg]);
    setLoading(false);
  }, [selectedCharacter]);

  // Handle multimodal error
  const handleMultimodalError = useCallback((errorMsg: string) => {
    setError(errorMsg);
    setLoading(false);
  }, []);

  const handleSelectCharacter = useCallback((id: string) => {
    setSelectedCharacter(id);
    setMessages([]);
    setSessionId(null);
  }, []);

  return (
    <div className="synthesus-app">
      {/* Starfield background */}
      <div className="starfield" aria-hidden="true">
        <div className="stars stars-1"></div>
        <div className="stars stars-2"></div>
        <div className="stars stars-3"></div>
      </div>

      <CharacterSidebar
        selectedCharacter={selectedCharacter}
        onSelectCharacter={handleSelectCharacter}
      />

      <main className="chat-main">
        <header className="chat-header">
          <div className="chat-header-left">
            <h1>Synthesus</h1>
            <span className="version-badge">3.0</span>
          </div>
          <div className="chat-header-controls">
            <select
              id="mode-select"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              title="Processing mode"
            >
              <option value="auto">Auto</option>
              <option value="cognitive">Cognitive</option>
              <option value="rag">RAG</option>
              <option value="pattern">Pattern</option>
            </select>

            <div className="view-toggle">
              <button
                className={viewMode === 'chat' ? 'active' : ''}
                onClick={() => setViewMode('chat')}
              >
                💬 Chat
              </button>
              <button
                className={viewMode === 'dashboard' ? 'active' : ''}
                onClick={() => setViewMode('dashboard')}
              >
                📊 Dashboard
              </button>
              <button
                className={viewMode === 'simulator' ? 'active' : ''}
                onClick={() => setViewMode('simulator')}
              >
                🛠️ Simulation
              </button>
              <button
                className={viewMode === 'studio' ? 'active' : ''}
                onClick={() => setViewMode('studio')}
              >
                🎨 Studio
              </button>
            </div>

            {sessionId && (
              <span className="session-indicator" title={`Session: ${sessionId}`}>
                ● Live
              </span>
            )}
          </div>
        </header>

        {viewMode === 'chat' ? (
          <>
            <ChatWindow messages={messages} loading={loading} />

            {error && (
              <div className="error-banner" onClick={() => setError(null)}>
                ⚠️ {error}
              </div>
            )}

            <div className="input-container">
              <MessageInput
                onSend={handleSend}
                disabled={loading}
                characterName={selectedCharacter}
              />

              <div className="multimodal-section">
                <h4>Multimodal Input</h4>
                <MultimodalInput
                  characterId={selectedCharacter}
                  sessionId={sessionId || ''}
                  onSend={handleMultimodalResponse}
                  onError={handleMultimodalError}
                />
              </div>
            </div>
          </>
        ) : viewMode === 'dashboard' ? (
          <Dashboard />
        ) : viewMode === 'studio' ? (
          <CharacterStudio />
        ) : (
          <SimulationPortal />
        )}
      </main>
    </div>
  );
}

export default App;
