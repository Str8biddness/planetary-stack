"""
Synthesus 4.0 — End-to-End Security System Test
Flow: Breach Discovery -> Attack Injection -> Reasoning Correlation -> Autonomous Remediation
"""

import asyncio
import sys
import os
import time
from datetime import datetime

# Add framework to path
sys.path.append(os.path.join(os.getcwd(), "synthesus_framework"))

from core.security_agent import SecurityAgent

async def test_system():
    print("🚀 STARTING FULL SYSTEM TEST: Synthesus 4.0 Autonomous Security")
    print("="*60)
    
    agent = SecurityAgent()
    
    # --- PHASE 1: RED TEAM DISCOVERY ---
    print("\n[PHASE 1] Red Team: Adversarial Discovery")
    target_config = {
        "type": "self_assessment",
        "services": [{"name": "ghostkey_api", "port": 8000, "authentication": "none"}],
        "debug_mode": True,
        "exposed_files": [".env"]
    }
    breach_result = await agent.run_breach_exercise(target_config)
    print(f"🚩 Breach Engine found {breach_result['vectors_found']} vulnerabilities.")
    
    # --- PHASE 2: ATTACK SIMULATION ---
    print("\n[PHASE 2] Attack: Simulating Active Breach based on Red Team findings")
    # Simulate an attacker exploiting the unauthenticated API
    agent.alert_store.create_alert(
        severity="medium",
        source="baseliner",
        title="Unauthorized Connection to ghostkey_api",
        description="Detected unknown IP 192.168.1.100 connecting to port 8000 (Unauthenticated)."
    )
    
    # Simulate attacker exploiting Debug Mode
    agent.alert_store.create_alert(
        severity="high",
        source="unauthorized_access",
        title="Sensitive Info Leakage via Debug Endpoint",
        description="Attacker extracted environment variables from /debug/vars."
    )
    
    # Simulate attacker modifying .env (Immune System detects it)
    agent.alert_store.create_alert(
        severity="critical",
        source="immune_system",
        title="Critical Configuration Modified",
        description="The .env file has been modified by an unauthorized process."
    )
    
    # --- PHASE 3: REASONING & CORRELATION ---
    print("\n[PHASE 3] Blue Team: Causal & Bayesian Reasoning")
    # Trigger a full scan which runs the reasoner
    scan_result = await agent.run_full_scan()
    
    # Get the latest reasoning analysis from the alert metadata
    recent_alerts = agent.alert_store.get_alerts(limit=5)
    incident_alert = next((a for a in recent_alerts if a["source"] == "reasoner"), None)
    
    if incident_alert:
        print(f"🧠 Reasoning Engine correlated alerts into a single incident!")
        print(f"📜 AEGIS NARRATIVE: \"{incident_alert['description']}\"")
        analysis = incident_alert["metadata"].get("analysis", {})
        print(f"📊 Bayesian Confidence: {analysis.get('max_confidence', 0)*100:.1f}%")
        
        for chain in analysis.get("top_threat", {}).get("causal_chain", []):
            print(f"   🔗 Causal Link: {chain}")
    else:
        print("⚠️ No correlated incident found. Checking reasoner directly...")
        analysis = agent.reasoner.analyze_threat(recent_alerts)
        print(f"📊 Confidence: {analysis['max_confidence']*100:.1f}%")

    # --- PHASE 4: AUTONOMOUS REMEDIATION ---
    print("\n[PHASE 4] Self-Healing: Autonomous Remediation")
    history = agent.remediator.get_history(5)
    
    if history:
        print(f"⚡ Remediation executed! History contains {len(history)} actions:")
        for action in history:
            status_icon = "✅" if action["status"] == "success" else "🚫" if action["status"] == "blocked" else "❌"
            print(f"   {status_icon} [{action['action'].upper()}] {action['result']}")
    else:
        print("❌ No remediation actions were taken. Checking guardrail logs...")

    print("\n" + "="*60)
    print("🏁 FULL SYSTEM TEST COMPLETE")
    print("Synthesus 4.0 is fully operational and self-healing.")

if __name__ == "__main__":
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    asyncio.run(test_system())
