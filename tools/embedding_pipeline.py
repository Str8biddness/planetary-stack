#!/usr/bin/env python3
"""
Synthesus 2.0 — Embedding Migration Pipeline
AIVM LLC

Downloads HuggingFace datasets, extracts Q/A patterns, embeds them with
SwarmEmbedder (TF-IDF + SVD), and builds a FAISS IndexFlatIP for semantic retrieval.

Optimized for 2-CPU / 8GB RAM sandbox:
  - Streams datasets (no full download)
  - Batched embedding with periodic saves
  - Checkpoint resume support
  - Memory-efficient processing

Target: Rebuild the 848K+ pattern knowledge base from the original
67 HuggingFace datasets plus character-specific patterns.
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import faiss
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/embedding_pipeline.log")
    ]
)
logger = logging.getLogger(__name__)

# ─── Configuration ───────────────────────────────────────────────────
PROJ_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJ_ROOT / "data"
INDEX_PATH = DATA_DIR / "faiss.index"
METADATA_PATH = DATA_DIR / "faiss_metadata.json"
CHECKPOINT_PATH = DATA_DIR / "migration_checkpoint.json"
ENRICHMENT_DIR = DATA_DIR / "enrichment"

EMBEDDING_DIM = 128  # SwarmEmbedder output dimension
BATCH_SIZE = 512
SAVE_EVERY = 10_000  # Save index every N patterns

# ─── Dataset Configurations ──────────────────────────────────────────
# Each entry: (hf_dataset_name, config, split, question_key, answer_key, max_rows)
DATASETS = [
    # Science & Reasoning
    ("allenai/ai2_arc", "ARC-Easy", "train", "question", "answerKey", 5000),
    ("allenai/ai2_arc", "ARC-Challenge", "train", "question", "answerKey", 3000),
    ("allenai/sciq", None, "train", "question", "correct_answer", 5000),
    ("allenai/openbookqa", "main", "train", "question_stem", "answerKey", 3000),
    
    # Common Sense
    ("tau/commonsense_qa", None, "train", "question", "answerKey", 5000),
    ("Rowan/hellaswag", None, "train", "ctx", "endings", 5000),
    ("aps/super_glue", "boolq", "train", "question", "label", 5000),
    
    # General Knowledge
    ("rajpurkar/squad", None, "train", "question", "answers", 10000),
    ("rajpurkar/squad_v2", None, "train", "question", "answers", 5000),
    ("Intel/orca_dpo_pairs", None, "train", "question", "chosen", 5000),
    
    # Instruction Following
    ("tatsu-lab/alpaca", None, "train", "instruction", "output", 10000),
    ("databricks/databricks-dolly-15k", None, "train", "instruction", "response", 10000),
    
    # Math & Logic
    ("openai/gsm8k", "main", "train", "question", "answer", 5000),
    
    # Truthfulness
    ("truthfulqa/truthful_qa", "generation", "validation", "question", "best_answer", 800),
    
    # Trivia
    ("mandarjoshi/trivia_qa", "rc", "train", "question", "answer", 10000),
    
    # Wikipedia Knowledge
    ("huggingartists/wikipedia", None, None, None, None, 0),  # Skip — needs special handling
    
    # Science Specific
    ("derek-thomas/ScienceQA", None, "train", "question", "answer", 3000),
    
    # Medical (for character domains)  
    ("openlifescienceai/medmcqa", None, "train", "question", "exp", 5000),
    
    # Financial (for character domains)
    ("takala/financial_phrasebank", "sentences_allagree", "train", "sentence", None, 3000),
]

def load_checkpoint() -> Dict:
    """Load migration checkpoint."""
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            return json.load(f)
    return {"completed_datasets": [], "total_embedded": 0, "status": "fresh"}

def save_checkpoint(cp: Dict):
    """Save migration checkpoint."""
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(cp, f, indent=2)

def extract_patterns_from_dataset(
    dataset_name: str,
    config: Optional[str],
    split: str,
    q_key: str,
    a_key: str,
    max_rows: int
) -> List[Dict]:
    """Extract Q/A patterns from a HuggingFace dataset."""
    from datasets import load_dataset
    
    patterns = []
    try:
        logger.info(f"Loading {dataset_name} (config={config}, split={split})...")
        
        try:
            if config:
                ds = load_dataset(dataset_name, config, split=split)
            else:
                ds = load_dataset(dataset_name, split=split)
        except Exception:
            # Fallback without trust_remote_code
            if config:
                ds = load_dataset(dataset_name, config, split=split, trust_remote_code=True)
            else:
                ds = load_dataset(dataset_name, split=split, trust_remote_code=True)
        
        count = 0
        for row in ds:
            if count >= max_rows:
                break
            
            question = str(row.get(q_key, "")).strip()
            if not question or len(question) < 5:
                continue
            
            # Handle different answer formats
            answer = ""
            if a_key is None:
                # Self-contained pattern (e.g., financial phrasebank)
                answer = question
                question = f"financial context: {question[:100]}"
            elif a_key == "answerKey":
                # Multiple choice — get the answer letter, try to resolve
                answer_key = str(row.get("answerKey", ""))
                choices = row.get("choices", {})
                if isinstance(choices, dict) and "text" in choices:
                    labels = choices.get("label", [])
                    texts = choices.get("text", [])
                    if answer_key in labels:
                        idx = labels.index(answer_key)
                        answer = texts[idx] if idx < len(texts) else answer_key
                    else:
                        answer = answer_key
                else:
                    answer = answer_key
            elif a_key == "answers":
                # SQuAD-style answers
                ans = row.get("answers", {})
                if isinstance(ans, dict):
                    texts = ans.get("text", [])
                    answer = texts[0] if texts else ""
                elif isinstance(ans, list):
                    answer = ans[0] if ans else ""
                else:
                    answer = str(ans)
            elif a_key == "endings":
                # HellaSwag: use the correct ending
                endings = row.get("endings", [])
                label = row.get("label", 0)
                if isinstance(label, str):
                    label = int(label) if label.isdigit() else 0
                answer = endings[label] if label < len(endings) else ""
            elif a_key == "label":
                # BoolQ
                label = row.get("label", 0)
                passage = str(row.get("passage", ""))[:500]
                answer = f"{'Yes' if label else 'No'}. {passage}"
            elif a_key == "chosen":
                # DPO pairs
                answer = str(row.get("chosen", ""))
            else:
                answer = str(row.get(a_key, "")).strip()
            
            if not answer or len(answer) < 3:
                continue
                
            # Advanced chunking for long answers
            if len(answer) > 400:
                # Split answers into chunks of up to 400 chars
                words = answer.split()
                chunks = []
                current_chunk = []
                current_len = 0
                for w in words:
                    if current_len + len(w) > 400 and current_chunk:
                        chunks.append(" ".join(current_chunk))
                        current_chunk = [w]
                        current_len = len(w)
                    else:
                        current_chunk.append(w)
                        current_len += len(w) + 1
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                
                for i, chunk in enumerate(chunks):
                    patterns.append({
                        "pattern": question if i == 0 else f"{question} (part {i+1})",
                        "response": chunk + ("..." if i < len(chunks)-1 else ""),
                        "source": dataset_name,
                        "domain": config or "general"
                    })
                count += 1
            else:
                patterns.append({
                    "pattern": question,
                    "response": answer,
                    "source": dataset_name,
                    "domain": config or "general"
                })
                count += 1
        
        logger.info(f"  Extracted {len(patterns)} patterns from {dataset_name}")
        return patterns
        
    except Exception as e:
        logger.error(f"  Failed to load {dataset_name}: {e}")
        return []

def load_character_patterns() -> List[Dict]:
    """Load all character-specific patterns from the characters/ directory."""
    chars_dir = PROJ_ROOT / "characters"
    patterns = []
    
    for char_dir in chars_dir.iterdir():
        if not char_dir.is_dir() or char_dir.name == "schema":
            continue
        
        pat_file = char_dir / "patterns.json"
        if not pat_file.exists():
            continue
        
        with open(pat_file) as f:
            data = json.load(f)
        
        char_id = data.get("character_id", char_dir.name)
        synth_patterns = data.get("synthetic_patterns", [])
        
        for sp in synth_patterns:
            triggers = sp.get("trigger", [])
            response = sp.get("response_template", "")
            domain = sp.get("domain", "character")
            
            for trigger in triggers:
                patterns.append({
                    "pattern": trigger,
                    "response": response,
                    "character_id": char_id,
                    "source": f"character/{char_id}",
                    "domain": domain
                })
        
        logger.info(f"  Loaded {len(synth_patterns)} patterns for character '{char_id}'")
    
    return patterns

def run_pipeline():
    """Main embedding pipeline."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ENRICHMENT_DIR.mkdir(parents=True, exist_ok=True)
    
    checkpoint = load_checkpoint()
    completed = set(checkpoint.get("completed_datasets", []))
    
    logger.info("=" * 60)
    logger.info("SYNTHESUS 2.0 — EMBEDDING MIGRATION PIPELINE")
    logger.info("=" * 60)
    
    # ── Step 1: Load embedding model ──
    logger.info("Loading SwarmEmbedder...")
    sys.path.insert(0, str(PROJ_ROOT))
    from ml.swarm_embedder import SwarmEmbedder
    embedder = SwarmEmbedder(dim=EMBEDDING_DIM)
    logger.info("SwarmEmbedder ready.")
    
    # ── Step 2: Load or create FAISS index ──
    if INDEX_PATH.exists() and checkpoint.get("total_embedded", 0) > 0:
        logger.info(f"Resuming from checkpoint: {checkpoint['total_embedded']} patterns already embedded")
        index = faiss.read_index(str(INDEX_PATH))
        with open(METADATA_PATH) as f:
            metadata = json.load(f)
    else:
        logger.info(f"Creating fresh FAISS index ({EMBEDDING_DIM}-dim, inner product / cosine sim)")
        index = faiss.IndexFlatIP(EMBEDDING_DIM)
        metadata = []
    
    total_before = index.ntotal
    logger.info(f"Index starts with {total_before} vectors")
    
    # ── Step 3: Load character patterns first ──
    if "character_patterns" not in completed:
        logger.info("\n─── Loading Character Patterns ───")
        char_patterns = load_character_patterns()
        if char_patterns:
            texts = [p["pattern"] for p in char_patterns]
            if not embedder.is_fitted:
                embedder.fit(texts)
            embeddings = embedder.embed_texts(texts)
            index.add(embeddings.astype(np.float32))
            metadata.extend(char_patterns)
            logger.info(f"Added {len(char_patterns)} character patterns")
        completed.add("character_patterns")
        checkpoint["completed_datasets"] = list(completed)
        checkpoint["total_embedded"] = index.ntotal
        save_checkpoint(checkpoint)
    
    # ── Step 4: Process HuggingFace datasets ──
    logger.info(f"\n─── Processing {len(DATASETS)} HuggingFace Datasets ───")
    
    for ds_name, config, split, q_key, a_key, max_rows in DATASETS:
        ds_id = f"{ds_name}_{config or 'default'}"
        
        if ds_id in completed:
            logger.info(f"  [SKIP] {ds_id} — already embedded")
            continue
        
        if max_rows == 0 or q_key is None:
            logger.info(f"  [SKIP] {ds_id} — requires special handling")
            completed.add(ds_id)
            continue
        
        patterns = extract_patterns_from_dataset(ds_name, config, split, q_key, a_key, max_rows)
        
        if patterns:
            # Embed in batches
            for i in range(0, len(patterns), BATCH_SIZE):
                batch = patterns[i:i + BATCH_SIZE]
                texts = [p["pattern"] for p in batch]
                if not embedder.is_fitted:
                    embedder.fit(texts)
                embeddings = embedder.embed_texts(texts)
                index.add(embeddings.astype(np.float32))
                metadata.extend(batch)
            
            logger.info(f"  Embedded {len(patterns)} patterns. Index total: {index.ntotal}")
        
        completed.add(ds_id)
        checkpoint["completed_datasets"] = list(completed)
        checkpoint["total_embedded"] = index.ntotal
        save_checkpoint(checkpoint)
        
        # Save index periodically
        if index.ntotal - total_before >= SAVE_EVERY:
            logger.info(f"  [SAVE] Saving index at {index.ntotal} vectors...")
            faiss.write_index(index, str(INDEX_PATH))
            with open(METADATA_PATH, "w") as f:
                json.dump(metadata, f)
            total_before = index.ntotal
    
    # ── Step 5: Final save ──
    logger.info("\n─── Final Index Save ───")
    faiss.write_index(index, str(INDEX_PATH))
    with open(METADATA_PATH, "w") as f:
        json.dump(metadata, f)
    
    checkpoint["status"] = "complete"
    checkpoint["total_embedded"] = index.ntotal
    checkpoint["completed_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_checkpoint(checkpoint)
    
    logger.info("=" * 60)
    logger.info(f"MIGRATION COMPLETE")
    logger.info(f"Total vectors in FAISS index: {index.ntotal}")
    logger.info(f"Metadata entries: {len(metadata)}")
    logger.info(f"Index file: {INDEX_PATH}")
    logger.info(f"Metadata file: {METADATA_PATH}")
    logger.info("=" * 60)
    
    return index.ntotal

if __name__ == "__main__":
    total = run_pipeline()
    print(f"\nDone. {total} patterns embedded.")
