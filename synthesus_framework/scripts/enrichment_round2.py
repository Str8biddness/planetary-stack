#!/usr/bin/env python3
"""
Synthesus 2.0 — Enrichment Round 2
Adds more datasets to push pattern count higher.
Resumes from existing FAISS index.
"""
import json, logging, os, sys, time
from pathlib import Path
import faiss
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.swarm_embedder import SwarmEmbedder
from datasets import load_dataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)

PROJ = Path(__file__).resolve().parent.parent
DATA = PROJ / "data"
INDEX = DATA / "faiss.index"
META = DATA / "faiss_metadata.json"
CP = DATA / "enrichment_r2_checkpoint.json"

DATASETS_R2 = [
    # More instruction-following
    ("TIGER-Lab/MathInstruct", None, "train", "instruction", "output", 2000),
    ("Open-Orca/OpenOrca", None, "train", "question", "response", 2000),
    # Coding knowledge
    ("sahil2801/CodeAlpaca-20k", None, "train", "instruction", "output", 2000),
    # Conversations
    ("HuggingFaceH4/ultrachat_200k", None, "train_sft", "messages", None, 2000),
    # Wikipedia-style facts
    ("wiki_qa", None, "train", "question", "answer", 2000),
    # Reasoning
    ("TIGER-Lab/MMLU-Pro", None, "test", "question", "answer", 2000),
    # More general knowledge
    ("lighteval/mmlu", "all", "test", "question", "answer", 2000),
    # Natural questions
    ("google-research-datasets/nq_open", None, "train", "question", "answer", 2000),
    # Ethics
    ("hendrycks/ethics", "justice", "train", "scenario", "label", 2000),
    # Winogrande (common sense)
    ("allenai/winogrande", "winogrande_xl", "train", "sentence", "answer", 2000),
]

def load_cp():
    if CP.exists():
        with open(CP) as f: return json.load(f)
    return {"done": [], "added": 0}

def save_cp(c):
    with open(CP, "w") as f: json.dump(c, f, indent=2)

def extract(name, config, split, qk, ak, maxr):
    patterns = []
    try:
        logger.info(f"Loading {name} config={config} split={split}...")
        ds = load_dataset(name, config, split=split) if config else load_dataset(name, split=split)
        count = 0
        for row in ds:
            if count >= maxr: break
            
            # Handle message-based datasets (ultrachat)
            if qk == "messages":
                msgs = row.get("messages", [])
                if len(msgs) >= 2:
                    q = msgs[0].get("content", "")[:300]
                    a = msgs[1].get("content", "")[:500]
                else:
                    continue
            else:
                q = str(row.get(qk, "")).strip()
                if ak == "label":
                    label = row.get("label", 0)
                    scenario = str(row.get(qk, ""))
                    a = f"{'Ethical/Just' if label else 'Unethical/Unjust'}: {scenario[:300]}"
                    q = f"Is this ethical? {scenario[:200]}"
                elif ak == "answer" and isinstance(row.get("answer"), list):
                    ans = row.get("answer", [])
                    a = ans[0] if ans else ""
                elif ak is None:
                    continue
                else:
                    a = str(row.get(ak, "")).strip()
            
            if not q or len(q) < 5 or not a or len(a) < 3: continue
            if len(a) > 500: a = a[:500] + "..."
            if len(q) > 300: q = q[:300]
            
            patterns.append({"pattern": q, "response": a, "source": name, "domain": config or "general"})
            count += 1
        
        logger.info(f"  Extracted {len(patterns)} from {name}")
        return patterns
    except Exception as e:
        logger.error(f"  Failed {name}: {e}")
        return []

def main():
    logger.info("Loading SwarmEmbedder...")
    embedder = SwarmEmbedder(dim=128)
    
    logger.info(f"Loading existing index from {INDEX}...")
    index = faiss.read_index(str(INDEX))
    with open(META) as f: metadata = json.load(f)
    logger.info(f"Starting with {index.ntotal} vectors")
    
    cp = load_cp()
    done = set(cp["done"])
    added_total = 0
    
    for name, config, split, qk, ak, maxr in DATASETS_R2:
        did = f"{name}_{config or 'def'}"
        if did in done:
            logger.info(f"[SKIP] {did}")
            continue
        
        pats = extract(name, config, split, qk, ak, maxr)
        if pats:
            for i in range(0, len(pats), 512):
                batch = pats[i:i+512]
                texts = [p["pattern"] for p in batch]
                if not embedder.is_fitted:
                    embedder.fit(texts)
                embs = embedder.embed_texts(texts)
                index.add(embs.astype(np.float32))
                metadata.extend(batch)
            added_total += len(pats)
            logger.info(f"  Index now: {index.ntotal} vectors (+{len(pats)})")
        
        done.add(did)
        cp["done"] = list(done)
        cp["added"] = added_total
        save_cp(cp)
    
    # Save final
    logger.info("Saving final index...")
    faiss.write_index(index, str(INDEX))
    with open(META, "w") as f: json.dump(metadata, f)
    logger.info(f"DONE. Total: {index.ntotal} vectors. Added this round: {added_total}")
    return index.ntotal

if __name__ == "__main__":
    main()
