import json
import os
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class Baseliner:
    """
    Learns 'Normal' system behavior for Ghostkey.
    Stores baseline statistics to reduce false positives in anomaly detection.
    """
    def __init__(self, data_path: str = "data/baseline.json"):
        self.data_path = data_path
        self.baseline = self._load()
        self.sample_count = self.baseline.get("sample_count", 0)

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {"ports": {}, "processes": {}, "sample_count": 0}

    def save(self):
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, "w") as f:
            json.dump(self.baseline, f, indent=2)

    def record_sample(self, ports: List[int], processes: List[str]):
        """Records a new sample of 'current state'."""
        self.sample_count += 1
        self.baseline["sample_count"] = self.sample_count
        
        # Record Port occurrences
        for port in ports:
            port_str = str(port)
            self.baseline["ports"][port_str] = self.baseline["ports"].get(port_str, 0) + 1
            
        # Record Process occurrences
        for proc in processes:
            self.baseline["processes"][proc] = self.baseline["processes"].get(proc, 0) + 1
        
        if self.sample_count % 10 == 0:
            self.save()

    def is_anomaly(self, port: int = None, process: str = None) -> bool:
        """
        Determines if a port or process is an anomaly based on baseline frequency.
        Only starts alerting after a 'warm-up' period of 50 samples.
        """
        if self.sample_count < 50:
            return False
            
        if port:
            count = self.baseline["ports"].get(str(port), 0)
            # If seen in less than 5% of samples, it's suspicious
            return (count / self.sample_count) < 0.05
            
        if process:
            count = self.baseline["processes"].get(process, 0)
            return (count / self.sample_count) < 0.05
            
        return False
