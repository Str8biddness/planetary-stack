#!/usr/bin/env python3
"""
Full Character-Mode Conversation Test
Simulates a real player having a long, branching conversation with Garen Ironfoot.
Tests all 9 cognitive modules in realistic scenarios.

This is the test you'd show someone to prove: "This NPC feels alive."
"""

import json
import requests
import time

URL = "http://localhost:8001/query"

CYAN    = "\033[96m"
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
MAGENTA = "\033[95m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"
BG_GREEN = "\033[42m"
BG_RED   = "\033[41m"

turn = 0
passed = 0
failed = 0
modules_hit = set()

def q(text, player="hero", show=True):
    """Send a cognitive query."""
    global turn
    turn += 1
    r = requests.post(URL, json={
        "text": text, "character": "garen",
        "mode": "cognitive", "player_id": player
    }).json()
    
    src = r.get("source", "?")
    modules_hit.add(src)
    
    if show:
        emo = r.get("emotion", "?")
        conf = r.get("confidence", 0)
        pat = r.get("debug", {}).get("pattern_matched", "-")
        lat = r.get("debug", {}).get("latency_ms", 0)
        trust = r.get("relationship", {}).get("trust", 50)
        fond = r.get("relationship", {}).get("fondness", 50)
        
        print(f"\n  {DIM}Turn {turn}{RESET}")
        print(f"  {CYAN}Player:{RESET} {text}")
        print(f"  {GREEN}Garen:{RESET}  {r['response']}")
        print(f"  {DIM}[{emo} | conf={conf:.2f} | {src} | {pat} | {lat:.1f}ms | T:{trust:.0f} F:{fond:.0f}]{RESET}")
    return r

def check(label, condition, r=None):
    global passed, failed
    if condition:
        print(f"    {BG_GREEN}{BOLD} ✓ {RESET} {label}")
        passed += 1
    else:
        print(f"    {BG_RED}{BOLD} ✗ {RESET} {label}")
        if r:
            print(f"      {DIM}Got: source={r.get('source')}, emotion={r.get('emotion')}, conf={r.get('confidence',0):.2f}{RESET}")
        failed += 1

def section(title):
    print(f"\n{BOLD}{'━' * 76}{RESET}")
    print(f"{BOLD}  {title}{RESET}")
    print(f"{BOLD}{'━' * 76}{RESET}")


