import json
import time
import os

AUDIT_FILE = os.path.join(os.path.dirname(__file__), "../../../data/foreman_audit.jsonl")

def log_audit(record: dict):
    # Ensure directory exists
    os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
    with open(AUDIT_FILE, "a") as f:
        record["ts"] = time.time()
        f.write(json.dumps(record) + "\n")
        
def get_audit_logs():
    if not os.path.exists(AUDIT_FILE):
        return []
    with open(AUDIT_FILE, "r") as f:
        return [json.loads(line) for line in f if line.strip()]
