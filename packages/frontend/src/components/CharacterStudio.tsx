import React, { useState } from 'react';
import './CharacterStudio.css';

export function CharacterStudio() {
  const [formData, setFormData] = useState({
    name: '',
    id: '',
    archetype: 'merchant',
    setting: 'medieval_fantasy',
    backstory: '',
    location: '',
    establishment: '',
    specialty: '',
    rank: '',
    years: 20,
    inventory_desc: '',
  });

  const [traits, setTraits] = useState<string[]>([]);
  const [newTrait, setNewTrait] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: name === 'years' ? parseInt(value) || 0 : value,
    }));
  };

  const handleAddTrait = (e: React.MouseEvent | React.KeyboardEvent) => {
    e.preventDefault();
    if (newTrait.trim() && !traits.includes(newTrait.trim())) {
      setTraits([...traits, newTrait.trim()]);
      setNewTrait('');
    }
  };

  const handleRemoveTrait = (traitToRemove: string) => {
    setTraits(traits.filter((t) => t !== traitToRemove));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setStatus(null);

    try {
      const payload = {
        ...formData,
        traits,
      };

      const res = await fetch('/api/v1/characters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Failed to generate character');
      }

      setStatus({
        type: 'success',
        message: `Successfully generated character genome for ${formData.name}! It is now available in the Chat tab.`,
      });
      
      // Optional: Clear form on success
      // setFormData({ ... });
      // setTraits([]);
    } catch (err: any) {
      setStatus({
        type: 'error',
        message: err.message || 'An unexpected error occurred.',
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="studio-container">
      <div className="studio-header">
        <h2>Character Studio</h2>
        <p>Visually design and deploy new NPC personas into the Synthesus Engine.</p>
      </div>

      <form className="studio-form" onSubmit={handleSubmit}>
        <div className="form-group">
          <label htmlFor="name">Display Name *</label>
          <input
            type="text"
            id="name"
            name="name"
            value={formData.name}
            onChange={handleChange}
            placeholder="e.g. Elda Brightwater"
            required
          />
        </div>

        <div className="form-group">
          <label htmlFor="id">Character ID (optional)</label>
          <input
            type="text"
            id="id"
            name="id"
            value={formData.id}
            onChange={handleChange}
            placeholder="e.g. elda (defaults to first name)"
          />
        </div>

        <div className="form-group">
          <label htmlFor="archetype">Archetype *</label>
          <select id="archetype" name="archetype" value={formData.archetype} onChange={handleChange} required>
            <option value="merchant">Merchant</option>
            <option value="guard">Guard</option>
            <option value="innkeeper">Innkeeper</option>
            <option value="scholar">Scholar</option>
            <option value="healer">Healer</option>
            <option value="blacksmith">Blacksmith</option>
          </select>
        </div>

        <div className="form-group">
          <label htmlFor="setting">World Setting</label>
          <input
            type="text"
            id="setting"
            name="setting"
            value={formData.setting}
            onChange={handleChange}
            placeholder="e.g. medieval_fantasy"
          />
        </div>

        <div className="form-group full-width">
          <label htmlFor="backstory">Backstory</label>
          <textarea
            id="backstory"
            name="backstory"
            value={formData.backstory}
            onChange={handleChange}
            placeholder="Describe the character's history and background..."
          />
        </div>

        <div className="form-group full-width">
          <label>Personality Traits</label>
          <div className="traits-input-container">
            <input
              type="text"
              value={newTrait}
              onChange={(e) => setNewTrait(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleAddTrait(e);
              }}
              placeholder="e.g. warm, gossipy, protective"
            />
            <button type="button" className="add-trait-btn" onClick={handleAddTrait}>
              Add
            </button>
          </div>
          <div className="traits-list">
            {traits.map((trait) => (
              <span key={trait} className="trait-tag">
                {trait}
                <button type="button" onClick={() => handleRemoveTrait(trait)}>
                  &times;
                </button>
              </span>
            ))}
          </div>
        </div>

        {/* Archetype-specific fields */}
        <div className="form-group">
          <label htmlFor="location">Location</label>
          <input
            type="text"
            id="location"
            name="location"
            value={formData.location}
            onChange={handleChange}
            placeholder="e.g. Riverbend"
          />
        </div>

        <div className="form-group">
          <label htmlFor="establishment">Establishment (Shop/Inn name)</label>
          <input
            type="text"
            id="establishment"
            name="establishment"
            value={formData.establishment}
            onChange={handleChange}
            placeholder="e.g. The Gilded Goose"
          />
        </div>

        <div className="form-group">
          <label htmlFor="specialty">Specialty / Field of Study</label>
          <input
            type="text"
            id="specialty"
            name="specialty"
            value={formData.specialty}
            onChange={handleChange}
            placeholder="e.g. ancient history"
          />
        </div>

        <div className="form-group">
          <label htmlFor="years">Years of Experience</label>
          <input
            type="number"
            id="years"
            name="years"
            value={formData.years}
            onChange={handleChange}
            min="0"
          />
        </div>

        {status && (
          <div className={`status-message ${status.type}`}>
            {status.message}
          </div>
        )}

        <div className="form-actions">
          <button type="submit" className="deploy-btn" disabled={loading || !formData.name}>
            {loading ? 'Generating Genome...' : 'Deploy Character'}
          </button>
        </div>
      </form>
    </div>
  );
}
