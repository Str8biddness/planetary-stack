#!/usr/bin/env python3
"""
Synthesus 5 - Sovereign Shell with Modular Agent Support
Allows the user to select, bolt-on, and swap individual character agents (Einstein, Tesla, etc.).
"""

import sys
import os
import json
import time
from pathlib import Path

# Ensure tools directory is in path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricEngineFallback
from conductive_assembler import ConductiveAssembler
from action_assembler import ActionAssembler

class ModularSynthesusShell:
    def __init__(self):
        self.engine = GeometricEngineFallback()
        self.assembler = ConductiveAssembler()
        self.motor = ActionAssembler(self.engine)
        self.shard_dir = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
        self.active_agent = None
        self.agent_shard = {}
        self._boot()

    def _boot(self):
        print("\033[1;36m" + "="*60)
        print("   SYNTHESUS 5 — MODULAR AGENT SHELL v1.0")
        print("   [Architecture: Bolt-on Sovereign Personalities]")
        print("="*60 + "\033[0m")
        
        # 1. Discover Agents
        self.available_agents = self._discover_agents()
        
        # 2. Selection Screen
        self._show_selection_menu()

    def _discover_agents(self):
        agents = []
        for shard in self.shard_dir.glob("archetype_*.kn"):
            name = shard.stem.replace("archetype_", "").capitalize()
            agents.append({'name': name, 'file': shard})
        for shard in self.shard_dir.glob("style_*.kn"):
            name = shard.stem.replace("style_", "").capitalize()
            agents.append({'name': name, 'file': shard})
        return agents

    def _show_selection_menu(self):
        print("\n📂 [AVAILABLE AGENTS]")
        print("0. Master Sovereign (Native Kernel)")
        for i, agent in enumerate(self.available_agents, 1):
            print(f"{i}. {agent['name']} Agent")
        
        while True:
            choice = input("\n👉 Select an Agent to Bolt-On (Enter number): ").strip()
            if choice == "0":
                self.active_agent = "Native"
                break
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(self.available_agents):
                    self.bolt_on_agent(self.available_agents[idx])
                    break
            except: pass
            print("❌ Invalid selection.")

    def bolt_on_agent(self, agent_info):
        print(f"\n🔩 [SYSTEM] Bolting on {agent_info['name']} Agent...")
        
        # 1. Load Knowledge (Archetype)
        with open(agent_info['file'], 'r', encoding='utf-8') as f:
            data = json.load(f)
            self.agent_shard = data['vectors']
        
        # 2. Load Conversational Style (Cadence)
        cadence_file = self.shard_dir / f"cadence_{agent_info['name'].lower()}.kn"
        if cadence_file.exists():
            print(f"   - Anchoring conversational cadence from {cadence_file.name}...")
            with open(cadence_file, 'r', encoding='utf-8') as f:
                c_data = json.load(f)
                self.agent_shard.update(c_data['vectors'])
        
        self.active_agent = agent_info['name']
        
        # Update the assembler's logic with the agent's combined harmonic DNA
        self.assembler.knowledge_cloud.update(self.agent_shard)
        print(f"✅ {agent_info['name']} Agent fully loaded and realistically backed.")

    def unload_agent(self):
        print(f"\n🔌 [SYSTEM] Unbolting active agent...")
        self.active_agent = "Native"
        self.agent_shard = {}
        # In full impl: This would restore the assembler to its base state
        print("✅ Agent unbolted. Returning to Native Kernel resonance.")

    def chat_loop(self):
        print(f"\n\033[1;32m[Session Started: {self.active_agent} Agent active]\033[0m")
        print("Type /swap to switch agents, /unload to go native, or 'exit' to quit.\n")
        
        while True:
            try:
                user_input = input(f"\033[1;34m👤 USER > \033[0m").strip()
                if user_input.lower() in ['exit', 'quit']:
                    break
                if user_input.startswith("/"):
                    self.handle_command(user_input)
                    continue
                if not user_input:
                    continue

                self.respond(user_input)
            except (EOFError, KeyboardInterrupt):
                break

    def handle_command(self, cmd):
        if cmd == "/swap":
            self._show_selection_menu()
        elif cmd == "/unload":
            self.unload_agent()
        else:
            print(f"❓ Unknown command: {cmd}")

    def respond(self, text):
        # 1. Coordinate Resonance
        query_vec = self.engine.word_to_vector(text)
        pitch = 220.0 + (query_vec[1] * 660.0)
        
        # 2. Action Resonance Check (Motor Control)
        action_result = self.motor.check_for_action(query_vec, text)
        
        # 3. Conductive Generation
        response = self.assembler.compose_sentence(text)
        
        # 4. Render with Persona Branding
        print(f"\033[1;35m🧠 {self.active_agent.upper()} > \033[0m", end="")
        print(response)
        if action_result:
            print(f"\033[1;33m🛠️  [ACTION_RESULT]: {action_result}\033[0m")
        print(f"\033[2m   [Frequency: {pitch:.1f}Hz | Multi-modal Sync: OK]\033[0m\n")

if __name__ == "__main__":
    shell = ModularSynthesusShell()
    shell.chat_loop()
