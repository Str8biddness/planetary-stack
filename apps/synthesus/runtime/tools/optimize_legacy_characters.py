import json
import os
from pathlib import Path

CHAR_DIR = Path("/home/dakin/Desktop/Synthesus_4.0/packages/characters")

CONFIGS = {
    "synth": {"scheduler": "realtime_principal", "permission": "agent"},
    "breach": {"scheduler": "realtime_principal", "permission": "agent"},
    "ghostkey": {"scheduler": "realtime_supporting", "permission": "agent"},
    "computress": {"scheduler": "realtime_supporting", "permission": "guest"},
    "garen": {"scheduler": "realtime_supporting", "permission": "guest"},
    "haven": {"scheduler": "realtime_supporting", "permission": "guest"},
    "lexis": {"scheduler": "realtime_supporting", "permission": "guest"},
    "synthesus": {"scheduler": "realtime_principal", "permission": "agent"},
}

def optimize_characters():
    for char_id, cfg in CONFIGS.items():
        bio_path = CHAR_DIR / char_id / "bio.json"
        if not bio_path.exists():
            print(f"Skipping {char_id}: bio.json not found")
            continue
            
        with open(bio_path, "r") as f:
            data = json.load(f)
            
        # Add 4.0 Metadata
        data["aivm_metadata"] = {
            "version": "4.0.0",
            "scheduler_class": cfg["scheduler"],
            "permission_level": cfg["permission"],
            "required_devices": [
                "VPD", "VMD", "VQD", "VGD", "VND", "VRD", "VSLLM"
            ]
        }
        
        # Add VTD if Agent
        if cfg["permission"] == "agent":
            data["aivm_metadata"]["required_devices"].append("VTD")
            
        # Ensure 'permission' is also at top level for current runtime logic
        data["permission"] = cfg["permission"]
        data["scheduler"] = cfg["scheduler"]

        with open(bio_path, "w") as f:
            json.dump(data, f, indent=2)
            
        print(f"Optimized {char_id} for AIVM 4.0")

if __name__ == "__main__":
    optimize_characters()
