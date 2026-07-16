# scripts/train_vocab.py
import os
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.generation.vocab_engine import VocabEngine
from core.generation.ngram_model import NgramModel

def train_domain(name: str, sources: list, output_path: str):
    print(f"Training domain: {name}...")
    engine = VocabEngine()
    all_texts = []
    for source in sources:
        if os.path.isdir(source):
            all_texts.extend(engine.ingest_directory(source))
        elif os.path.isfile(source):
            try:
                with open(source, 'r', encoding='utf-8') as f:
                    all_texts.append(f.read())
            except Exception: pass
            
    if not all_texts:
        print(f"Warning: No text found for domain {name}")
        return

    tables = engine.build_frequency_tables(all_texts)
    model = NgramModel(n=3)
    model.train_from_tables(tables)
    model.save(output_path)
    print(f"Saved {name} model to {output_path} (Vocab size: {len(model.vocab)})")

if __name__ == "__main__":
    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    # General Domain
    train_domain("general", [
        "README.md", 
        "TECHNICAL_DOCUMENTATION.md", 
        "PERSONA.md"
    ], "data/vocab_general.pkl")

    # GM Dialogue Domain
    train_domain("gm_dialogue", ["characters"], "data/vocab_gm_dialogue.pkl")

    # Sysops Domain
    train_domain("sysops", ["core", "api"], "data/vocab_sysops.pkl")
