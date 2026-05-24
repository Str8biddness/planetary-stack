import os
import time
import random
import subprocess
import json
import sys
import asyncio

# Ensure synthesus is in the path
# In the monorepo structure, synthesus_framework is in the same directory as backend.py
SYNTH_BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), "synthesus_framework"))
if SYNTH_BASE not in sys.path:
    sys.path.insert(0, SYNTH_BASE)

try:
    from core.quadbrain_master import QuadbrainMaster
    from core.synthesus_master import SynthesusMaster
    from core.crypto_provider import CryptoProvider
except ImportError as e:
    print(f"Warning: SynthesusMaster, QuadbrainMaster, or CryptoProvider not found ({e}). Using dummy master.")
    class QuadbrainMaster:
        def __init__(self):
            self.state = type('obj', (object,), {
                't': 0,
                'fluid': type('obj', (object,), {
                    'policy_prior': 0.5,
                    'risk_outcome': 0.1,
                    'attention': 0.5
                })
            })
        async def think(self, query, **kwargs):
            return {"answer": f"Dummy quadbrain response to: {query}"}
    class CryptoProvider:
        def encrypt(self, d): return d
        def decrypt(self, d): return d

# File Paths for IPC (Sync with MainActivity.java)
BASE_DIR = "/sdcard/GhostkeyQuadbrain"
INPUT_FILE = os.path.join(BASE_DIR, "input.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "output.txt")
CONSCIOUSNESS_FILE = os.path.join(BASE_DIR, "consciousness_state.txt")
CHAT_LOG = os.path.join(BASE_DIR, "chat_log.txt")
KEY_FILE = os.path.join(BASE_DIR, ".key")

crypto = None # Will be initialized when we get the key

def ensure_dir():
    global BASE_DIR, INPUT_FILE, OUTPUT_FILE, CONSCIOUSNESS_FILE, CHAT_LOG, KEY_FILE
    if not os.path.exists(BASE_DIR):
        try:
            os.makedirs(BASE_DIR)
            print(f"Created directory: {BASE_DIR}")
        except Exception as e:
            print(f"Error creating directory: {e}")
            BASE_DIR = os.path.join(os.path.dirname(__file__), "ipc_data")
            os.makedirs(BASE_DIR, exist_ok=True)
            INPUT_FILE = os.path.join(BASE_DIR, "input.txt")
            OUTPUT_FILE = os.path.join(BASE_DIR, "output.txt")
            CONSCIOUSNESS_FILE = os.path.join(BASE_DIR, "consciousness_state.txt")
            CHAT_LOG = os.path.join(BASE_DIR, "chat_log.txt")
            KEY_FILE = os.path.join(BASE_DIR, ".key")
            print(f"Falling back to local directory: {BASE_DIR}")

async def wait_for_secure_enclave(master):
    """Waits for the Android app to provide the Hardware-Secured IPC Key."""
    global crypto
    print("Waiting for Secure Enclave initialization from Android Host...")
    while True:
        if os.path.exists(KEY_FILE):
            try:
                with open(KEY_FILE, "r") as f:
                    key = f.read().strip()
                if key:
                    # Push key to AIOS Hardware-Secured Enclave (C++)
                    if master.runtime and master.runtime._emul_engine:
                        master.runtime._emul_engine.set_secure_key(key.encode())
                        print("✅ Key pushed to AIOS C++ TrustZone.")

                    crypto = CryptoProvider(key_str=key)
                    # Delete the key file from disk
                    os.remove(KEY_FILE)
                    print("✅ Secure Enclave IPC Key loaded and secured in memory.")
                    return
            except Exception as e:
                print(f"Error reading enclave key: {e}")
        
        # Fallback for testing without the app
        if os.environ.get("GHOSTKEY_TEST_MODE"):
            print("Running in test mode. Using dummy key.")
            crypto = CryptoProvider(key_str="GhostkeyTestModeKey2026!!!")
            return
            
        await asyncio.sleep(1)

def update_consciousness_file(master):
    """Writes consciousness state to file for Android UI (Encrypted)."""
    if hasattr(master, "shared_state"):
        fluid = master.shared_state.fluid
        t = master.shared_state.t
    else:
        fluid = master.state.fluid
        t = master.state.t

    # Hardware context from AIOS
    hardware_info = ""
    if hasattr(master, "runtime") and master.runtime and hasattr(master.runtime, "_host_profile"):
        profile = master.runtime._host_profile
        cpu = profile.get("cpu", {})
        mem = profile.get("memory", {})
        hardware_info = (f"Hardware: {cpu.get('model', 'Unknown')}\n"
                         f"Cores: {cpu.get('cores', 0)}\n"
                         f"RAM: {mem.get('total_mb', 0)}MB\n")

    # Average of policy_prior and attention can be a proxy for "consciousness level"
    c_val = (fluid.policy_prior + fluid.attention) / 2.0
    
    data = (f"Consciousness: {c_val:.4f}\n"
            f"MC: {fluid.policy_prior:.2f}\n"
            f"Psi: {fluid.attention:.2f}\n"
            f"NS: {fluid.risk_outcome:.2f}\n"
            f"Timestep: {t}\n"
            f"{hardware_info}")
    
    try:
        encrypted_data = crypto.encrypt(data)
        with open(CONSCIOUSNESS_FILE, "w") as f:
            f.write(encrypted_data)
    except Exception as e:
        print(f"Error updating consciousness file: {e}")

async def process_input(message, master):
    """Processes the message using QuadbrainMaster and returns a response."""
    message = message.strip()
    print(f"Processing message: {message}")
    
    # All commands (including 'scan') are now handled by QuadbrainMaster 
    # via the AgentDispatcher and the new SecurityTools module.
    try:
        result = await master.think(message, character_id="ghostkey")
        
        # Incorporate quadbrain metrics into the answer for debugging/visibility
        answer = result.get("answer", "No cognitive output produced.")
        if "quadbrain_metrics" in result:
            metrics = result["quadbrain_metrics"]
            if metrics.get("pattern_anomalies"):
                answer += f"\n\n[QUADBRAIN PATTERN ALERTS]:\n- " + "\n- ".join(metrics["pattern_anomalies"])

        return answer
    except Exception as e:
        print(f"Cognitive Error during think: {e}")
        return f"Cognitive Error: {str(e)}"

async def security_pulse(master):
    """Periodically performs background security checks."""
    while True:
        try:
            # Trigger an internal audit query
            # This will use the 'analyzer' tool via AgentDispatcher
            # We don't care about the return answer here, just the state update
            await master.think("audit device", character_id="ghostkey")
            print("Security pulse: Device audit completed via Quadbrain.")
        except Exception as e:
            print(f"Security pulse error: {e}")
        
        await asyncio.sleep(60)

async def main_loop():
    # Find the synthesus directory relative to this script
    current_dir = os.path.dirname(os.path.abspath(__file__))
    SYNTH_DIR = os.path.join(current_dir, "synthesus_framework")
    
    if os.path.exists(SYNTH_DIR):
        os.chdir(SYNTH_DIR)
        print(f"Changed working directory to: {SYNTH_DIR}")
    else:
        print(f"Warning: Synthesus directory not found at {SYNTH_DIR}")
    
    ensure_dir()
    
    master = QuadbrainMaster()
    await wait_for_secure_enclave(master)
    
    print("Ghostkey AI Backend (Quadbrain-powered) started. Monitoring for input...")
    
    # Start the security pulse in the background
    asyncio.create_task(security_pulse(master))
    
    last_consciousness_update = 0
    
    while True:
        # Update consciousness every 2 seconds
        if time.time() - last_consciousness_update > 2:
            update_consciousness_file(master)
            last_consciousness_update = time.time()
            
        # Check for input message
        if os.path.exists(INPUT_FILE):
            try:
                # Use a small wait to ensure file is fully written
                await asyncio.sleep(0.1)
                with open(INPUT_FILE, "r") as f:
                    encrypted_content = f.read().strip()
                
                if encrypted_content:
                    # Decrypt input via AIOS TrustZone if available
                    content = ""
                    if master.runtime and master.runtime._emul_engine:
                         try:
                             decrypted_bytes = master.runtime._emul_engine.decrypt_ipc(encrypted_content.encode())
                             content = decrypted_bytes.decode()
                             print("✅ Decrypted via AIOS Hardware-Secured Enclave.")
                         except Exception as e:
                             print(f"TrustZone decryption failed: {e}. Falling back to Python.")
                             content = crypto.decrypt(encrypted_content)
                    else:
                        content = crypto.decrypt(encrypted_content)

                    # Clear the input file immediately
                    os.remove(INPUT_FILE)
                    
                    if content:
                        # Process and write output
                        response = await process_input(content, master)
                        # Encrypt output
                        encrypted_response = crypto.encrypt(response)
                        with open(OUTPUT_FILE, "w") as f:
                            f.write(encrypted_response)
                        print(f"Response sent: {response}")
                        
                        # Log chat (Encrypted)
                        timestamp = time.strftime("%H:%M", time.localtime())
                        log_entry = crypto.encrypt(f"[{timestamp}] You: {content}\n[{timestamp}] Ghostkey: {response}\n\n")
                        with open(CHAT_LOG, "a") as f:
                            f.write(log_entry + "\n")
            except Exception as e:
                print(f"Error processing input: {e}")
        
        await asyncio.sleep(0.5)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("Backend stopped.")
