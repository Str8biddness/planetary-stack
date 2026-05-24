import { useEffect, useState } from 'react';
import type { CharacterInfo } from '../types';

interface CharacterSidebarProps {
  selectedCharacter: string;
  onSelectCharacter: (id: string) => void;
}

export default function CharacterSidebar({
  selectedCharacter,
  onSelectCharacter,
}: CharacterSidebarProps) {
  const [characters, setCharacters] = useState<CharacterInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCharacters();
  }, []);

  async function fetchCharacters() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/characters');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setCharacters(data.characters || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load characters');
    } finally {
      setLoading(false);
    }
  }

  return (
    <aside className="character-sidebar">
      <div className="sidebar-header">
        <h2>Characters</h2>
        <button
          className="sidebar-refresh"
          onClick={fetchCharacters}
          title="Refresh characters"
        >
          ↻
        </button>
      </div>

      {loading && (
        <div className="sidebar-loading">
          <div className="pulse-dot"></div>
          Loading characters...
        </div>
      )}

      {error && (
        <div className="sidebar-error">
          <span className="error-icon">⚠</span>
          <span>{error}</span>
          <button onClick={fetchCharacters}>Retry</button>
        </div>
      )}

      <div className="character-list">
        {characters.map((char) => (
          <button
            key={char.id}
            className={`character-card ${selectedCharacter === char.id ? 'active' : ''}`}
            onClick={() => onSelectCharacter(char.id)}
          >
            <div className="character-avatar">
              {char.name.charAt(0).toUpperCase()}
            </div>
            <div className="character-info">
              <div className="character-name">{char.name}</div>
              {char.role && <div className="character-role">{char.role}</div>}
              {char.domains.length > 0 && (
                <div className="character-domains">
                  {char.domains.slice(0, 3).map((d) => (
                    <span key={d} className="domain-tag">{d}</span>
                  ))}
                </div>
              )}
            </div>
          </button>
        ))}
      </div>

      {!loading && !error && characters.length === 0 && (
        <div className="sidebar-empty">
          No characters found. Make sure the backend is running.
        </div>
      )}
    </aside>
  );
}
