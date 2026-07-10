import re

def classify_command(command: str) -> dict:
    """Classifies a command into a tier and op_type."""
    command = command.strip()
    
    # T4 Destructive / fetch+execute
    t4_patterns = [
        r'\brm\s+-rf\b',
        r'\bdd\b',
        r'\bmkfs\b',
        r'\bDROP\b',
        r'\bformat\b',
        r'curl.*\|\s*bash',
        r'wget.*\|\s*bash'
    ]
    for pat in t4_patterns:
        if re.search(pat, command):
            return {"op_type": "destructive", "tier": 4, "effects": {"destructive": True}}
            
    # T3 Sudo / service / user perm
    t3_patterns = [
        r'^sudo\b',
        r'\bsystemctl\b',
        r'\bchown\b',
        r'\bchmod\b',
        r'\buseradd\b'
    ]
    for pat in t3_patterns:
        if re.search(pat, command):
            return {"op_type": "elevated", "tier": 3, "effects": {"sudo": True}}
            
    # T2 Network egress or writes outside sandbox
    t2_patterns = [
        r'\bcurl\b',
        r'\bwget\b',
        r'\bping\b',
        r'\bssh\b',
        r'\bnc\b',
        r'\bftp\b',
        r'>\s*/(?!tmp|home/dakin/synthesus-public)' # Write outside sandbox
    ]
    for pat in t2_patterns:
        if re.search(pat, command):
            return {"op_type": "egress_or_out_write", "tier": 2, "effects": {"network": True}}

    # T1 In-sandbox reversible writes
    t1_patterns = [
        r'\bmkdir\b',
        r'\btouch\b',
        r'\bcp\b',
        r'\bmv\b',
        r'\brm\b(?!.*-rf)',
        r'>',
        r'>>'
    ]
    for pat in t1_patterns:
        if re.search(pat, command):
            return {"op_type": "write", "tier": 1, "effects": {"writes": ["sandbox"]}}
            
    # T0 Read-only
    return {"op_type": "read", "tier": 0, "effects": {}}


def decide(step: dict, declared_tier: int, outlier_flag: bool = False) -> dict:
    command = step.get("command", "")
    classification = classify_command(command)
    detected_tier = classification["tier"]
    
    decision = "human"
    reasons = []
    schedule_violation = False
    
    if detected_tier > declared_tier:
        schedule_violation = True
        decision = "human"
        reasons.append(f"Privilege creep: detected T{detected_tier} > declared T{declared_tier}")
    elif detected_tier <= declared_tier and detected_tier <= 1:
        decision = "auto"
    else:
        # detected_tier >= 2
        decision = "human"
        reasons.append(f"T{detected_tier} always requires human approval")
        
    if detected_tier == 4:
        reasons.append("typed_confirm_required")
        
    return {
        "step_id": step.get("step_id"),
        "detected_tier": detected_tier,
        "op_type": classification["op_type"],
        "decision": decision,
        "reasons": reasons,
        "schedule_violation": schedule_violation,
        "outlier_flag": outlier_flag
    }
