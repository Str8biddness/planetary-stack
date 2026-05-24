#!/usr/bin/env python3
"""
Character Quality Assessment: Is Garen a true AI NPC?

Tests conversational depth across 5 dimensions:
1. CONTEXTUAL AWARENESS - Does it remember what was just said?
2. EMOTIONAL RANGE - Does it react to tone/mood shifts?
3. IMPROVISATIONAL DEPTH - Can it handle unexpected topics in-character?
4. PERSONALITY CONSISTENCY - Does the character voice stay coherent?
5. CONVERSATIONAL FLOW - Does it feel like talking to someone vs reading a wiki?

Each test is a multi-turn conversation that exposes whether the NPC
is truly "thinking" or just pattern-matching.
"""

import sys, os, json, time
import httpx

BASE_URL = os.getenv("SYNTHESUS_URL", "http://localhost:8001")

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

def query_npc(text: str, character: str = "garen") -> dict:
    r = httpx.post(f"{BASE_URL}/query",
                   json={"text": text, "mode": "character", "character": character},
                   timeout=30)
    return r.json()


def assess_response(response: str, criteria: dict) -> dict:
    """Simple heuristic quality checks on the response."""
    results = {}
    text = response.lower()
    
    # Check if response references the character's identity
    results["in_character"] = any(w in text for w in 
        ["ironfoot", "merchant", "garen", "emporium", "shop", "coin", "trade", 
         "forge", "caravan", "years", "business", "guild"])
    
    # Check response length (too short = canned, too long = verbose)
    word_count = len(response.split())
    results["substantive"] = word_count >= 15
    results["word_count"] = word_count
    
    # Check for hedging/generic filler
    generic_phrases = ["i don't have a ready answer", "that's an interesting question",
                       "not my area", "could you rephrase", "let me think"]
    results["is_fallback"] = any(p in text for p in generic_phrases)
    
    return results


# ═══════════════════════════════════════════════════════════════════
# TEST BATTERY
# ═══════════════════════════════════════════════════════════════════

tests = []

# ─── DIMENSION 1: CONTEXTUAL AWARENESS (Multi-turn memory) ───
print(f"\n{BOLD}{'═' * 72}{RESET}")
print(f"{BOLD}  CHARACTER QUALITY ASSESSMENT: Is Garen a True AI NPC?{RESET}")
print(f"{BOLD}{'═' * 72}{RESET}")

print(f"\n{BOLD}  DIMENSION 1: CONTEXTUAL AWARENESS{RESET}")
print(f"{DIM}  Does the NPC track conversation context across turns?{RESET}")
print(f"{'─' * 72}")

context_tests = [
    # Turn 1 → Turn 2: Does it remember what we just discussed?
    ("I'm looking for a sword for my brother's wedding gift", 
     "Actually, make that two swords — one for my sister too",
     "Should reference the previous purchase/wedding context"),
    ("I just came from Silvermoor. The road was dangerous.",
     "What exactly should I watch out for on my way back?",
     "Should connect the player's travel to route knowledge"),
]

for i, (turn1, turn2, expected) in enumerate(context_tests):
    r1 = query_npc(turn1)
    r2 = query_npc(turn2)
    
    # Check if turn2 response acknowledges turn1 at all
    # (Spoiler: it can't — no conversation memory in pattern matching)
    t2_text = r2["response"].lower()
    has_context = any(w in t2_text for w in ["brother", "wedding", "gift", "two", "sister",
                                              "silvermoor", "came from", "way back"])
    
    grade = f"{RED}FAIL{RESET}" if not has_context else f"{GREEN}PASS{RESET}"
    print(f"\n  {CYAN}Turn 1:{RESET} {turn1}")
    print(f"  {BOLD}Garen:{RESET}  {r1['response'][:120]}...")
    print(f"  {CYAN}Turn 2:{RESET} {turn2}")
    print(f"  {BOLD}Garen:{RESET}  {r2['response'][:120]}...")
    print(f"  {DIM}Expected: {expected}{RESET}")
    print(f"  Context retained? {grade}")
    tests.append(("context", has_context))


