import json
import os
import sys
from pathlib import Path

# Add project root to path for local imports
sys.path.append(os.getcwd())

try:
    from core.universal_substrate import UniversalSubstrate
except ImportError:
    print("Error: Could not import UniversalSubstrate. Ensure you're in the project root.")
    sys.exit(1)

def migrate():
    substrate = UniversalSubstrate()
    characters_dir = Path("characters")
    
    if not characters_dir.exists():
        print(f"Error: {characters_dir} not found.")
        return

    print(f"--- Starting Migration to Universal Substrate (V2) ---")
    
    for char_path in characters_dir.iterdir():
        if not char_path.is_dir():
            continue
            
        char_id = char_path.name
        if char_id == "schema":
            continue

        print(f"\nProcessing character: {char_id}")
        
        # Files to ingest
        genomes = {
            "bio.json": "bio",
            "patterns.json": "patterns",
            "knowledge.json": "knowledge",
            "personality.json": "personality"
        }
        
        for filename, param_suffix in genomes.items():
            file_path = char_path / filename
            if file_path.exists():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        
                    param_key = f"char_{char_id}.{param_suffix}"
                    # Ingest into substrate
                    print(f"  Ingesting {param_key}...")
                    substrate.set_parameter(
                        namespace=param_key,
                        value=data,
                        value_type="json",
                        domain="right_hemisphere", # Characters belong to cognitive domain
                        metadata={"source_file": str(file_path)}
                    )
                except Exception as e:
                    print(f"  Failed: {e}")
            else:
                print(f"  Skipping: {filename} not found.")

    print(f"\n--- Migration Complete ---")

if __name__ == "__main__":
    migrate()
