import re
import shlex

# Auto-execution is ALLOW-LISTED and, in v1, restricted to PROVABLY READ-ONLY commands
# — ones with no write/exec/egress flag. Anything that can mutate state, execute, or
# reach the network (incl. writes like cp/mv/mkdir, escape-hatch tools like sed -i /
# awk 'system()' / find -delete / sort -o, and git write/egress subcommands) -> human.
# (v2 can widen auto to path-scoped writes with real argument analysis.)
AUTO_ALLOWLIST = {
    "ls", "cat", "pwd", "echo", "head", "tail", "wc", "grep", "egrep", "fgrep", "file",
    "stat", "du", "df", "which", "whoami", "id", "date", "uptime", "uname", "hostname",
    "tree", "cut", "diff", "basename", "dirname", "realpath", "printenv", "true", "false", "test",
}
# Only these git SUBcommands are read-only enough to auto-run; everything else (push,
# commit, config, clean, checkout, reset, ...) writes/egresses -> human.
GIT_READONLY = {"status", "log", "diff", "show", "branch", "ls-files", "rev-parse", "describe", "blame"}

# Chaining / redirect / command-substitution — a compound command cannot be safely
# reasoned about by simple patterns, so its presence forces human review.
_META = re.compile(r'[;&|`\n<>]|\$\(')


def _base_cmd(command: str) -> str:
    """First real command word (skips leading VAR=val), as a basename so
    ``/usr/bin/sudo`` -> ``sudo``."""
    try:
        parts = shlex.split(command)
    except Exception:
        parts = command.split()
    for p in parts:
        if re.match(r'^\w+=', p):        # skip environment assignments
            continue
        return p.split("/")[-1]
    return ""


def classify_command(command: str) -> dict:
    """Classify a command into a risk tier. Biased toward OVER-classifying: when a
    command is compound, privileged, destructive, or unrecognized, escalate."""
    command = command.strip()
    low = command.lower()

    # T4 — destructive / irreversible / fetch-and-execute (broad, case-insensitive).
    t4 = [
        r'\brm\b[^;|&]*(-\w*[rf]|--recursive|--force)',  # rm -rf / -fr / -r -f / --recursive ...
        r'\bdd\b', r'\bmkfs', r'\bfdisk\b', r'\bparted\b', r'\bshred\b', r'\bmkswap\b',
        r'>\s*/dev/', r'\bdrop\b', r'\btruncate\b', r'\bformat\b',
        r'(curl|wget)\b[^\n]*\|\s*(ba)?sh',              # curl ... | bash
    ]
    for p in t4:
        if re.search(p, low):
            return {"op_type": "destructive", "tier": 4, "effects": {"destructive": True}}

    # T3 — privilege escalation / service / user-perm. Detected ANYWHERE (not anchored),
    # so `x; sudo ...`, `A=1 sudo ...`, `/usr/bin/sudo ...` are all caught.
    t3 = [r'\bsudo\b', r'\bsu\b', r'\bdoas\b', r'\bpkexec\b', r'\bsystemctl\b',
          r'\bservice\b', r'\bchown\b', r'\bchmod\b', r'\buseradd\b', r'\busermod\b',
          r'\bgroupadd\b', r'\bpasswd\b', r'\bvisudo\b']
    for p in t3:
        if re.search(p, low):
            return {"op_type": "elevated", "tier": 3, "effects": {"sudo": True}}

    # ANY shell metacharacter / chaining / redirect / substitution -> not auto-classifiable.
    if _META.search(command):
        return {"op_type": "compound_or_redirect", "tier": 2, "effects": {"compound": True}}

    # T2 — network egress / package install / plain (irreversible) delete.
    t2 = [r'\bcurl\b', r'\bwget\b', r'\bping\b', r'\bssh\b', r'\bscp\b', r'\bsftp\b',
          r'\bnc\b', r'\bnetcat\b', r'\bftp\b', r'\btelnet\b', r'\brsync\b',
          r'\bpip[0-9]*\s+install\b', r'\bnpm\s+(i|install|ci)\b', r'\byarn\b',
          r'\bapt(-get)?\s+install\b', r'\bbrew\s+install\b', r'\brm\b']
    for p in t2:
        if re.search(p, low):
            return {"op_type": "egress_or_irreversible", "tier": 2, "effects": {"network_or_delete": True}}

    # T1 — in-sandbox reversible writes.
    for p in [r'\bmkdir\b', r'\btouch\b', r'\bcp\b', r'\bmv\b']:
        if re.search(p, low):
            return {"op_type": "write", "tier": 1, "effects": {"writes": ["sandbox"]}}

    # T0 — read-only.
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
        decision = "human"
        reasons.append(f"T{detected_tier} always requires human approval")

    # ALLOW-LIST gate on auto-execution (defense in depth): even a T0/T1 command only
    # auto-runs if its base command is a known read-only tool. Unknown binary -> human.
    if decision == "auto":
        base = _base_cmd(command)
        if base == "git":
            try:
                toks = shlex.split(command)
            except Exception:
                toks = command.split()
            sub = next((t for t in toks[1:] if not t.startswith("-")), "")
            if sub not in GIT_READONLY:
                decision = "human"
                reasons.append(f"git '{sub}' is not a read-only subcommand")
        elif base not in AUTO_ALLOWLIST:
            decision = "human"
            reasons.append(f"Base command '{base}' is not on the auto allow-list")

    if detected_tier == 4:
        reasons.append("typed_confirm_required")

    return {
        "step_id": step.get("step_id"),
        "detected_tier": detected_tier,
        "op_type": classification["op_type"],
        "decision": decision,
        "reasons": reasons,
        "schedule_violation": schedule_violation,
        "outlier_flag": outlier_flag,
    }