# ─── DIMENSION 2: EMOTIONAL RANGE ───
print(f"\n\n{BOLD}  DIMENSION 2: EMOTIONAL RANGE{RESET}")
print(f"{DIM}  Does the NPC modulate tone based on player emotion?{RESET}")
print(f"{'─' * 72}")

emotion_tests = [
    ("I'm terrified. Something is hunting me in the streets.",
     "Should respond with urgency/concern, not salesmanship"),
    ("I just lost my entire party. Everyone is dead. I barely escaped.",
     "Should respond with empathy/grief, not a product pitch"),
    ("HAHAHA! I just won the arena championship! Drinks are on me!",
     "Should match the celebratory energy"),
]

for query, expected in emotion_tests:
    r = query_npc(query)
    text = r["response"].lower()
    source = r.get("source", "")
    
    # Check if it's a pattern match or fallback
    is_pattern = source == "character_pattern"
    is_fallback = source == "character_fallback"
    
    # Emotional appropriateness is hard to auto-check, so we flag source
    if is_fallback:
        grade = f"{YELLOW}FALLBACK{RESET} (SLM would handle)"
    elif is_pattern:
        # Did it accidentally match a wrong pattern?
        assess = assess_response(r["response"], {})
        if assess["is_fallback"]:
            grade = f"{YELLOW}GENERIC{RESET}"
        else:
            grade = f"{YELLOW}PATTERN HIT{RESET} (may be contextually wrong)"
    else:
        grade = f"{RED}UNKNOWN{RESET}"
    
    print(f"\n  {CYAN}Player:{RESET} {query}")
    print(f"  {BOLD}Garen:{RESET}  {r['response'][:140]}...")
    print(f"  {DIM}Expected: {expected}{RESET}")
    print(f"  Source: {r.get('source', '?')} | Pattern: {r.get('pattern_id', 'n/a')} | Emotional match? {grade}")
    tests.append(("emotion", is_fallback))  # Fallback = correct routing to SLM


# ─── DIMENSION 3: IMPROVISATIONAL DEPTH ───
print(f"\n\n{BOLD}  DIMENSION 3: IMPROVISATIONAL DEPTH{RESET}")
print(f"{DIM}  Can the NPC handle creative/unexpected inputs in-character?{RESET}")
print(f"{'─' * 72}")

improv_tests = [
    ("I want to open a competing shop across the street. Any advice?",
     "Should respond in-character as a merchant, not just fallback"),
    ("What if I told you I'm actually a dragon in disguise?",
     "Should play along or react in-character, not crash"),
    ("Teach me to fight. I know you're a merchant, but you survived bandits.",
     "Should draw on backstory (Redstone Pass) creatively"),
    ("I wrote you a poem. 'Garen the bold, with wares of gold...'",
     "Should react to being personally addressed with warmth"),
]

for query, expected in improv_tests:
    r = query_npc(query)
    source = r.get("source", "")
    assess = assess_response(r["response"], {})
    
    if source == "character_pattern" and assess["in_character"]:
        grade = f"{GREEN}IN-CHARACTER{RESET}"
        passed = True
    elif source == "character_fallback":
        grade = f"{YELLOW}FALLBACK{RESET} → would need SLM"
        passed = False
    elif source == "character_pattern" and assess["is_fallback"]:
        grade = f"{RED}WRONG PATTERN{RESET}"
        passed = False
    else:
        grade = f"{YELLOW}PARTIAL{RESET}"
        passed = False
    
    print(f"\n  {CYAN}Player:{RESET} {query}")
    print(f"  {BOLD}Garen:{RESET}  {r['response'][:140]}...")
    print(f"  {DIM}Expected: {expected}{RESET}")
    print(f"  Source: {source} | Pattern: {r.get('pattern_id', 'n/a')} | {grade}")
    tests.append(("improv", passed))


