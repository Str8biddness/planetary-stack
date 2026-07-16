#!/usr/bin/env python3
"""
NPC Scaling Architecture Simulator

Answers the question: "How do we run 100 NPCs with dual-hemisphere 
architecture on a PS5 / gaming PC WITHOUT 100 independent SLMs?"

Simulates three architectures:
  A) Naive: 100 independent SLMs (impossible)
  B) Shared SLM Queue: 1 SLM instance, shared inference queue
  C) Synthesus Optimal: 1 SLM + left-hemisphere priority routing

Models realistic player interaction patterns, SLM queuing theory,
and shows why Architecture C works on consumer hardware.
"""

import json, math, random, time
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
MAGENTA = "\033[95m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"
BG_RED  = "\033[41m"
BG_GREEN = "\033[42m"
BG_CYAN = "\033[46m"

# ═══════════════════════════════════════════════════════════════════
# HARDWARE TARGETS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class HardwareTarget:
    name: str
    gpu: str
    vram_mb: int
    slm_tok_per_sec: float
    cpu_cores: int
    ram_gb: int
    
    # Derived
    slm_vram_mb: int = 450          # Qwen3-0.6B Q4
    slm_response_tokens: int = 60
    
    @property
    def slm_response_ms(self) -> float:
        return (self.slm_response_tokens / self.slm_tok_per_sec) * 1000
    
    @property
    def slm_qps(self) -> float:
        return 1000 / self.slm_response_ms
    
    @property
    def max_slm_instances(self) -> int:
        """How many SLM copies fit in VRAM."""
        return self.vram_mb // self.slm_vram_mb


TARGETS = [
    HardwareTarget("PS5", "AMD Oberon (RDNA2)", 16384, 90, 8, 16),
    HardwareTarget("RTX 3060 PC", "RTX 3060 12GB", 12288, 85, 8, 16),
    HardwareTarget("RTX 4070 PC", "RTX 4070 12GB", 12288, 130, 8, 32),
    HardwareTarget("Steam Deck", "AMD APU (RDNA2)", 4096, 25, 4, 16),
]


# ═══════════════════════════════════════════════════════════════════
# PLAYER INTERACTION MODEL
# ═══════════════════════════════════════════════════════════════════

@dataclass
class InteractionModel:
    """Models realistic NPC conversation patterns in a game."""
    
    total_npcs: int = 100
    
    # Not all NPCs are in conversation simultaneously
    # In a typical RPG: player talks to 1 NPC, maybe 2 companions chime in
    # In a town with 100 NPCs, maybe 3-5 are actively being conversed with
    active_conversation_pct: float = 0.05   # 5% actively talking at any time
    
    # Within an active conversation: ~1 query every 4 seconds (player reads, types)
    query_interval_sec: float = 4.0
    
    # Ambient NPC-to-NPC chatter (optional, lower priority)
    ambient_chatter_pct: float = 0.02      # 2% doing ambient dialogue
    ambient_interval_sec: float = 10.0      # Slower pace for ambient
    
    # Left hemisphere coverage
    left_hemisphere_pct: float = 0.74       # From our simulation
    
    @property
    def active_npcs(self) -> int:
        return max(1, int(self.total_npcs * self.active_conversation_pct))
    
    @property 
    def ambient_npcs(self) -> int:
        return int(self.total_npcs * self.ambient_chatter_pct)
    
    @property
    def total_qps(self) -> float:
        """Total queries per second across all active NPCs."""
        active_qps = self.active_npcs / self.query_interval_sec
        ambient_qps = self.ambient_npcs / self.ambient_interval_sec
        return active_qps + ambient_qps
    
    @property
    def slm_qps_needed(self) -> float:
        """SLM queries per second (right hemisphere only)."""
        return self.total_qps * (1.0 - self.left_hemisphere_pct)
    
    @property
    def left_qps_needed(self) -> float:
        return self.total_qps * self.left_hemisphere_pct


# ═══════════════════════════════════════════════════════════════════
# QUEUING MODEL
# ═══════════════════════════════════════════════════════════════════

def mm1_queue_wait(arrival_rate: float, service_rate: float) -> float:
    """M/M/1 queue average wait time (ms). Returns inf if overloaded."""
    if arrival_rate >= service_rate:
        return float('inf')
    utilization = arrival_rate / service_rate
    # Average time in system = 1 / (service_rate - arrival_rate)
    avg_system_time = 1.0 / (service_rate - arrival_rate)
    return avg_system_time * 1000  # convert to ms

