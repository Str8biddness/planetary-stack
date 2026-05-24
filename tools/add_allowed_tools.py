import json
import os
from pathlib import Path

def main():
    base_dir = Path(__file__).parent.parent / "characters"
    
    # Define tool allocations based on character personas
    tool_allocations = {
        "computress": ["scraper", "kernel_analyze"],
        "lexis": ["scraper", "kernel_analyze", "code_executor"],
        "synth": ["scraper"],
        "synthesus": ["scraper", "kernel_analyze", "autonomous_takeover"],
        "haven": [],
        "garen": ["trade_calculator"]
    }
    
    for char_id, profiles in tool_allocations.items():
        bio_path = base_dir / char_id / "bio.json"
        if bio_path.exists():
            with open(bio_path, "r") as f:
                bio = json.load(f)
            
            bio["allowed_tools"] = profiles
            
            with open(bio_path, "w") as f:
                json.dump(bio, f, indent=2)
            print(f"Updated {char_id} with tools: {profiles}")

if __name__ == "__main__":
    main()
