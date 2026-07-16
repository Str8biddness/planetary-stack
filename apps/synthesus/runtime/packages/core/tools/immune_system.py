import hashlib
import os
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

class ImmuneSystem:
    """
    The Digital Immune System for Ghostkey.
    Calculates SHA-256 hashes of critical source files to detect unauthorized modifications.
    """
    def __init__(self, root_dir: str = ".", signature_file: str = "data/immune_signatures.json"):
        self.root_dir = os.path.abspath(root_dir)
        self.signature_file = os.path.join(self.root_dir, signature_file)
        # Critical files to monitor (relative to Synthesus root)
        self.critical_files = [
            "core/quadbrain_master.py",
            "core/conscious_state.py",
            "core/consciousness_integrator.py",
            "core/tools/security.py",
            "core/tools/baseliner.py",
            "core/tools/immune_system.py",
            "core/tools/ghost_net.py",
            "../projects/ghostkey_quadbrain/backend.py"
        ]
        self.baseline_hashes = self._load_signatures()

    def _hash_file(self, filepath: str) -> Optional[str]:
        """Calculates the SHA-256 hash of a file."""
        hasher = hashlib.sha256()
        try:
            with open(filepath, 'rb') as f:
                # Read in chunks to handle potentially large files (though these are small scripts)
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"ImmuneSystem hashing error on {filepath}: {e}")
            return None

    def _load_signatures(self) -> Dict[str, str]:
        """Loads known good signatures."""
        if os.path.exists(self.signature_file):
            try:
                with open(self.signature_file, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def save_signatures(self) -> None:
        """Calculates and saves current file hashes as the baseline."""
        new_hashes = {}
        for rel_path in self.critical_files:
            abs_path = os.path.join(self.root_dir, rel_path)
            file_hash = self._hash_file(abs_path)
            if file_hash:
                new_hashes[rel_path] = file_hash
        
        os.makedirs(os.path.dirname(self.signature_file), exist_ok=True)
        with open(self.signature_file, "w") as f:
            json.dump(new_hashes, f, indent=2)
        self.baseline_hashes = new_hashes
        logger.info("ImmuneSystem: Baseline signatures saved.")

    def check_integrity(self) -> List[str]:
        """
        Verifies current files against the baseline.
        Returns a list of anomalies (modified or missing files).
        """
        # If no baseline exists, assume first run and create it.
        if not self.baseline_hashes:
            self.save_signatures()
            return []

        anomalies = []
        for rel_path in self.critical_files:
            abs_path = os.path.join(self.root_dir, rel_path)
            current_hash = self._hash_file(abs_path)
            
            baseline_hash = self.baseline_hashes.get(rel_path)
            
            if baseline_hash is None and current_hash is not None:
                # New file added to tracking but not in baseline
                anomalies.append(f"Untracked critical file detected: {rel_path}")
            elif baseline_hash is not None and current_hash is None:
                anomalies.append(f"Critical file missing/deleted: {rel_path}")
            elif baseline_hash != current_hash:
                anomalies.append(f"INTEGRITY COMPROMISED: {rel_path} has been modified!")
                
        return anomalies