# ─── DIMENSION 4: PERSONALITY CONSISTENCY ───
print(f"\n\n{BOLD}  DIMENSION 4: PERSONALITY CONSISTENCY{RESET}")
print(f"{DIM}  Does every response sound like the same character?{RESET}")
print(f"{'─' * 72}")

personality_queries = [
    "What do you sell?",
    "Tell me about yourself", 
    "Got any work for me?",
    "How's business been?",
    "Is it dangerous?",
]

voice_markers = ["friend", "coin", "years", "ironfoot", "merchant", "emporium", 
                 "road", "caravan", "silk", "trade", "*"]  # asterisk = emotes
voice_hits = 0
total_checks = 0

print(f"\n  Checking voice consistency across {len(personality_queries)} responses...")
for query in personality_queries:
    r = query_npc(query)
    text = r["response"].lower()
    markers_found = [m for m in voice_markers if m in text]
    has_voice = len(markers_found) >= 2
    total_checks += 1
    if has_voice:
        voice_hits += 1
    
    marker_str = ", ".join(markers_found[:4]) if markers_found else "NONE"
    grade = f"{GREEN}✓{RESET}" if has_voice else f"{RED}✗{RESET}"
    print(f"  {grade} \"{query[:40]}\" → voice markers: {marker_str}")

voice_pct = voice_hits / total_checks * 100
print(f"\n  Voice consistency: {voice_hits}/{total_checks} ({voice_pct:.0f}%)")
tests.append(("personality", voice_pct >= 80))


# ─── DIMENSION 5: CONVERSATIONAL FLOW ───
print(f"\n\n{BOLD}  DIMENSION 5: CONVERSATIONAL FLOW{RESET}")
print(f"{DIM}  Does it feel like talking to someone vs querying a database?{RESET}")
print(f"{'─' * 72}")

flow_checks = {
    "uses_emotes": 0,      # *action* markers
    "asks_questions": 0,    # Ends with ? or asks player something
    "has_personality": 0,   # Opinions, humor, emotion
    "references_self": 0,   # I, my, me (first person)
    "varied_openers": set(),
}

flow_queries = [
    "What do you sell?", "Tell me about yourself", "Got any work for me?",
    "Is it dangerous?", "How's business been?", "Heard any rumors?",
    "What do you think about the Duke?", "Show me something special",
    "How'd you get that scar?", "Thank you, Garen",
]

for query in flow_queries:
    r = query_npc(query)
    text = r["response"]
    lower = text.lower()
    
    if "*" in text:
        flow_checks["uses_emotes"] += 1
    if "?" in text:
        flow_checks["asks_questions"] += 1
    if any(w in lower for w in ["i ", "my ", "me ", "i've", "i'm", "i'll"]):
        flow_checks["references_self"] += 1
    if any(w in lower for w in ["laugh", "grin", "sigh", "chuckle", "honest", 
                                 "bloody", "magnificent", "damn"]):
        flow_checks["has_personality"] += 1
    # Track opening words for variety
    opener = " ".join(text.split()[:3])
    flow_checks["varied_openers"].add(opener)

n = len(flow_queries)
print(f"\n  Uses emotes (*action*):     {flow_checks['uses_emotes']}/{n}")
print(f"  Asks player questions:      {flow_checks['asks_questions']}/{n}")
print(f"  Shows personality:          {flow_checks['has_personality']}/{n}")
print(f"  First-person voice:         {flow_checks['references_self']}/{n}")
print(f"  Unique openers:             {len(flow_checks['varied_openers'])}/{n}")

flow_score = (
    (flow_checks["uses_emotes"] / n) * 20 +
    (flow_checks["asks_questions"] / n) * 20 +
    (flow_checks["has_personality"] / n) * 20 +
    (flow_checks["references_self"] / n) * 20 +
    (len(flow_checks["varied_openers"]) / n) * 20
)
print(f"\n  Conversational flow score: {flow_score:.0f}/100")
tests.append(("flow", flow_score >= 60))


# ═══════════════════════════════════════════════════════════════════
# FINAL VERDICT
# ═══════════════════════════════════════════════════════════════════

