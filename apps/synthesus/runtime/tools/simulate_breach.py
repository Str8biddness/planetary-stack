"""
Breach Simulation — Red Team Adversarial Discovery
Triggers the BreachEngine to scan the system for vulnerabilities.
"""

import asyncio
import sys
import os

# Add framework to path
sys.path.append(os.path.join(os.getcwd(), "synthesus_framework"))

from core.security_agent import SecurityAgent

async def run_breach():
    print("⚔️ Initializing Red Team Breach Exercise...")
    
    agent = SecurityAgent()
    
    # Target configuration for self-assessment
    target_config = {
        "type": "self_assessment",
        "services": [
            {"name": "ghostkey_api", "port": 8000, "version": "4.0.1", "authentication": "none"},
            {"name": "internal_db", "port": 5432, "uses_defaults": True}
        ],
        "debug_mode": True,
        "exposed_files": [".env", "config.json", "public/readme.md"]
    }
    
    print("🔍 Scanning attack surface...")
    result = await agent.run_breach_exercise(target_config)
    
    if result["status"] == "complete":
        print(f"\n✅ Breach Exercise Complete in {result['elapsed_ms']}ms")
        print(f"🚩 Discovered {result['vectors_found']} Attack Vectors:")
        
        for i, vector in enumerate(result["vectors"], 1):
            print(f"\n[{i}] {vector['name'].upper()} ({vector['severity']})")
            print(f"    Category: {vector['category']}")
            print(f"    Target:   {vector['target_component']}")
            print(f"    Desc:     {vector['description']}")
            print(f"    Mitigation: {', '.join(vector['mitigations'])}")
            
        print("\n🧠 Integration: These vectors have been sent to the AlertStore.")
        print("Blue Team is now aware of these potential entry points.")
    else:
        print(f"❌ Breach Exercise Failed: {result.get('error')}")

if __name__ == "__main__":
    # Handle console encoding for Windows
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        
    asyncio.run(run_breach())
