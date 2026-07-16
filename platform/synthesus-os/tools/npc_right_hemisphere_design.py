#!/usr/bin/env python3
"""
NPC Right Hemisphere Design: The Cognitive Engine

What replaces the SLM inside the NPC brain?
A lightweight, zero-inference cognitive engine that gives NPCs
the ILLUSION of intelligence through deterministic algorithms.

The SLM still exists — but as a separate Thinking Layer service.
This is what the NPC can do ENTIRELY ON ITS OWN.
"""

CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
MAGENTA = "\033[95m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"
BG_GREEN = "\033[42m"
BG_CYAN  = "\033[46m"

def main():
    print(f"""
{BOLD}{'═' * 76}{RESET}
{BOLD}  THE NPC RIGHT HEMISPHERE: A Cognitive Engine (No SLM Required){RESET}
{BOLD}{'═' * 76}{RESET}

  The question: What pairs with the left hemisphere (patterns) to create
  a character that feels alive WITHOUT calling the SLM?

  The answer: {BOLD}Six lightweight cognitive modules{RESET} that run in <1ms each,
  use zero GPU, and give the NPC genuine behavioral intelligence.

{BOLD}{'═' * 76}{RESET}
{BOLD}  THE SIX MODULES{RESET}
{BOLD}{'═' * 76}{RESET}

{BOLD}  ┌─────────────────────────────────────────────────────────────────────┐{RESET}
{BOLD}  │                    NPC BRAIN (self-contained)                       │{RESET}
{BOLD}  │                                                                     │{RESET}
{BOLD}  │   LEFT HEMISPHERE          │    RIGHT HEMISPHERE                    │{RESET}
{BOLD}  │   (what it knows)          │    (how it thinks)                     │{RESET}
{BOLD}  │                            │                                        │{RESET}
{BOLD}  │   ┌──────────────────┐     │    ┌──────────────────────────────┐   │{RESET}
{BOLD}  │   │{GREEN} Pattern Matcher  {RESET}{BOLD}│     │    │{CYAN} 1. Conversation Tracker    {RESET}{BOLD}│   │{RESET}
{BOLD}  │   │{GREEN} (PPBRS)          {RESET}{BOLD}│     │    │{CYAN} 2. Emotion State Machine   {RESET}{BOLD}│   │{RESET}
{BOLD}  │   │{GREEN}                  {RESET}{BOLD}│     │    │{CYAN} 3. Response Compositor     {RESET}{BOLD}│   │{RESET}
{BOLD}  │   │{GREEN} 30-200 patterns  {RESET}{BOLD}│     │    │{CYAN} 4. Relationship Tracker    {RESET}{BOLD}│   │{RESET}
{BOLD}  │   │{GREEN} per character    {RESET}{BOLD}│     │    │{CYAN} 5. World State Reactor     {RESET}{BOLD}│   │{RESET}
{BOLD}  │   │{GREEN}                  {RESET}{BOLD}│     │    │{CYAN} 6. Escalation Gate         {RESET}{BOLD}│   │{RESET}
{BOLD}  │   └──────────────────┘     │    └──────────────────────────────┘   │{RESET}
{BOLD}  │                            │                                        │{RESET}
{BOLD}  └─────────────────────────────────────────────────────────────────────┘{RESET}
{BOLD}          │                                      │{RESET}
{BOLD}          │  Can't handle it?                     │{RESET}
{BOLD}          └──────────────┬───────────────────────┘{RESET}
{BOLD}                         ▼{RESET}
{BOLD}              ┌─────────────────────┐{RESET}
{BOLD}              │  {RED}THINKING LAYER{RESET}{BOLD}       │  ← External SLM service{RESET}
{BOLD}              │  {RED}(shared, optional){RESET}{BOLD}   │  ← Only for truly novel queries{RESET}
{BOLD}              └─────────────────────┘{RESET}


{BOLD}{'═' * 76}{RESET}
{BOLD}  MODULE 1: CONVERSATION TRACKER{RESET}
{DIM}  "What did we just talk about?"{RESET}
{BOLD}{'═' * 76}{RESET}

  {BOLD}What it does:{RESET}
  Maintains a rolling context window of the current conversation.
  Tracks: last 5 player messages, last 5 NPC responses, active topic,
  mentioned entities (items, people, places), and open questions.

  {BOLD}How it works (no inference):{RESET}
  • Keyword extraction from each player message (same stop-word filter)
  • Topic detection: match keywords against domain categories
    "sword" + "buy" → topic=SHOPPING
    "caravan" + "missing" → topic=QUEST
    "scar" + "story" → topic=BACKSTORY
  • Entity tracking: named entity list from patterns + bio
    Player says "Tomás" → entity=TOMAS tagged as KNOWN_NPC
  • Pronoun resolution: "it" / "that" → last mentioned entity

  {BOLD}What it enables:{RESET}
  Player: "I need a sword"
  Garen: [pattern match → sword response]
  Player: "Actually, make that two"
  {GREEN}→ Tracker knows topic=SHOPPING, last_item=SWORD
  → Modifies response: "Two Dwarven longswords? That'll be 240 gold."{RESET}

  {BOLD}Cost:{RESET} ~0.1ms per query, ~500 bytes RAM per conversation
  {BOLD}Intelligence gained:{RESET} Multi-turn context without any inference


{BOLD}{'═' * 76}{RESET}
{BOLD}  MODULE 2: EMOTION STATE MACHINE{RESET}
{DIM}  "How is the NPC feeling right now?"{RESET}
{BOLD}{'═' * 76}{RESET}

  {BOLD}What it does:{RESET}
  Tracks the NPC's emotional state as a finite state machine.
  States: NEUTRAL → FRIENDLY → EXCITED → SUSPICIOUS → ANGRY → AFRAID
  Transitions are triggered by keyword/topic detection in player input.

  {BOLD}How it works:{RESET}
  • Each state has a set of trigger words/patterns that move to another state
  • Emotional decay: states drift back toward baseline over time
  • Each state modifies response DELIVERY, not content:
    NEUTRAL:    "I carry swords. 120 gold."
    FRIENDLY:   "For you? I carry the finest swords. 120 gold, friend."
    SUSPICIOUS: "...Swords? What do you need a sword for? 120 gold. Cash."
    AFRAID:     "S-swords? Y-yes, I have some... 120 gold. Please."

  {BOLD}Implementation:{RESET}
  ┌──────────┐  player_threat  ┌──────────┐  continued_threat  ┌────────┐
  │ NEUTRAL  │───────────────→│SUSPICIOUS│───────────────────→│ AFRAID │
  └────┬─────┘                └──────────┘                    └────────┘
       │ player_kind                │ player_apologize
       ▼                            ▼
  ┌──────────┐                ┌──────────┐
  │ FRIENDLY │                │ NEUTRAL  │
  └──────────┘                └──────────┘

  {BOLD}Emotion modifiers are templates, not generation:{RESET}
  Each pattern response has optional emotion variants:
    "response_template": "I carry swords. 120 gold.",
    "emotion_variants": {{
      "friendly": "For you? Best swords in town. 120 gold, friend.",
      "afraid": "S-swords? Y-yes, I have some... 120 gold. Please."
    }}

  {BOLD}Cost:{RESET} ~0.05ms per query, 1 byte per NPC (current state enum)
  {BOLD}Intelligence gained:{RESET} NPCs react to player tone. Feels alive.


{BOLD}{'═' * 76}{RESET}
{BOLD}  MODULE 3: RESPONSE COMPOSITOR{RESET}
{DIM}  "Building responses from parts instead of lookup"{RESET}
{BOLD}{'═' * 76}{RESET}

  {BOLD}What it does:{RESET}
  Instead of returning a single static template, assembles responses
  from modular PARTS based on context. This is the key to making
  30 patterns feel like 300.

  {BOLD}How it works:{RESET}
  A response template becomes a COMPOSITE:
  {{
    "id": "SP_GAREN_002",
    "trigger": ["buy a sword", "need a weapon"],
    "response_parts": {{
      "opener": [
        "I carry a modest selection of blades.",
        "Ah, a warrior! Let me show you what I've got.",
        "Swords? You've come to the right place."
      ],
      "body": "Dwarven-forged steel from the Iron Mountains.",
      "price": "Prices start at 50 gold for a short sword, 120 for a longsword.",
      "closer": [
        "Want to see one?",
        "Shall I wrap one up?",
        "Take your pick, friend."
      ]
    }},
    "context_inserts": {{
      "IF_RETURNING_CUSTOMER": "Back for another? ",
      "IF_QUEST_ACTIVE": "You'll need a good blade for that road. ",
      "IF_EMOTION_FRIENDLY": "And for a friend like you, I'll sharpen it free. "
    }}
  }}

  {BOLD}Output with context:{RESET}
  {GREEN}"Back for another? Ah, a warrior! Let me show you what I've got.
   Dwarven-forged steel from the Iron Mountains. You'll need a good
   blade for that road. Prices start at 50 gold. And for a friend
   like you, I'll sharpen it free. Shall I wrap one up?"{RESET}

  Same pattern, {BOLD}completely different feel{RESET} every time.

  {BOLD}Cost:{RESET} ~0.2ms per query (string assembly)
  {BOLD}Intelligence gained:{RESET} Dynamic responses, no repetition, context-aware


{BOLD}{'═' * 76}{RESET}
{BOLD}  MODULE 4: RELATIONSHIP TRACKER{RESET}
{DIM}  "The NPC remembers YOU across sessions"{RESET}
{BOLD}{'═' * 76}{RESET}

  {BOLD}What it does:{RESET}
  Tracks the NPC's relationship with each player as numeric scores:
  • trust:     0-100  (do they believe the player?)
  • fondness:  0-100  (do they like the player?)
  • respect:   0-100  (do they take the player seriously?)
  • debt:      -100 to 100  (does the NPC owe the player or vice versa?)

  {BOLD}How it works:{RESET}
  Events modify scores:
  • Player completes quest  → trust +20, fondness +10, debt +30
  • Player haggles hard     → respect +5, fondness -5
  • Player threatens NPC    → trust -30, fondness -20
  • Player buys expensive   → fondness +5, debt -10

  Scores unlock/lock response tiers:
  • trust < 20:  Won't share rumors, won't offer quests
  • trust > 60:  Shares secrets, offers better prices
  • fondness > 80: Uses nickname, gives free items
  • debt > 50:   "I owe you one" — unlocks special dialogue

  {BOLD}Persistence:{RESET} 4 integers per player-NPC pair. Trivial to save/load.

  {BOLD}Cost:{RESET} ~0.05ms per query, 16 bytes per relationship
  {BOLD}Intelligence gained:{RESET} NPCs that remember you. The BIGGEST immersion factor.


{BOLD}{'═' * 76}{RESET}
{BOLD}  MODULE 5: WORLD STATE REACTOR{RESET}
{DIM}  "The NPC knows what's happening in the world"{RESET}
{BOLD}{'═' * 76}{RESET}

  {BOLD}What it does:{RESET}
  Subscribes to a global world state bus. When world events happen,
  NPCs update their available response pool and emotional baseline.

  {BOLD}World state flags (set by game engine):{RESET}
  • QUEST_CARAVAN_ACTIVE: true/false
  • QUEST_CARAVAN_COMPLETED: true/false
  • TOWN_UNDER_ATTACK: true/false
  • TIME_OF_DAY: morning/afternoon/evening/night
  • PLAYER_REPUTATION: hero/neutral/criminal

  {BOLD}How it works:{RESET}
  Each pattern can have conditional activation:
  {{
    "id": "SP_GAREN_014",
    "trigger": ["heard any rumors"],
    "conditions": {{
      "QUEST_CARAVAN_ACTIVE": true
    }},
    "response_template": "The caravan is still missing..."
  }},
  {{
    "id": "SP_GAREN_014b",
    "trigger": ["heard any rumors"],
    "conditions": {{
      "QUEST_CARAVAN_COMPLETED": true
    }},
    "response_template": "Thanks to you, the roads are safe again..."
  }}

  {BOLD}NPC behavior shifts:{RESET}
  TOWN_UNDER_ATTACK=true → all NPCs shift emotional baseline to AFRAID
  TIME_OF_DAY=night → shopkeeper patterns disabled ("Shop's closed")
  PLAYER_REPUTATION=criminal → trust starts at 10 instead of 50

  {BOLD}Cost:{RESET} ~0.1ms per query (flag lookup), 0 extra RAM (shared flags)
  {BOLD}Intelligence gained:{RESET} NPCs respond to the world, not just the player


{BOLD}{'═' * 76}{RESET}
{BOLD}  MODULE 6: ESCALATION GATE{RESET}
{DIM}  "When to call the Thinking Layer"{RESET}
{BOLD}{'═' * 76}{RESET}

  {BOLD}What it does:{RESET}
  The smart decision-maker that determines whether the NPC can handle
  a query locally or needs to escalate to the shared SLM.

  {BOLD}Escalation criteria (scored 0-1, escalate if total > threshold):{RESET}

  ┌────────────────────────────┬─────────┬──────────────────────────────┐
  │ Signal                     │ Weight  │ Example                      │
  ├────────────────────────────┼─────────┼──────────────────────────────┤
  │ Pattern confidence < 0.55  │  0.40   │ No good pattern match found  │
  │ Query has novel entities   │  0.20   │ "dragons", "magic portal"    │
  │ Player asked WHY/HOW       │  0.15   │ Needs reasoning, not lookup  │
  │ Conversation depth > 5     │  0.10   │ Deep into multi-turn thread  │
  │ Emotional intensity high   │  0.10   │ Player seems upset/excited   │
  │ Player used complex syntax │  0.05   │ Conditionals, hypotheticals  │
  └────────────────────────────┴─────────┴──────────────────────────────┘

  {BOLD}Below threshold:{RESET} NPC handles it locally (cognitive engine)
  {BOLD}Above threshold:{RESET} Queue to Thinking Layer (SLM)
  {BOLD}Thinking Layer offline:{RESET} Graceful fallback with stall response
    "That's... a deep question. Let me think on that. Ask me again later."
    (In-character, buys time, doesn't break immersion)

  {BOLD}Cost:{RESET} ~0.1ms per query
  {BOLD}Intelligence gained:{RESET} Smart routing, graceful degradation


{BOLD}{'═' * 76}{RESET}
{BOLD}  WHAT THIS GIVES YOU: NPC CAPABILITY MATRIX{RESET}
{BOLD}{'═' * 76}{RESET}

  ┌──────────────────────────┬────────────┬────────────┬────────────────┐
  │ Capability               │ Left Only  │ Left+Right │ + Thinking Lyr │
  │                          │ (patterns) │ (cog. eng) │ (+ SLM)        │
  ├──────────────────────────┼────────────┼────────────┼────────────────┤
  │ Answer known questions   │ {GREEN}    ✓     {RESET}│ {GREEN}    ✓     {RESET}│ {GREEN}      ✓       {RESET}│
  │ Multi-turn conversation  │ {RED}    ✗     {RESET}│ {GREEN}    ✓     {RESET}│ {GREEN}      ✓       {RESET}│
  │ React to player emotion  │ {RED}    ✗     {RESET}│ {GREEN}    ✓     {RESET}│ {GREEN}      ✓       {RESET}│
  │ Remember the player      │ {RED}    ✗     {RESET}│ {GREEN}    ✓     {RESET}│ {GREEN}      ✓       {RESET}│
  │ Varied responses         │ {RED}    ✗     {RESET}│ {GREEN}    ✓     {RESET}│ {GREEN}      ✓       {RESET}│
  │ React to world events    │ {RED}    ✗     {RESET}│ {GREEN}    ✓     {RESET}│ {GREEN}      ✓       {RESET}│
  │ Handle novel questions   │ {RED}    ✗     {RESET}│ {YELLOW}  stall   {RESET}│ {GREEN}      ✓       {RESET}│
  │ Creative improvisation   │ {RED}    ✗     {RESET}│ {RED}    ✗     {RESET}│ {GREEN}      ✓       {RESET}│
  │ Deep reasoning           │ {RED}    ✗     {RESET}│ {RED}    ✗     {RESET}│ {GREEN}      ✓       {RESET}│
  ├──────────────────────────┼────────────┼────────────┼────────────────┤
  │ Latency                  │  {GREEN} ~10ms  {RESET}│  {GREEN} ~12ms  {RESET}│  {YELLOW} ~700ms      {RESET}│
  │ GPU required             │  {GREEN}  None  {RESET}│  {GREEN}  None  {RESET}│  {YELLOW} Shared 450MB{RESET}│
  │ RAM per NPC              │  {GREEN}  2 MB  {RESET}│  {GREEN} ~3 MB  {RESET}│  {GREEN}  ~3 MB      {RESET}│
  │ Feels alive?             │  {RED}   No   {RESET}│  {GREEN}  YES   {RESET}│  {GREEN}  YES+++     {RESET}│
  └──────────────────────────┴────────────┴────────────┴────────────────┘

  {BOLD}Left + Cognitive Engine (no SLM) covers ~90% of what makes an NPC{RESET}
  {BOLD}feel alive.{RESET} The SLM adds the last 10% — creative improvisation
  and deep reasoning — but the NPC is already compelling without it.


{BOLD}{'═' * 76}{RESET}
{BOLD}  PERFORMANCE BUDGET{RESET}
{BOLD}{'═' * 76}{RESET}

  Module                    │ Latency  │ RAM/NPC  │ CPU
  ──────────────────────────┼──────────┼──────────┼──────────
  Left hemisphere (PPBRS)   │  ~8ms    │  2.0 MB  │ negligible
  1. Conversation Tracker   │  ~0.1ms  │  0.5 KB  │ negligible
  2. Emotion State Machine  │  ~0.05ms │  1 byte  │ negligible
  3. Response Compositor    │  ~0.2ms  │  0 (uses patterns)  │ negligible
  4. Relationship Tracker   │  ~0.05ms │  16 bytes │ negligible
  5. World State Reactor    │  ~0.1ms  │  0 (shared flags)   │ negligible
  6. Escalation Gate        │  ~0.1ms  │  0       │ negligible
  ──────────────────────────┼──────────┼──────────┼──────────
  TOTAL                     │ {GREEN}~8.6ms{RESET}   │ {GREEN}~2.1 MB{RESET}  │ {GREEN}negligible{RESET}

  Still fits in a single frame at 60 FPS.
  100 NPCs: {GREEN}~210 MB RAM, 0 GPU, ~8.6ms per query.{RESET}


{BOLD}{'═' * 76}{RESET}
{BOLD}  THE BOTTOM LINE{RESET}
{BOLD}{'═' * 76}{RESET}

  You don't need the SLM to make an NPC feel alive.
  You need it to make an NPC feel {BOLD}brilliant.{RESET}

  The cognitive engine gives you:
  • NPCs that remember your conversation     (Tracker)
  • NPCs that react to your mood             (Emotion)
  • NPCs that never repeat themselves         (Compositor)
  • NPCs that build relationships with you    (Relationship)
  • NPCs that live in a changing world        (World State)
  • NPCs that know their own limits           (Escalation)

  That's already better than 99% of NPCs in any game ever shipped.

  The SLM, sitting in its own Thinking Layer, adds the magic moments:
  the philosophical conversations, the creative improvisation,
  the truly unexpected responses. But it's the cherry on top —
  not the cake itself.

  {BOLD}The cake is the cognitive engine.{RESET}
""")


if __name__ == "__main__":
    main()
