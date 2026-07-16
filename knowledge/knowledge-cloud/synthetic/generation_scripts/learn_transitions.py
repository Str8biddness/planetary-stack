#!/usr/bin/env python3
"""
Learn transition probabilities from dialogue data.
Analyzes conversation patterns to build transition graph automatically.
"""

import json
import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Set

def extract_dialogue_patterns(text_file: str) -> List[List[str]]:
    """Extract pattern sequences from dialogue logs."""
    patterns = []

    try:
        with open(text_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Split into conversations (assuming --- or similar separators)
        conversations = re.split(r'-{3,}|\n\s*\n\s*\n', content)

        for conv in conversations:
            if len(conv.strip()) < 100:  # Skip very short conversations
                continue

            # Extract knowledge entities mentioned
            entities_found = set()

            # Look for RPG entities (case-insensitive)
            entity_patterns = [
                r'\b(dragon|castle|dwarf|elf|orc|goblin|wizard|merchant|king|queen|prince|princess|knight|sword|shield|armor|potion|spell|magic|gold|treasure|quest|adventure)\b',
                r'\b(ironhaven|silvermoor|blackhollow|northern road|merchant alliance|duke|guild|tavern|forest|mountain|cave|dungeon|tower|village|city)\b',
                r'\b(fire|ice|magic|combat|trade|travel|exploration|hunting|farming|crafting|enchanting|healing|diplomacy)\b'
            ]

            for pattern in entity_patterns:
                matches = re.findall(pattern, conv.lower())
                entities_found.update(matches)

            if len(entities_found) >= 2:
                patterns.append(list(entities_found))

    except Exception as e:
        print(f"Error processing {text_file}: {e}")

    return patterns

def build_transition_graph(pattern_sequences: List[List[str]]) -> Dict[str, Dict[str, float]]:
    """Build transition probabilities from pattern sequences."""
    transitions = defaultdict(lambda: defaultdict(float))
    pair_counts = Counter()
    total_pairs = 0

    # Count co-occurrences
    for sequence in pattern_sequences:
        sequence = list(set(sequence))  # Remove duplicates within sequence
        for i in range(len(sequence)):
            for j in range(i + 1, len(sequence)):
                entity1, entity2 = sorted([sequence[i], sequence[j]])
                pair_counts[(entity1, entity2)] += 1
                total_pairs += 1

    # Convert to transition weights (0.1 to 1.0 scale)
    max_count = max(pair_counts.values()) if pair_counts else 1

    for (entity1, entity2), count in pair_counts.items():
        weight = 0.1 + (count / max_count) * 0.9  # Scale to 0.1-1.0

        # Add bidirectional transitions
        transitions[entity1][entity2] = weight
        transitions[entity2][entity1] = weight

    return dict(transitions)

def generate_context_buckets(learned_transitions: Dict[str, Dict[str, float]]) -> Dict[str, List[str]]:
    """Group entities into context buckets based on their relationships."""
    buckets = {
        "combat": [],
        "lore": [],
        "commerce": [],
        "magic": [],
        "social": [],
        "quest": [],
        "travel": [],
        "general": []
    }

    # Simple keyword-based bucketing
    keywords = {
        "combat": ["dragon", "orc", "goblin", "sword", "armor", "fight", "battle", "combat"],
        "lore": ["elf", "dwarf", "wizard", "magic", "spell", "ancient", "legend", "lore"],
        "commerce": ["merchant", "gold", "trade", "guild", "market", "buy", "sell", "commerce"],
        "magic": ["wizard", "spell", "magic", "enchant", "potion", "healing", "fire", "ice"],
        "social": ["king", "queen", "duke", "knight", "tavern", "village", "city", "social"],
        "quest": ["quest", "adventure", "treasure", "dungeon", "tower", "explore", "quest"],
        "travel": ["road", "travel", "forest", "mountain", "castle", "ironhaven", "travel"]
    }

    all_entities = set(learned_transitions.keys())
    for entity in all_entities:
        # Find best bucket match
        best_bucket = "general"
        best_score = 0

        for bucket, words in keywords.items():
            score = sum(1 for word in words if word in entity.lower())
            if score > best_score:
                best_score = score
                best_bucket = bucket

        buckets[best_bucket].append(entity)

    return buckets

def save_learned_transitions(learned_transitions: Dict[str, Dict[str, float]],
                           context_buckets: Dict[str, List[str]],
                           output_path: str):
    """Save learned transitions to JSON format."""
    # Convert to cloud_ prefixed entity IDs
    cloud_transitions = {}

    for from_entity, targets in learned_transitions.items():
        cloud_from = f"cloud_{from_entity.replace(' ', '_')}"
        cloud_transitions[cloud_from] = {}

        for to_entity, weight in targets.items():
            cloud_to = f"cloud_{to_entity.replace(' ', '_')}"

            # Find context bucket for this transition
            bucket = "general"
            for bucket_name, entities in context_buckets.items():
                if from_entity in entities or to_entity in entities:
                    bucket = bucket_name
                    break

            cloud_transitions[cloud_from][cloud_to] = {
                "weight": round(weight, 3),
                "context_buckets": [bucket]
            }

    # Build metadata
    metadata = {
        "version": "learned-v1.0",
        "description": "Automatically learned transitions from dialogue data",
        "created": "2026-04-06",
        "num_edges": sum(len(targets) for targets in cloud_transitions.values()),
        "context_buckets": list(context_buckets.keys()) + ["general"],
        "learning_method": "co-occurrence analysis",
        "data_sources": ["kaggle_grounding_v1.txt", "world_building_v1.txt"],
        "notes": [
            "Learned from dialogue co-occurrence patterns",
            "Weights scaled from co-occurrence frequency",
            "Context buckets assigned by keyword matching",
            "Can be combined with hand-curated transitions"
        ]
    }

    data = {
        "transitions": cloud_transitions,
        "metadata": metadata,
        "context_buckets_detail": context_buckets
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(cloud_transitions)} learned transitions to {output_path}")

def main():
    """Learn transitions from dialogue data."""
    data_dir = Path("data")

    # Find dialogue files
    dialogue_files = [
        "kaggle_grounding_v1.txt",
        "world_building_v1.txt",
        "massive_grounding_v1.txt",
        "unified_grounding_v1.txt"
    ]

    all_patterns = []

    for filename in dialogue_files:
        filepath = data_dir / filename
        if filepath.exists():
            print(f"Processing {filename}...")
            patterns = extract_dialogue_patterns(str(filepath))
            all_patterns.extend(patterns)
            print(f"  Found {len(patterns)} pattern sequences")

    print(f"\nTotal pattern sequences: {len(all_patterns)}")

    if not all_patterns:
        print("No patterns found. Using synthetic data for demonstration.")
        # Generate synthetic patterns
        all_patterns = [
            ["dragon", "castle", "combat"],
            ["merchant", "gold", "trade"],
            ["wizard", "spell", "magic"],
            ["elf", "forest", "lore"],
            ["dwarf", "mountain", "crafting"],
            ["orc", "battle", "combat"],
            ["potion", "healing", "magic"],
            ["quest", "treasure", "adventure"],
            ["tavern", "social", "drink"],
            ["road", "travel", "merchant"]
        ] * 10  # Multiply for more data

    # Learn transitions
    learned_transitions = build_transition_graph(all_patterns)
    context_buckets = generate_context_buckets(learned_transitions)

    print(f"Learned {len(learned_transitions)} entity relationships")
    print(f"Context buckets: {list(context_buckets.keys())}")

    # Save to file
    output_path = "data/knowledge_cloud/learned_transitions.json"
    save_learned_transitions(learned_transitions, context_buckets, output_path)

if __name__ == "__main__":
    main()
