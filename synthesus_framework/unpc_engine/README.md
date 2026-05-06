# UNPC Engine - Universal NPC Character Generator

## Overview

The UNPC Engine is a **pattern synthesis system** that generates massive synthetic pattern datasets from simple character archetypes. It transforms a small character description into thousands of realistic patterns that can be loaded into the Synthesus left hemisphere to create fully-formed NPC personalities.

## Architecture

```
Character Archetype (Input)     →  Pattern Generator  →  Massive Pattern Genome (Output)
   ↓                                      ↓                         ↓
{name, role, backstory,         Expansion Algorithms      {1000+ synthetic patterns,
 traits, expertise}              - Expertise expander       generic patterns,
                                 - Backstory parser         confidence scores,
                                 - Personality mapper       domain classifications}
                                 - Opinion synthesizer
```

## How It Works

### Input: Character Archetype
You provide a JSON file describing the character:
- **Name** - Character's full name
- **Role** - Profession/archetype (software_engineer, doctor, merchant, warrior, etc.)
- **Age** - Character age
- **Backstory** - Detailed life story (education, career, experiences, achievements)
- **Traits** - Personality traits (analytical, creative, empathetic, etc.)
- **Expertise** - Technical/domain knowledge areas (20+ recommended)
- **Personality** - Response style (professional, warm, casual, formal)

### Processing: Pattern Expansion
The generator expands your archetype into:

1. **Expertise Patterns** (300-500 patterns)
   - Each expertise domain → 10-20 patterns
   - Technical knowledge, troubleshooting, best practices
   - Example: `python` expertise → patterns for debugging, libraries, syntax, performance

2. **Backstory Patterns** (50-200 patterns)
   - Life events parsed into conversational triggers
   - "Tell me about your time at Google" → narrative response
   - Temporal context (past, present, ongoing)

3. **Personality Patterns** (20-50 patterns)
   - Trait-based response behaviors
   - "What are you like?" → responses reflecting analytical/creative/direct traits

4. **Contextual Patterns** (50-100 patterns)
   - Role-specific situational responses
   - "How do you debug?" → methodology tied to role

5. **Opinion Patterns** (50-100 patterns)
   - Beliefs, preferences, philosophy
   - Tied to personality and role experience

6. **Generic Patterns** (3-5 patterns)
   - Universal greetings, thanks, goodbyes

### Output: Pattern Genome
A complete `patterns.json` file containing:
- **500-1000+ synthetic patterns** (expandable to 5000+)
- Unique hemisphere_id for character isolation
- PPBRS v2 schema compatibility
- Confidence scores for each pattern
- Domain classifications
- Fallback response

## Usage

### 1. Create an Archetype
```json
// archetypes/my_character.json
{
  "name": "Alex Rivera",
  "role": "software_engineer",
  "age": 35,
  "backstory": "Graduated MIT 2013. Worked at Google on Search Infrastructure for 5 years. Now Tech Lead at fintech startup. Led $2B payment system redesign...",
  "traits": ["analytical", "direct", "optimistic"],
  "expertise": ["python", "golang", "kubernetes", "distributed_systems", ...],
  "personality": "professional"
}
```

### 2. Generate Pattern Genome
```bash
python unpc_engine/pattern_generator.py \
  --archetype unpc_engine/archetypes/software_engineer.json \
  --output characters/alex_rivera/patterns.json \
  --expand 1000
```

### 3. Load into Synthesus
The generated `patterns.json` is automatically compatible with:
- Left hemisphere PPBRS pattern matcher
- Character Factory loader
- VCU rendering pipeline

```bash
# Start Synthesus with your new character
./build/synthesus --character alex_rivera
```

## Pattern Expansion Factor

The `--expand` parameter controls pattern density:
- **100** (default) - ~500 patterns, lightweight NPCs
- **1000** - ~2000 patterns, detailed NPCs with rich backstories
- **5000** - ~10,000 patterns, ultra-realistic characters with deep knowledge

For game NPCs with limited dialogue, use 100-500.
For main characters or complex AI agents, use 1000-5000.

## Example: Creating a Software Engineer NPC

**Archetype Input** (46 lines):
```json
{
  "name": "Alex Rivera",
  "expertise": ["python", "golang", "rust", "kubernetes", ...20 domains]
}
```

**Generated Output** (~2000 patterns):
- "How do you debug Python?" → "I reproduce the bug, check logs, use breakpoints..."
- "Tell me about your time at Google" → "I worked on Search Infrastructure for 5 years..."
- "What's your favorite language?" → "I learned Rust in 2020 and fell in love with memory safety..."
- "How do you approach code reviews?" → "I focus on readability, edge cases, performance..."
- And 1996 more patterns covering every aspect of Alex's technical knowledge and life story

## Benefits

✅ **Create infinite unique NPCs** - Each generated character has a unique personality
✅ **No cloud APIs** - All patterns are pre-generated and loaded locally
✅ **Realistic depth** - Characters have consistent backstories, opinions, expertise
✅ **Game-ready** - Output is optimized for real-time pattern matching
✅ **Scalable** - Generate 100 NPCs with different personalities in minutes

## Roadmap

- [ ] LLM-based backstory expansion (use right hemisphere to generate life events)
- [ ] Visual character creator UI
- [ ] Pattern deduplication and optimization
- [ ] Multi-language support
- [ ] Voice profile integration
- [ ] Emotion modeling

---
**UNPC Engine v1.0** | Part of AIVM Synthesus 2.0