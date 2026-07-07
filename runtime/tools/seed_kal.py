#!/usr/bin/env python3
r"""
KAL V4 -- Character Knowledge Seeder + Index Rebuild

Reads all character genomes (knowledge.json, patterns.json, bio.json)
and injects them into the FAISS index with KAL V4 namespace/domain tags.

If the existing FAISS index has collapsed dimensions (d=1), this script
rebuilds the entire index from existing metadata + new character data
with a properly fitted 128-dim SwarmEmbedder.

Idempotent: checks for existing character data before adding.

Usage:
  .venv\Scripts\python.exe scripts/seed_kal.py [--dry-run] [--character haven]
  .venv\Scripts\python.exe scripts/seed_kal.py --rebuild
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("seed_kal")


# -- Namespace mapping -------------------------------------------------------

ARCHETYPE_NAMESPACE_MAP = {
    "merchant_npc": "game_lore",
    "warrior": "game_lore",
    "npc": "game_lore",
    "platform_ai_npc": "character_genome",
    "brand_ambassador": "character_genome",
    "technical_assistant": "character_genome",
    "wellness_companion": "character_genome",
}


def map_character_namespace(char_type):
    return ARCHETYPE_NAMESPACE_MAP.get(char_type, "character_genome")


# -- Data extraction ----------------------------------------------------------

def extract_knowledge_entries(char_id, char_dir, namespace):
    kpath = char_dir / "knowledge.json"
    if not kpath.exists():
        return []

    with open(kpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    for entity_name, entity in data.get("entities", {}).items():
        if entity.get("entity_type") == "person" and entity.get("depth") == "acquainted":
            continue
        desc = entity.get("description", "")
        if not desc:
            continue

        display = entity.get("display_name", entity_name)
        text = f"{display}: {desc}"
        domain = entity.get("topics", ["general"])[0] if entity.get("topics") else "general"

        entries.append({
            "pattern": text, "response": "",
            "source": "character_knowledge", "domain": domain,
            "character_id": char_id, "namespace": namespace,
            "entity_type": entity.get("entity_type", "concept"),
            "depth": entity.get("depth", "familiar"),
            "aliases": entity.get("aliases", []),
        })

        for emotion, variant_text in entity.get("emotion_variants", {}).items():
            entries.append({
                "pattern": f"{display} ({emotion}): {variant_text}",
                "response": variant_text,
                "source": "character_knowledge_emotion", "domain": domain,
                "character_id": char_id, "namespace": namespace,
                "entity_type": "emotion_variant", "depth": entity.get("depth", "familiar"),
                "emotion": emotion,
            })

    return entries


def extract_pattern_entries(char_id, char_dir, namespace):
    ppath = char_dir / "patterns.json"
    if not ppath.exists():
        return []

    with open(ppath, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    for pat in data.get("synthetic_patterns", []):
        triggers = pat.get("trigger", [])
        if not triggers:
            continue
        response = pat.get("response_template", "")
        trigger_text = " | ".join(triggers[:3])
        text = f"Q: {trigger_text} A: {response[:200]}" if response else f"Q: {trigger_text}"

        entries.append({
            "pattern": text, "response": response,
            "source": "character_pattern", "domain": pat.get("domain", "general"),
            "character_id": char_id, "namespace": namespace,
            "pattern_id": pat.get("id", ""), "confidence": pat.get("confidence", 0.5),
        })

    return entries


def extract_bio_entries(char_id, char_dir, namespace):
    bpath = char_dir / "bio.json"
    if not bpath.exists():
        return []

    with open(bpath, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = []
    name = data.get("name", char_id)

    desc = data.get("description", "")
    if desc:
        entries.append({
            "pattern": f"{name}: {desc}", "response": "",
            "source": "character_bio", "domain": "biography",
            "character_id": char_id, "namespace": namespace,
            "archetype": data.get("archetype", "unknown"),
        })

    values = data.get("immutable_core", {}).get("core_values", [])
    if values:
        entries.append({
            "pattern": f"{name} core values: {'; '.join(values)}",
            "response": "", "source": "character_bio", "domain": "core_values",
            "character_id": char_id, "namespace": namespace,
        })

    disclosure = data.get("metacognition", {}).get("disclosure", "")
    if disclosure:
        entries.append({
            "pattern": f"{name} identity: {disclosure}",
            "response": "", "source": "character_bio", "domain": "identity",
            "character_id": char_id, "namespace": namespace,
        })

    return entries


# -- Main seeder --------------------------------------------------------------

def seed_characters(characters=None, dry_run=False, force_rebuild=False):
    import faiss
    import numpy as np
    from ml.swarm_embedder import SwarmEmbedder

    chars_dir = ROOT / "characters"
    registry_path = chars_dir / "registry.json"
    index_path = ROOT / "data" / "faiss.index"
    meta_path = ROOT / "data" / "faiss_metadata.json"

    with open(registry_path, "r", encoding="utf-8") as f:
        registry = json.load(f)

    char_list = registry.get("characters", [])
    if characters:
        char_list = [c for c in char_list if c["character_id"] in characters]

    log.info(f"Processing {len(char_list)} characters")

    # ---- Extract new character entries ----
    new_entries = []
    for char in char_list:
        cid = char["character_id"]
        cdir = chars_dir / cid
        ctype = char.get("type", "unknown")
        ns = map_character_namespace(ctype)

        log.info(f"  [{cid}] type={ctype}, namespace={ns}")

        bio = extract_bio_entries(cid, cdir, ns)
        knowledge = extract_knowledge_entries(cid, cdir, ns)
        patterns = extract_pattern_entries(cid, cdir, ns)

        log.info(f"    bio={len(bio)}, knowledge={len(knowledge)}, patterns={len(patterns)}")

        new_entries.extend(bio)
        new_entries.extend(knowledge)
        new_entries.extend(patterns)

    log.info(f"\nNew entries extracted: {len(new_entries)}")

    if dry_run:
        log.info("DRY RUN -- no changes made")
        for entry in new_entries[:5]:
            text = entry["pattern"][:100]
            log.info(f"  [{entry['character_id']}] {entry['namespace']}/{entry['domain']}: {text}...")
        return new_entries

    # ---- Load existing metadata ----
    existing_meta = []
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            existing_meta = json.load(f)

    # ---- Check existing index dimension ----
    existing_dim = 0
    if index_path.exists():
        idx = faiss.read_index(str(index_path))
        existing_dim = idx.d
        log.info(f"Existing FAISS index: d={existing_dim}, n={idx.ntotal}")

    needs_rebuild = force_rebuild or existing_dim < 2
    if needs_rebuild:
        log.info(f"REBUILD required (existing d={existing_dim}, target d=128)")

    # ---- Deduplicate ----
    existing_chars = set()
    for m in existing_meta:
        cid = m.get("character_id", "")
        src = m.get("source", "")
        if cid and src.startswith("character_"):
            existing_chars.add(cid)

    if existing_chars and not needs_rebuild:
        log.warning(f"Found existing character data for: {existing_chars}")
        before = len(new_entries)
        new_entries = [e for e in new_entries if e["character_id"] not in existing_chars]
        log.info(f"  Skipping {before - len(new_entries)} duplicate entries")

    # ---- Combine all metadata for embedding ----
    if needs_rebuild:
        # Re-embed everything: existing metadata + new entries
        all_meta = existing_meta + new_entries
        all_texts = [m.get("pattern", "") for m in all_meta]
        log.info(f"Rebuilding: {len(existing_meta)} existing + {len(new_entries)} new = {len(all_meta)} total")
    else:
        if not new_entries:
            log.info("No new entries to add")
            return []
        all_meta = new_entries
        all_texts = [m.get("pattern", "") for m in all_meta]

    # ---- Fit SwarmEmbedder on the full corpus ----
    target_dim = 128
    embedder = SwarmEmbedder(dim=target_dim)

    # Fit on ALL texts for best vocabulary coverage
    log.info(f"Fitting SwarmEmbedder on {len(all_texts)} texts -> {target_dim}-dim")
    embedder.fit(all_texts)
    actual_dim = embedder.dim
    log.info(f"Actual embedding dimension: {actual_dim}")

    # ---- Embed in batches ----
    BATCH = 512
    all_vecs = []
    for i in range(0, len(all_texts), BATCH):
        batch = all_texts[i:i + BATCH]
        vecs = embedder.embed_texts(batch)
        all_vecs.append(vecs)
        log.info(f"  Embedded batch {i // BATCH + 1}/{(len(all_texts) + BATCH - 1) // BATCH}")

    vectors = np.vstack(all_vecs).astype("float32")
    log.info(f"Vectors shape: {vectors.shape}")

    # ---- Build new FAISS index ----
    if needs_rebuild:
        new_index = faiss.IndexFlatIP(actual_dim)
        new_index.add(vectors)
        final_meta = all_meta
    else:
        # Append to existing index (same dimension)
        existing_idx = faiss.read_index(str(index_path))
        if actual_dim != existing_idx.d:
            log.error(f"Dimension mismatch: embedder={actual_dim}, index={existing_idx.d}")
            return []
        existing_idx.add(vectors)
        new_index = existing_idx
        final_meta = existing_meta + new_entries

    # ---- Save ----
    faiss.write_index(new_index, str(index_path))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(final_meta, f)

    # Save the fitted embedder model for RAGPipeline to reload
    model_dir = ROOT / "data" / "models"
    model_dir.mkdir(parents=True, exist_ok=True)
    embedder.model_dir = model_dir
    embedder._save()
    log.info(f"Saved SwarmEmbedder model to {model_dir}")

    log.info(f"\nFAISS index saved: d={new_index.d}, n={new_index.ntotal}")
    log.info(f"Metadata saved: {len(final_meta)} entries")

    # ---- Stats ----
    ns_counts = {}
    char_counts = {}
    for e in (new_entries if not needs_rebuild else all_meta):
        ns = e.get("namespace", e.get("domain", "general"))
        ns_counts[ns] = ns_counts.get(ns, 0) + 1
        cid = e.get("character_id", "global")
        char_counts[cid] = char_counts.get(cid, 0) + 1

    log.info("\nBy namespace:")
    for ns, count in sorted(ns_counts.items()):
        log.info(f"  {ns}: {count}")
    log.info("\nBy character/source:")
    for cid, count in sorted(char_counts.items()):
        log.info(f"  {cid}: {count}")

    return new_entries


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed character data into KAL FAISS index")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--character", type=str, nargs="*", help="Specific character IDs")
    parser.add_argument("--rebuild", action="store_true", help="Force full index rebuild")
    args = parser.parse_args()

    t0 = time.time()
    entries = seed_characters(
        characters=args.character,
        dry_run=args.dry_run,
        force_rebuild=args.rebuild,
    )
    elapsed = time.time() - t0
    log.info(f"\nDone in {elapsed:.2f}s -- {len(entries)} entries processed")