def mmc_queue_wait(arrival_rate: float, service_rate_per_server: float, c: int) -> float:
    """M/M/c queue average wait time (ms). c = number of parallel SLM instances."""
    if c == 0:
        return float('inf')
    total_service = service_rate_per_server * c
    if arrival_rate >= total_service:
        return float('inf')
    rho = arrival_rate / total_service  # utilization per server
    
    # Erlang-C formula (simplified)
    a = arrival_rate / service_rate_per_server  # offered load
    
    # P(wait) using Erlang-C
    sum_terms = sum((a ** n) / math.factorial(n) for n in range(c))
    last_term = (a ** c) / (math.factorial(c) * (1 - rho))
    pw = last_term / (sum_terms + last_term)
    
    # Average wait time
    avg_wait = pw / (c * service_rate_per_server - arrival_rate)
    return avg_wait * 1000


# ═══════════════════════════════════════════════════════════════════
# MAIN SIMULATION
# ═══════════════════════════════════════════════════════════════════

def main():
    print(f"\n{BOLD}{'═' * 76}{RESET}")
    print(f"{BOLD}  SCALING 100 NPCs: SHARED SLM ARCHITECTURE ANALYSIS{RESET}")
    print(f"{BOLD}  \"Do we need 100 independent SLMs?\" — No. Here's why.{RESET}")
    print(f"{BOLD}{'═' * 76}{RESET}")

    # ─── KEY INSIGHT ───
    print(f"""
{BOLD}  THE KEY INSIGHT: Not all NPCs talk at once.{RESET}

  In a game with 100 NPCs in a town:
  • The player is talking to {CYAN}1-2 NPCs{RESET} at any given moment
  • Maybe {CYAN}2-3 companion NPCs{RESET} react to what's happening
  • That's {BOLD}5 active conversations max{RESET}, not 100
  • Of those 5, {GREEN}74% of queries hit the left hemisphere{RESET} (instant)
  • Only {RED}26% need the SLM{RESET} — that's ~0.3 SLM queries/sec

  You don't need 100 SLMs. You need {BOLD}one SLM with a queue.{RESET}
""")

    # ─── ARCHITECTURE COMPARISON ───
    print(f"{BOLD}{'═' * 76}{RESET}")
    print(f"{BOLD}  ARCHITECTURE A: 100 Independent SLMs (Naive){RESET}")
    print(f"{BOLD}{'═' * 76}{RESET}")
    
    for hw in TARGETS:
        instances = hw.max_slm_instances
        needed = 100
        vram_needed = needed * hw.slm_vram_mb
        print(f"  {hw.name:<16} VRAM: {hw.vram_mb}MB | SLMs that fit: {instances} | Need: 100 | "
              f"{RED}IMPOSSIBLE — need {vram_needed/1024:.0f}GB VRAM{RESET}")
    
    print(f"\n  {BG_RED}{BOLD} VERDICT: Architecture A is physically impossible on any consumer hardware {RESET}")

    # ─── SHARED QUEUE ARCHITECTURE ───
    print(f"\n{BOLD}{'═' * 76}{RESET}")
    print(f"{BOLD}  ARCHITECTURE B: Shared SLM Queue (1 model, all NPCs share it){RESET}")
    print(f"{BOLD}{'═' * 76}{RESET}")
    
    print(f"""
  {BOLD}How it works:{RESET}
  ┌────────────────────────────────────────────────────────────┐
  │  100 NPCs, each with their own LEFT hemisphere (patterns)  │
  │  All share ONE right hemisphere SLM instance                │
  │                                                             │
  │  NPC query → Left hemisphere (pattern match, ~10ms)         │
  │           → If conf < threshold:                            │
  │              → Push to SLM QUEUE with character context      │
  │              → SLM processes requests in FIFO order          │
  │              → Response delivered async (speech bubble delay) │
  └────────────────────────────────────────────────────────────┘

  The SLM doesn't need to know which NPC it's speaking as.
  It receives: [character_bio + conversation_history + query]
  It returns:  [in-character response]

  One model, {BOLD}100 different personalities{RESET} — just different prompts.
""")

    interaction = InteractionModel(total_npcs=100)
    
    print(f"  {BOLD}Interaction Model:{RESET}")
    print(f"  • 100 NPCs in world, {interaction.active_npcs} actively talking ({interaction.active_conversation_pct*100:.0f}%)")
    print(f"  • {interaction.ambient_npcs} doing ambient chatter")
    print(f"  • Total queries/sec: {interaction.total_qps:.2f}")
    print(f"  • Left hemisphere handles: {interaction.left_qps_needed:.2f} QPS (instant)")
    print(f"  • SLM queue receives: {interaction.slm_qps_needed:.2f} QPS")
    
    print(f"\n  {BOLD}{'─' * 72}{RESET}")
    print(f"  {BOLD}{'Hardware':<16} │ {'SLM Speed':>10} │ {'SLM QPS':>8} │ {'Queue Wait':>11} │ {'Total Resp':>11} │ Status{RESET}")
    print(f"  {BOLD}{'─' * 72}{RESET}")
    
    for hw in TARGETS:
        slm_resp = hw.slm_response_ms
        slm_qps = hw.slm_qps
        
        if interaction.slm_qps_needed < slm_qps:
            queue_wait = mm1_queue_wait(interaction.slm_qps_needed, slm_qps)
            total_resp = slm_resp + queue_wait
            
            if queue_wait < 500:
                status = f"{GREEN}✓ Smooth{RESET}"
            elif queue_wait < 2000:
                status = f"{YELLOW}~ Playable{RESET}"
            else:
                status = f"{RED}! Laggy{RESET}"
            
            print(f"  {hw.name:<16} │ {slm_resp:>8.0f}ms │ {slm_qps:>7.2f} │ {queue_wait:>9.0f}ms │ {total_resp:>9.0f}ms │ {status}")
        else:
            print(f"  {hw.name:<16} │ {slm_resp:>8.0f}ms │ {slm_qps:>7.2f} │ {'∞':>9} │ {'∞':>9} │ {BG_RED} OVERLOADED {RESET}")

    # ─── OPTIMAL ARCHITECTURE ───
    print(f"\n{BOLD}{'═' * 76}{RESET}")
    print(f"{BOLD}  ARCHITECTURE C: Synthesus Optimal (Left-First + Shared SLM + Smart Queue){RESET}")
    print(f"{BOLD}{'═' * 76}{RESET}")
    
    print(f"""
  {BOLD}Additional optimizations over Architecture B:{RESET}

  {GREEN}1. PRIORITY QUEUING{RESET}
     Player-facing NPCs get priority. Ambient chatter is lowest.
     Player asks merchant a question → immediate SLM priority
     Two NPCs gossiping in background → can wait 5+ seconds

  {GREEN}2. SPECULATIVE LEFT-HEMISPHERE RESPONSE{RESET}
     While SLM processes, show a LEFT hemisphere "stall" response:
     "Hmm, let me think about that..." (pattern-matched, instant)
     Then swap in the SLM response when ready (async update)
     Player sees the NPC "thinking" — feels natural, not broken.

  {GREEN}3. SLM RESPONSE CACHING{RESET}
     Similar off-script queries get cached SLM responses.
     "What do you think about dragons?" asked to 3 different NPCs →
     First NPC: full SLM inference (700ms)
     NPCs 2-3: cached template + character voice overlay (~50ms)

  {GREEN}4. BATCH INFERENCE{RESET}
     Queue 2-4 SLM requests and batch them. Modern SLMs can
     process multiple prompts with ~40% overhead instead of 400%.
     4 requests at once: 4x700ms = 2800ms serial → ~1000ms batched

  {GREEN}5. CONVERSATION COOLDOWN{RESET}
     After an SLM response, the NPC has a 2-3 sec "thinking cooldown"
     before accepting another off-script query. During cooldown,
     left hemisphere handles everything. This naturally rate-limits
     SLM demand without the player noticing.
""")

    # Model Architecture C with optimizations
    print(f"  {BOLD}Architecture C Performance Model:{RESET}")
    print(f"  {BOLD}{'─' * 72}{RESET}")
    
    # With caching: ~30% of SLM queries hit cache
    cache_hit_rate = 0.30
    # With cooldown: reduces effective SLM demand by ~20%
    cooldown_reduction = 0.20
    # Batch efficiency: 2x throughput with batching
    batch_multiplier = 2.0
    
    effective_slm_qps = interaction.slm_qps_needed * (1 - cache_hit_rate) * (1 - cooldown_reduction)
    
    print(f"  Raw SLM demand:          {interaction.slm_qps_needed:.3f} QPS")
    print(f"  After cache (30% hit):   {interaction.slm_qps_needed * (1 - cache_hit_rate):.3f} QPS")
    print(f"  After cooldown (-20%):   {effective_slm_qps:.3f} QPS")
    print(f"  Batch throughput boost:   {batch_multiplier:.0f}x effective SLM capacity")
    
    print(f"\n  {BOLD}{'Hardware':<16} │ {'Eff. SLM QPS':>13} │ {'Eff. Capacity':>14} │ {'Queue Wait':>11} │ Status{RESET}")
    print(f"  {BOLD}{'─' * 72}{RESET}")
    
    for hw in TARGETS:
        slm_resp = hw.slm_response_ms
        effective_capacity = hw.slm_qps * batch_multiplier
        
        if effective_slm_qps < effective_capacity:
            queue_wait = mm1_queue_wait(effective_slm_qps, effective_capacity)
            total = slm_resp + queue_wait
            
            if queue_wait < 200:
                status = f"{BG_GREEN}{BOLD} EXCELLENT {RESET}"
            elif queue_wait < 500:
                status = f"{GREEN}✓ Smooth{RESET}"
            elif queue_wait < 2000:
                status = f"{YELLOW}~ Playable{RESET}"
            else:
                status = f"{RED}! Laggy{RESET}"
            
            print(f"  {hw.name:<16} │ {effective_slm_qps:>11.3f}   │ {effective_capacity:>12.2f}   │ {queue_wait:>9.0f}ms │ {status}")
        else:
            print(f"  {hw.name:<16} │ {effective_slm_qps:>11.3f}   │ {effective_capacity:>12.2f}   │ {'∞':>9} │ {BG_RED} OVERLOADED {RESET}")

    # ─── VRAM BUDGET ───
    print(f"\n{BOLD}{'═' * 76}{RESET}")
    print(f"{BOLD}  VRAM / MEMORY BUDGET — 100 NPCs{RESET}")
    print(f"{BOLD}{'═' * 76}{RESET}")
    
    slm_vram = 450
    pattern_per_npc = 2  # ~2MB per NPC pattern table (30 patterns)
    total_pattern_mb = 100 * pattern_per_npc
    conversation_mem_per_npc = 0.1  # ~100KB per active conversation buffer
    total_conv_mb = 100 * conversation_mem_per_npc
    
    print(f"""
  ┌───────────────────────────────────────────────────────────────────┐
  │ Component                    │ Count │ Per Unit │ Total           │
  ├───────────────────────────────────────────────────────────────────┤
  │ SLM (Qwen3-0.6B Q4)         │   {GREEN}1{RESET}   │  450 MB  │ {GREEN}  450 MB (VRAM){RESET} │
  │ Left hemisphere patterns     │ 100   │    2 MB  │ {GREEN}  200 MB (RAM){RESET}  │
  │ Conversation memory buffers  │ 100   │  0.1 MB  │ {GREEN}   10 MB (RAM){RESET}  │
  │ Character bios + config      │ 100   │  0.05MB  │ {GREEN}    5 MB (RAM){RESET}  │
  │ SLM KV-cache (active ctx)    │   1   │  128 MB  │ {GREEN}  128 MB (VRAM){RESET} │
  ├───────────────────────────────────────────────────────────────────┤
  │ {BOLD}TOTAL                                          │ ~578 MB VRAM{RESET}   │
  │ {BOLD}                                               │ ~215 MB RAM{RESET}    │
  └───────────────────────────────────────────────────────────────────┘
""")
    
    print(f"  {BOLD}VRAM comparison:{RESET}")
    for hw in TARGETS:
        used = 578
        remaining = hw.vram_mb - used
        pct_used = used / hw.vram_mb * 100
        bar_len = int(pct_used / 2)
        bar = f"{YELLOW}{'█' * bar_len}{RESET}{'░' * (50 - bar_len)}"
        print(f"  {hw.name:<16} [{bar}] {pct_used:.0f}% ({remaining}MB free for rendering)")

    # ─── NPC SCALING CURVES ───
    print(f"\n{BOLD}{'═' * 76}{RESET}")
    print(f"{BOLD}  HOW MANY NPCs AT DIFFERENT LEFT-HEMISPHERE RATIOS?{RESET}")
    print(f"{BOLD}  (PS5 hardware, Architecture C optimizations){RESET}")
    print(f"{BOLD}{'═' * 76}{RESET}")
    
    ps5 = TARGETS[0]
    
    print(f"\n  {BOLD}{'Left %':>8} │ {'Right %':>8} │ {'Max NPCs':>10} │ {'SLM Wait':>10} │ Status{RESET}")
    print(f"  {BOLD}{'─' * 65}{RESET}")
    
    for left_pct in [0.50, 0.60, 0.70, 0.74, 0.80, 0.85, 0.90, 0.95, 0.99]:
        right_pct = 1.0 - left_pct
        
        # Find max NPCs where queue wait < 2000ms
        max_npcs = 0
        for n in range(10, 2001, 10):
            active = max(1, int(n * 0.05))
            ambient = int(n * 0.02)
            total_qps = active / 4.0 + ambient / 10.0
            slm_demand = total_qps * right_pct * (1 - cache_hit_rate) * (1 - cooldown_reduction)
            capacity = ps5.slm_qps * batch_multiplier
            
            if slm_demand < capacity:
                wait = mm1_queue_wait(slm_demand, capacity)
                if wait < 2000:
                    max_npcs = n
                else:
                    break
            else:
                break
        
        if max_npcs >= 500:
            status = f"{BG_GREEN}{BOLD} MASSIVE SCALE {RESET}"
        elif max_npcs >= 200:
            status = f"{GREEN}✓ Open world{RESET}"
        elif max_npcs >= 100:
            status = f"{GREEN}✓ Large town{RESET}"
        elif max_npcs >= 50:
            status = f"{YELLOW}~ Medium area{RESET}"
        else:
            status = f"{RED}! Limited{RESET}"
        
        marker = " ← YOU ARE HERE" if left_pct == 0.74 else ""
        print(f"  {left_pct*100:>7.0f}% │ {right_pct*100:>7.0f}% │ {max_npcs:>10} │ {'< 2s':>10} │ {status}{BOLD}{marker}{RESET}")

    print(f"  {BOLD}{'─' * 65}{RESET}")

    # ─── FINAL ARCHITECTURE DIAGRAM ───
    print(f"""
{BOLD}{'═' * 76}{RESET}
{BOLD}  FINAL ANSWER: The 100-NPC Architecture{RESET}
{BOLD}{'═' * 76}{RESET}

  ┌─────────────────────────────────────────────────────────────────────────┐
  │                         GAME ENGINE (60 FPS)                           │
  │                                                                        │
  │   NPC 1    NPC 2    NPC 3   ...   NPC 100                             │
  │   ┌───┐    ┌───┐    ┌───┐         ┌───┐                               │
  │   │{GREEN}L{RESET} {GREEN}H{RESET}│    │{GREEN}L{RESET} {GREEN}H{RESET}│    │{GREEN}L{RESET} {GREEN}H{RESET}│         │{GREEN}L{RESET} {GREEN}H{RESET}│  ← 100 LEFT hemispheres    │
  │   │{GREEN}pat{RESET}│    │{GREEN}pat{RESET}│    │{GREEN}pat{RESET}│         │{GREEN}pat{RESET}│    (pattern tables, ~2MB each) │
  │   └─┬─┘    └─┬─┘    └─┬─┘         └─┬─┘                              │
  │     │        │        │              │                                 │
  │     │   conf < 0.65?  Escalate!      │                                 │
  │     │        │        │              │                                 │
  │     └────────┴────────┴──────────────┘                                 │
  │                       │                                                │
  │              ┌────────▼────────┐                                       │
  │              │  {RED}SLM QUEUE{RESET}        │  ← Priority queue (player > ambient) │
  │              │  [bio + ctx + q] │  ← Each request carries NPC context  │
  │              └────────┬────────┘                                       │
  │                       │                                                │
  │              ┌────────▼────────┐                                       │
  │              │  {BOLD}{RED}ONE SLM{RESET}          │  ← Qwen3-0.6B Q4 (450MB VRAM)      │
  │              │  {RED}Qwen3-0.6B{RESET}      │  ← Processes requests sequentially    │
  │              │  {RED}(shared){RESET}         │  ← Different NPC = different prompt   │
  │              └────────┬────────┘                                       │
  │                       │                                                │
  │              ┌────────▼────────┐                                       │
  │              │  Response Cache  │  ← Similar queries skip inference    │
  │              └─────────────────┘                                       │
  └─────────────────────────────────────────────────────────────────────────┘

  {BOLD}Total VRAM: ~578MB{RESET}   |   {BOLD}Total RAM: ~215MB{RESET}   |   {BOLD}SLM instances: 1{RESET}

  The SLM is a {BOLD}shared service{RESET}, not a per-NPC resource.
  It's the same model answering as 100 different characters —
  the {BOLD}character personality comes from the prompt, not the weights.{RESET}
""")

if __name__ == "__main__":
    main()