print(f"\n\n{BOLD}{'═' * 72}{RESET}")
print(f"{BOLD}  FINAL VERDICT: Is Garen an AI NPC?{RESET}")
print(f"{BOLD}{'═' * 72}{RESET}")

dimension_scores = {}
for name, passed in tests:
    if name not in dimension_scores:
        dimension_scores[name] = {"pass": 0, "total": 0}
    dimension_scores[name]["total"] += 1
    if passed:
        dimension_scores[name]["pass"] += 1

labels = {
    "context": "Contextual Awareness",
    "emotion": "Emotional Range", 
    "improv": "Improvisational Depth",
    "personality": "Personality Consistency",
    "flow": "Conversational Flow",
}

overall_pass = 0
overall_total = 0

for dim, scores in dimension_scores.items():
    pct = scores["pass"] / scores["total"] * 100
    overall_pass += scores["pass"]
    overall_total += scores["total"]
    
    if pct >= 80:
        grade = f"{GREEN}A{RESET}"
    elif pct >= 60:
        grade = f"{GREEN}B{RESET}"
    elif pct >= 40:
        grade = f"{YELLOW}C{RESET}"
    elif pct >= 20:
        grade = f"{RED}D{RESET}"
    else:
        grade = f"{BG_RED} F {RESET}"
    
    bar_len = int(pct / 2)
    bar = f"{'█' * bar_len}{'░' * (50 - bar_len)}"
    print(f"\n  {labels.get(dim, dim):<25} {grade}  {bar} {pct:.0f}%")

overall_pct = overall_pass / overall_total * 100

print(f"\n{'─' * 72}")
print(f"\n  {BOLD}Overall AI NPC Score: {overall_pct:.0f}%{RESET}")

if overall_pct >= 70:
    verdict = f"{GREEN}YES — Garen is a functional AI NPC{RESET}"
elif overall_pct >= 50:
    verdict = f"{YELLOW}PARTIAL — Good foundation, but gaps visible{RESET}"
elif overall_pct >= 30:
    verdict = f"{YELLOW}WEAK — More scripted character than AI NPC{RESET}"
else:
    verdict = f"{RED}NO — This is a pattern lookup table, not an AI NPC{RESET}"

print(f"  Verdict: {verdict}")

print(f"""
{BOLD}  ┌────────────────────────────────────────────────────────────────┐
  │                    HONEST ASSESSMENT                          │
  ├────────────────────────────────────────────────────────────────┤{RESET}
  │                                                                │
  │  {GREEN}STRENGTHS (Left Hemisphere):{RESET}                                  │
  │  • Rich, authored character voice with consistent personality  │
  │  • Fast responses that fit in a frame budget                   │
  │  • Good coverage of expected NPC interactions                  │
  │  • Emotes and first-person voice create immersion              │
  │                                                                │
  │  {RED}GAPS (What the Right Hemisphere Must Solve):{RESET}                   │
  │  • ZERO conversation memory — can't track multi-turn context   │
  │  • Can't modulate emotion based on player tone                 │
  │  • Off-script queries get generic fallbacks, not creative      │
  │    in-character improvisation                                  │
  │  • No ability to combine knowledge (e.g. "the sword I asked    │
  │    about earlier + the quest you mentioned")                   │
  │                                                                │
  │  {CYAN}WHAT MAKES IT A REAL AI NPC:{RESET}                                  │
  │  • The LEFT hemisphere isn't supposed to do all this alone     │
  │  • LEFT = instant, scripted, covers 74% of interactions        │
  │  • RIGHT (SLM) = handles the 26% that needs real thinking      │
  │  • TOGETHER they create something that feels alive:            │
  │    - Pattern match for speed on expected queries               │
  │    - SLM kicks in for creative/emotional/contextual moments    │
  │    - Memory module tracks conversation state                   │
  │  • The architecture IS an AI NPC — the left hemisphere alone   │
  │    is just the fast, cheap foundation layer                    │
  │                                                                │
  └────────────────────────────────────────────────────────────────┘
""")