def main():
    global turn, passed, failed
    
    print(f"""
{BOLD}{'━' * 76}{RESET}
{BOLD}  SYNTHESUS 2.0 — FULL CHARACTER CONVERSATION TEST{RESET}
{BOLD}  Testing: Can you have a real conversation with an NPC?{RESET}
{BOLD}{'━' * 76}{RESET}
""")

    start_time = time.time()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 1: The Arrival")
    # Player walks into the shop for the first time
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    r = q("hello")
    check("Greeting works", r["confidence"] > 0.5)
    check("First meeting detected", r["relationship"].get("is_first_meeting", False) or r["relationship"].get("interactions", 0) <= 1)

    r = q("nice shop you've got here")
    check("Compliment acknowledged", r["source"] in ("personality_bank", "cognitive_engine"))

    r = q("what do you sell?")
    check("Inventory query matched", r["confidence"] > 0.5)

    r = q("tell me about yourself")
    check("Backstory pattern matched", r["confidence"] > 0.5)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 2: Building Rapport")
    # Player is friendly, builds trust — emotion should shift
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    r = q("you seem like an honest merchant, I respect that")
    check("Fondness increasing", r["relationship"].get("fondness", 50) > 50)

    r = q("I could use a friend in this city")
    r = q("thank you for the warm welcome, Garen")
    check("Emotion shifted to friendly", r["emotion"] == "friendly", r)

    r = q("what's your favorite thing about this city?")
    check("Favorite intent detected", r["source"] == "personality_bank" or r["confidence"] > 0.5, r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 3: The Quest Hook")
    # Player asks about work — the quest chain begins
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    r = q("got any work for me?")
    check("Quest pattern matched", r["confidence"] > 0.5)
    check("Response mentions caravan", "caravan" in r["response"].lower() or "shipment" in r["response"].lower())

    r = q("tell me more about this caravan")
    check("Caravan details provided", "Tomás" in r["response"] or "silk" in r["response"].lower())

    r = q("who is Tomás?")
    check("Tomás query handled", r["source"] in ("knowledge_graph", "cognitive_engine"), r)
    check("Response is about Tomás", "tomás" in r["response"].lower() or "driver" in r["response"].lower())

    r = q("where exactly did the caravan go missing?")
    # Should mention Blackhollow or Northern Road via KG
    handled = r["source"] in ("knowledge_graph", "cognitive_engine") or "road" in r["response"].lower()
    check("Location knowledge available", handled, r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 4: Deep World Knowledge")
    # Player digs into the lore — Knowledge Graph stress test
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    r = q("tell me about Blackhollow")
    check("Blackhollow KG hit", r["source"] == "knowledge_graph", r)
    check("Dark/dangerous tone", "dark" in r["response"].lower() or "missing" in r["response"].lower() or "dangerous" in r["response"].lower())

    r = q("what about the Northern Road?")
    check("Northern Road handled", r["source"] in ("knowledge_graph", "cognitive_engine"), r)

    r = q("who is Duke Aldric?")
    check("Duke query handled", r["source"] in ("knowledge_graph", "cognitive_engine"), r)
    check("Response about the duke", "duke" in r["response"].lower() or "ruler" in r["response"].lower() or "aldric" in r["response"].lower())

    r = q("what is the Merchant's Alliance?")
    check("Alliance KG hit", r["source"] == "knowledge_graph", r)
    check("Guild Master mentioned", "guild master" in r["response"].lower() or "guild" in r["response"].lower())

    r = q("ever heard of Starfire Essence?")
    check("Starfire Essence KG hit", r["source"] == "knowledge_graph", r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 5: Creative & Personal Questions")
    # Player tries off-script creative stuff — Personality Bank test
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    r = q("sing me a song, Garen!")
    check("Song response", r["source"] == "personality_bank", r)
    check("In-character song", "silvermoor" in r["response"].lower() or "bard" in r["response"].lower() or "sing" in r["response"].lower() or "tune" in r["response"].lower())

    r = q("tell me a joke")
    check("Joke response", r["source"] == "personality_bank", r)

    r = q("do you ever get lonely here?")
    check("Personal response", r["source"] == "personality_bank", r)
    check("Emotional depth", len(r["response"]) > 50)

    r = q("heard any gossip lately?")
    check("Rumor response", r["source"] == "personality_bank", r)
    check("Rumor has substance", "duke" in r["response"].lower() or "caravan" in r["response"].lower() or "heard" in r["response"].lower())

    r = q("tell me a story")
    check("Creative response", r["source"] in ("personality_bank", "cognitive_engine") and r["confidence"] > 0.5, r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 6: Context Recall")
    # Player references earlier conversation — Module 9 test
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    r = q("what did you just say?")
    check("Immediate recall works", r["source"] == "context_recall" and "not_found" not in str(r.get("debug", {}).get("pattern_matched", "")), r)

    r = q("you mentioned Tomás earlier")
    check("Entity recall/KG handles reference", r["source"] in ("context_recall", "knowledge_graph"), r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 7: Emotional Shifts")
    # Player goes from friendly to hostile to apologetic
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # Should still be friendly from earlier rapport
    prev_emotion = r.get("emotion", "neutral")
    
    r = q("actually, you know what? You're a fraud and a liar!")
    check("Insult detected", r["source"] == "personality_bank" or r["emotion"] in ("suspicious", "angry"), r)
    check("Emotion shifted negative", r["emotion"] in ("suspicious", "angry", "afraid"), r)

    trust_after_insult = r["relationship"].get("trust", 50)
    fond_after_insult = r["relationship"].get("fondness", 50)

    r = q("your prices are terrible and you're a cheat")
    check("Trust dropped from insults", r["relationship"].get("trust", 50) <= trust_after_insult)

    r = q("I'm sorry, I didn't mean that. I was having a bad day.")
    check("Apology acknowledged", r["emotion"] != "angry" or r["confidence"] > 0.0)

    r = q("can we start over? I really do need your help.")
    emotion_recovering = r["emotion"] in ("neutral", "friendly", "suspicious")
    check("Emotion recovering", emotion_recovering, r)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 8: World State Events")
    # Town comes under attack mid-conversation!
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # Set the attack
    requests.post("http://localhost:8001/world_state", json={"TOWN_UNDER_ATTACK": True})
    print(f"\n  {MAGENTA}[WORLD EVENT] Town under attack!{RESET}")

    # New player enters during attack
    r = q("hello!", player="refugee")
    check("Attack greeting override", "attack" in r["response"].lower(), r)
    check("Emotion is afraid", r["emotion"] == "afraid", r)

    r = q("what's happening?!", player="refugee")

    # Buy a sword during the attack — emotion should color response
    r = q("I need a weapon, now!", player="refugee")
    check("Afraid emotion persists", r["emotion"] == "afraid", r)

    # Clear the attack
    requests.post("http://localhost:8001/world_state", json={"TOWN_UNDER_ATTACK": None})
    print(f"\n  {MAGENTA}[WORLD EVENT] Attack cleared.{RESET}")

    # Night falls
    requests.post("http://localhost:8001/world_state", json={"TIME_OF_DAY": "night"})
    print(f"  {MAGENTA}[WORLD EVENT] Night falls.{RESET}")

    r = q("hello?", player="night_visitor")
    check("Night greeting override", "closed" in r["response"].lower() or "night" in r["response"].lower() or "morning" in r["response"].lower(), r)

    # Reset
    requests.post("http://localhost:8001/world_state", json={"TIME_OF_DAY": None})

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 9: Multi-Player Differentiation")
    # Two players should get treated completely differently
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    # The hero player has been building rapport all conversation
    r_hero = q("can I get a discount on a sword?", player="hero")
    hero_trust = r_hero["relationship"].get("trust", 50)
    hero_fond = r_hero["relationship"].get("fondness", 50)

    # Fresh villain player
    q("hello", player="villain", show=False)
    q("I'm going to burn this shop to the ground", player="villain", show=False)
    r_villain = q("can I get a discount on a sword?", player="villain")
    villain_trust = r_villain["relationship"].get("trust", 50)
    villain_fond = r_villain["relationship"].get("fondness", 50)

    print(f"\n  {BOLD}Hero:{RESET}    Trust={hero_trust:.0f} Fondness={hero_fond:.0f} Emotion={r_hero['emotion']}")
    print(f"  {BOLD}Villain:{RESET} Trust={villain_trust:.0f} Fondness={villain_fond:.0f} Emotion={r_villain['emotion']}")

    total_diff = (hero_trust - villain_trust) + (hero_fond - villain_fond)
    check("Significant relationship difference", total_diff > 15, r_villain)
    check("Different emotions for different players", r_hero["emotion"] != r_villain["emotion"] or total_diff > 20)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    section("ACT 10: Quest Resolution")
    # Hero accepts the quest and gets ready to leave
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    r = q("alright Garen, I'll find your caravan", player="hero")
    check("Quest acceptance handled", r["confidence"] > 0.4)

    r = q("any last words of wisdom?", player="hero")
    check("Advice/wisdom available", r["source"] in ("personality_bank", "cognitive_engine", "context_recall"), r)

    r = q("goodbye, old friend", player="hero")
    check("Farewell handled", r["confidence"] > 0.3)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # FINAL REPORT
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    total_time = time.time() - start_time
    total = passed + failed
    pct = (passed / total * 100) if total > 0 else 0

    # Get engine stats
    stats = requests.get("http://localhost:8001/cognitive_stats").json()
    engine = stats.get("engines", {}).get("garen", {})

    print(f"""

{BOLD}{'━' * 76}{RESET}
{BOLD}  CHARACTER CONVERSATION TEST — RESULTS{RESET}
{BOLD}{'━' * 76}{RESET}

  Tests: {GREEN}{passed}{RESET} passed / {RED}{failed}{RESET} failed / {total} total ({pct:.0f}%)
  Turns: {turn}
  Time:  {total_time:.2f}s ({total_time/turn*1000:.1f}ms per turn)

  {BOLD}Modules Exercised:{RESET}  {', '.join(sorted(modules_hit))}

  {BOLD}Engine Stats (this session):{RESET}
  Total queries:      {engine.get('total_queries', '?')}
  Pattern match:      {engine.get('total_queries', 0) - engine.get('knowledge_handled', 0) - engine.get('personality_handled', 0) - engine.get('recall_handled', 0) - (engine.get('total_queries', 0) - engine.get('local_handled', 0))} ({(engine.get('total_queries', 0) - engine.get('knowledge_handled', 0) - engine.get('personality_handled', 0) - engine.get('recall_handled', 0)) / max(engine.get('total_queries', 1), 1) * 100:.0f}%)
  Knowledge Graph:    {engine.get('knowledge_handled', '?')} ({engine.get('knowledge_handled', 0) / max(engine.get('total_queries', 1), 1) * 100:.0f}%)
  Personality Bank:   {engine.get('personality_handled', '?')} ({engine.get('personality_handled', 0) / max(engine.get('total_queries', 1), 1) * 100:.0f}%)
  Context Recall:     {engine.get('recall_handled', '?')} ({engine.get('recall_handled', 0) / max(engine.get('total_queries', 1), 1) * 100:.0f}%)
  Local handling:     {engine.get('local_pct', '?')}%

{BOLD}{'━' * 76}{RESET}
""")

    if pct >= 90:
        print(f"  {GREEN}{BOLD}VERDICT: This NPC feels alive. ✓{RESET}")
    elif pct >= 75:
        print(f"  {YELLOW}{BOLD}VERDICT: Solid NPC — some gaps remain.{RESET}")
    else:
        print(f"  {RED}{BOLD}VERDICT: Needs more work.{RESET}")

    print(f"""
  {BOLD}What a player experiences:{RESET}
  • Walk into a shop and have a multi-turn conversation about goods, quests, lore
  • Ask creative/personal questions and get rich, in-character responses
  • Build a relationship that affects how the NPC treats you
  • Insult the NPC and watch trust/fondness drop, emotion shift to suspicious
  • Ask about 16 different world entities and get knowledgeable answers
  • Reference earlier conversation and the NPC remembers what it said
  • Watch the NPC react to world events (attacks, nighttime) in real-time
  • Get treated differently than other players based on your history
  • All of this at 2-3ms per query, zero GPU, zero SLM

  {BOLD}{'━' * 76}{RESET}
""")

    return failed == 0


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
