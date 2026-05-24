#!/usr/bin/env python3
"""
Synthesus ML Organ Data Synthesizer
Generates large high-quality synthetic training datasets for all ML organs.

Usage:
    python scripts/synthesize_ml_data.py [--organ INTENT|SENTIMENT|BEHAVIOR|EMOTION|DIALOGUE|LOOT|ALL]
    python scripts/synthesize_ml_data.py --organ ALL --size 2000
"""

import argparse
import json
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

random.seed(42)

# ─────────────────────────────────────────────────────────────
# INTENT CLASSIFIER — 14 classes, high-variety phrase templates
# ─────────────────────────────────────────────────────────────

_INTENT_TEMPLATES = {
    "greeting": [
        "hello", "hi", "hey", "yo", "howdy", "greetings", "good day", "good morning",
        "good evening", "what's up", "how are you", "howdy partner", "long time no see",
        "hey there", "hiya", "well hello there", "hello friend", "good to see you",
        "nice to meet you", "pleased to meet you",
    ],
    "farewell": [
        "goodbye", "bye", "see you", "farewell", "take care", "later", "gotta go",
        "I must leave", "until next time", "I'll be back", "see you around",
        "I'm off", "heading out", "time to go", "bye for now", "catch you later",
        "so long", "it's been real", "I'll see myself out",
    ],
    "question": [
        "what is this place", "who are you", "what do you do", "where am I",
        "how long have you been here", "what's going on", "can you explain",
        "I have a question", "tell me what you know", "can I ask something",
        "want to know something", "curious about something", "help me understand",
        "I was wondering", "do you happen to know", "could you tell me",
        "I'm trying to find out", "can you inform me", "what does this mean",
        "what's the story here", "any idea what that is", "I need information",
    ],
    "lore": [
        "tell me about the history", "what is the lore of this place", "any legends",
        "tell me about the kingdom", "what happened in the war", "ancient history",
        "tell me a story", "any myths around here", "what's the legend", "the old tales",
        "I want to hear about the past", "the ancient ones", "forgotten histories",
        "tell of the old days", "any tales of heroes", "what happened long ago",
        "the story behind this town", "any prophecies", "rumors of the past",
        "the old world stories", "hidden lore", "secrets of this place",
    ],
    "shop_browse": [
        "what do you sell", "show me your wares", "what's for sale", "what do you have",
        "let me see your inventory", "any goods available", "what items do you carry",
        "what can I browse", "show me what you've got", "open up your shop",
        "I want to look around", "display your goods", "what's in stock",
        "anything interesting for sale", "do you have anything special",
        "show me around", "let me browse", "what are your offerings",
        "I hear you have good items", "what's new in stock",
    ],
    "shop_buy": [
        "I want to buy that", "I'll take this one", "purchase a sword", "buy a shield",
        "sell me a weapon", "I need a health potion", "can I get one of those",
        "how much for the sword", "I'll buy it", "give me that item", "I'll pay for it",
        "add it to my purchase", "I want to order this", "I'll have that please",
        "one of those please", "take my gold", "that's exactly what I need",
        "I need this item", "it's just what I was looking for", "I'll take it all",
        "ring it up", "I'm ready to buy", "name your price and I'll pay",
        "give me the good stuff", "I have the coin",
    ],
    "shop_haggle": [
        "too expensive", "can you lower the price", "that's too much", "give me a discount",
        "how about a better price", "come on cheaper", "I'll pay 50 gold",
        "would you take less", "that's highway robbery", "I can get this cheaper elsewhere",
        "negotiate the price", "work with me on this", "price is a bit steep",
        "can't you do better", "I was thinking cheaper", "cut me a deal",
        "I'm a good customer", "what's your best price", "throw in a discount",
        "make me an offer", "I expect a better rate", "discount please",
        "I'll pay if it's fair", "name a lower price",
    ],
    "personal": [
        "are you happy", "do you get lonely", "tell me about yourself", "are you married",
        "what are your dreams", "how are you feeling", "do you have a family",
        "what do you enjoy", "tell me your story", "what's your name", "where are you from",
        "what's your life like", "any regrets", "what makes you happy", "sad lately",
        "have you seen hard times", "any friends here", "what keeps you busy",
        "how's your day going", "anything troubling you", "you seem well",
        "I feel for you", "you've been here long", "seen any trouble",
    ],
    "creative": [
        "sing me a song", "tell me a joke", "do you know any riddles", "tell me a story",
        "make me laugh", "recite a poem", "entertain me", "any funny stories",
        "do a trick", "share some wisdom", "teach me something", "any riddles",
        "give me a puzzle", "tell a tale", "make me smile", "I've had a rough day",
        "cheer me up", "something amusing", "a bit of fun", "humor me",
        "lighten the mood", "something witty", "any songs here",
    ],
    "combat": [
        "I attack you", "draw your weapon", "prepare to fight", "defend yourself",
        "I'm going to kill you", "fight me", "I challenge you", "let's battle",
        "time to die", "I'm your opponent", "no mercy", "you'll regret that",
        "get ready to lose", "swing at you now", "strike", "counter attack",
        "use your skill", "I'll crush you", "destroy you", "finish you off",
        "this ends now", "witness my power", "face me", "prepare to die fool",
    ],
    "quest": [
        "any work available", "I'll take the job", "got any quests", "I need a task",
        "what needs doing", "any missions", "I accept the quest", "I'll do it",
        "send me on a quest", "count me in", "looking for a job", "need employment",
        "have something for me", "I'm an adventurer", "dispatch me somewhere",
        "I want to help", "where do you need me", "point me to trouble",
        "give me a purpose", "I need coin and glory", "hero work available",
        "any monsters to slay", "dangerous tasks", "I'll handle it",
    ],
    "compliment": [
        "you're amazing", "great shop you have", "you're the best", "I really appreciate you",
        "you're so kind", "what a wonderful place", "impressive work", "you're very helpful",
        "you're a legend", "love what you've done", "extraordinary", "you've outdone yourself",
        "top notch", "first class", "I admire your skill", "truly magnificent",
        "remarkable work", "you've earned my respect", "a true master", "you're a credit to your trade",
    ],
    "insult": [
        "you're stupid", "you're an idiot", "this place is terrible", "you're a liar",
        "you're a cheat", "you're useless", "what a dump", "you're pathetic",
        "this town is a joke", "worst I've ever seen", "disgraceful", "you're a fraud",
        "a waste of space", "pathetic excuse for a shop", "garbage", "you call this quality",
        "this is trash", "I've seen better", "laughable", "embarrassing",
    ],
    "unknown": [
        "asdfghjkl qwerty", "the GDP of Belgium", "purple elephant mathematics",
        "define ultracrepidarian", "I like pie and jugaad", "xyz coordinate system",
        "quantum entanglement explained", "antidisestablishmentarianism",
    ],
}


def generate_intent_data(n_per_class: int = 300) -> List[Tuple[str, str]]:
    """Generate large intent classification dataset with diverse phrasing."""
    data = []
    for intent, templates in _INTENT_TEMPLATES.items():
        for _ in range(n_per_class):
            base = random.choice(templates)
            # Add variations: prefixes, suffixes, mid-sentence twists
            variant = random.choice([
                lambda b: b,
                lambda b: b + " please",
                lambda b: b + " won't you",
                lambda b: b + " for me",
                lambda b: b + " would you",
                lambda b: b + " can you",
                lambda b: b + " will you",
                lambda b: b + " won't you",
                lambda b: b.capitalize() + "?",
                lambda b: b.capitalize() + ".",
                lambda b: "Hey, " + b,
                lambda b: "So, " + b,
                lambda b: "Well, " + b,
                lambda b: "Listen, " + b,
                lambda b: "Umm, " + b,
                lambda b: "Actually, " + b,
                lambda b: b + "...",  # trailing ellipsis
                lambda b: b.replace(" ", "  "),  # extra spaces
            ])
            try:
                text = variant(base)
            except Exception:
                text = base
            data.append((text, intent))
    return data


# ─────────────────────────────────────────────────────────────
# SENTIMENT ANALYZER — 6 classes, nuanced phrasing
# ─────────────────────────────────────────────────────────────

_SENTIMENT_TEMPLATES = {
    "positive": {
        "strong": [
            "you are absolutely wonderful", "this is absolutely fantastic", "I love this so much",
            "you're incredible", "best I've ever seen", "truly remarkable", "extraordinary",
            "you've outdone yourself", "absolutely brilliant", "this is perfect",
        ],
        "mild": [
            "that's nice", "I appreciate it", "thank you", "how kind", "that's good",
            "I'm happy with that", "pleased to hear", "that works for me", "fine by me",
            "sounds good", "looking good", "not bad at all", "this will do nicely",
        ],
        "enthusiastic": [
            "oh wow thank you so much", "this is amazing I'm so happy",
            "you've made my day", "absolutely love it here", "best experience ever",
            "I'm thrilled", "couldn't be happier", "what a delight",
        ],
    },
    "negative": {
        "strong": [
            "this is absolutely terrible", "I hate this", "you're useless", "what garbage",
            "this is a waste", "pathetic", "disgusting", "how dare you", "you've ruined everything",
        ],
        "mild": [
            "I'm not happy about this", "that's disappointing", "not impressed",
            "this could be better", "I'm dissatisfied", "let me down", "not great",
            "a bit underwhelming", "not what I expected", "not good enough",
        ],
        "frustrated": [
            "this is frustrating", "I can't believe this", "are you serious",
            "unbelievable", "are you kidding me", "this is ridiculous",
            "I've had enough", "seriously though", "come on now",
        ],
    },
    "neutral": {
        "factual": [
            "what is that", "tell me about it", "I want to know more", "explain that",
            "I'm curious", "tell me how it works", "what's the price", "describe it",
            "give me the details", "I have a question", "just want to know",
        ],
        "transactional": [
            "I need that item", "I'll take the sword", "show me the wares",
            "what do you have", "where is the shop", "point me to the inn",
            "who is in charge", "where do I go", "what's the cost",
        ],
    },
    "threatening": {
        "direct": [
            "I'll kill you", "hand over the gold or die", "give me everything or suffer",
            "prepare to die", "I'm going to destroy you", "you'll regret crossing me",
            "I'll burn this place down", "your days are numbered",
        ],
        "coercive": [
            "give me what I want or else", "don't make me hurt you", "surrender or die",
            "you'll pay for this", "I'm not playing games", "this is your last warning",
            "choose your fate", "don't test me", "you're making a mistake",
        ],
    },
    "pleading": {
        "desperate": [
            "please help me I'm desperate", "I have nothing left", "my family is starving",
            "have mercy on me", "I can't afford this", "please give me a chance",
            "I'm so scared and alone", "I don't know what to do", "take pity on me",
            "please I'm begging you", "I have no other options", "I need this so badly",
        ],
        "sad": [
            "I'm so sad", "nothing seems to go right", "I feel hopeless", "everything is falling apart",
            "my life is in ruins", "I can't catch a break", "why does everything go wrong",
            "I just want it all to stop", "I'm at my lowest", "nothing matters anymore",
        ],
    },
    "flirtatious": {
        "bold": [
            "you have beautiful eyes", "are you single", "you're quite handsome",
            "want to grab a drink sometime", "you're very charming", "how about dinner",
            "I find you attractive", "quite the looker", "your smile lights up the room",
        ],
        "subtle": [
            "nice to see you always", "you look well today", "you've got a nice energy",
            "I always enjoy our talks", "you're good company", "this feels nice",
            "I could talk to you all day", "you make me smile", "there's something about you",
        ],
    },
}


def generate_sentiment_data(n_per_class: int = 300) -> List[Tuple[str, str]]:
    """Generate large sentiment classification dataset."""
    data = []
    for sentiment, strength_buckets in _SENTIMENT_TEMPLATES.items():
        for _ in range(n_per_class):
            bucket_key = random.choice(list(strength_buckets.keys()))
            templates = strength_buckets[bucket_key]
            base = random.choice(templates)
            # Add minor variations
            variants = [
                lambda b: b,
                lambda b: b + ".",
                lambda b: b.capitalize() + "!",
                lambda b: "Hey, " + b,
                lambda b: b.capitalize(),
                lambda b: "Wow, " + b,
                lambda b: "Look, " + b,
            ]
            try:
                text = random.choice(variants)(base)
            except Exception:
                text = base
            data.append((text, sentiment))
    return data


# ─────────────────────────────────────────────────────────────
# BEHAVIOR PREDICTOR — features + action labels
# ─────────────────────────────────────────────────────────────

_BEHAVIOR_ACTIONS = ["buy", "sell", "leave", "fight", "ask_question", "explore", "negotiate", "idle"]

_BEHAVIOR_FEATURES = [
    ("turn_count", list(range(1, 21))),
    ("avg_msg_length", [5, 10, 15, 20, 25, 30, 50]),
    ("sentiment_trend", [-1.0, -0.5, 0.0, 0.5, 1.0]),
    ("topic_switches", list(range(0, 6))),
    ("time_between_msgs", [5, 15, 30, 60, 120, 300]),
    ("question_ratio", [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]),
]

# Mapping: feature combos → likely action
_BEHAVIOR_RULES = [
    # High question ratio + low msg length → ask_question
    (lambda f: f["question_ratio"] >= 0.5 and f["avg_msg_length"] <= 15, "ask_question"),
    # Negative sentiment + high turn count → leave
    (lambda f: f["sentiment_trend"] < -0.3 and f["turn_count"] >= 6, "leave"),
    # Negative sentiment + low turn count → fight
    (lambda f: f["sentiment_trend"] < -0.3 and f["turn_count"] <= 3, "fight"),
    # High turns + neutral sentiment + long messages → negotiate
    (lambda f: f["turn_count"] >= 5 and f["sentiment_trend"] == 0.0 and f["avg_msg_length"] >= 20, "negotiate"),
    # Low turns + positive sentiment → buy
    (lambda f: f["turn_count"] <= 3 and f["sentiment_trend"] > 0.3, "buy"),
    # High topic switches + many turns → explore
    (lambda f: f["topic_switches"] >= 3 and f["turn_count"] >= 8, "explore"),
    # Very short messages + few turns → idle
    (lambda f: f["avg_msg_length"] <= 5 and f["turn_count"] <= 2, "idle"),
    # Default: sell
    (lambda _: True, "sell"),
]


def generate_behavior_data(n_samples: int = 1000) -> List[Dict]:
    """Generate behavioral feature vectors with action labels."""
    data = []
    for _ in range(n_samples):
        features = {
            name: random.choice(vals) for name, vals in _BEHAVIOR_FEATURES
        }
        # Determine action via rules
        action = None
        for rule_fn, action_label in _BEHAVIOR_RULES:
            if rule_fn(features):
                action = action_label
                break
        # Add noise: 10% flip to random action
        if random.random() < 0.1:
            action = random.choice(_BEHAVIOR_ACTIONS)
        features["action"] = action
        data.append(features)
    return data


# ─────────────────────────────────────────────────────────────
# EMOTION DETECTOR — 8 emotion categories
# ─────────────────────────────────────────────────────────────

_EMOTION_TEMPLATES = {
    "joy": [
        "I am so happy", "this is wonderful", "what joy I feel", "I'm delighted",
        "how marvelous", "I'm overjoyed", "this makes me so glad", "what a thrill",
        "pure happiness", "I could leap for joy", "everything is perfect",
        "I'm elated", "what a beautiful day", "my heart is full", "blissful",
    ],
    "anger": [
        "I'm furious", "this makes me so angry", "I could punch something",
        "I'm enraged", "how dare you", "I'm going to lose my temper", "this is infuriating",
        "I'm so mad I could scream", "unacceptable", "how could you do this to me",
        "I'm at my limit", "this is intolerable", "I've had enough of this",
        "wrath upon you", "you've pushed too far", "I will not tolerate this",
    ],
    "sadness": [
        "I feel so sad", "nothing brings me joy anymore", "my heart is heavy",
        "I'm feeling down", "everything feels hopeless", "I can't stop crying",
        "the weight of sorrow", "I'm heartbroken", "I miss them so much",
        "tears won't stop falling", "I feel so alone", "this pain is unbearable",
        "why does it hurt so much", "I wish it would stop", "I can't bear this",
    ],
    "fear": [
        "I'm terrified", "I'm so scared", "this frightens me to my core",
        "I am afraid", "my heart races with fear", "something terrible is coming",
        "dread fills my soul", "I can't shake this fear", "the terror is real",
        "I'm shaking", "cold sweat runs down my spine", "I sense danger",
        "something is very wrong", "I fear the worst", "this chill I feel",
    ],
    "surprise": [
        "I am shocked", "I can't believe it", "what a twist", "unexpected!",
        "my jaw dropped", "I never saw that coming", "astonishing", "wow just wow",
        "this surprises me greatly", "speechless right now", "what a revelation",
        "truly unexpected", "I am awestruck", "you've stunned me", "incredible",
    ],
    "disgust": [
        "this disgusts me", "I feel sick", "revolting", "how disgusting",
        "I can barely stand this", "the sheer audacity", "nauseating",
        "it makes my stomach turn", "absolutely repulsive", "what vileness",
        "I am revolted", "the stench of it", "that is putrid", "how foul",
    ],
    "trust": [
        "I trust you completely", "I believe in you", "you have my full trust",
        "I know you won't let me down", "you are honest and true",
        "I put my faith in you", "you've never betrayed my trust",
        "I rely on you fully", "you are my most trusted friend",
        "I know you're telling the truth", "I believe every word you say",
    ],
    "neutral": [
        "the weather is fine", "I need to go to the market", "what time is it",
        "where is the nearest town", "tell me about the road ahead",
        "I saw a bird on the roof", "three coins on the table", "the sun is bright",
        "a cup of tea please", "the book is on the shelf", "nothing unusual",
    ],
}


def generate_emotion_data(n_per_class: int = 200) -> List[Tuple[str, str]]:
    """Generate emotion detection dataset."""
    data = []
    for emotion, templates in _EMOTION_TEMPLATES.items():
        for _ in range(n_per_class):
            base = random.choice(templates)
            variants = [
                lambda b: b,
                lambda b: b + ".",
                lambda b: b.capitalize() + "!",
                lambda b: "Hey, " + b,
                lambda b: b.capitalize(),
            ]
            try:
                text = random.choice(variants)(base)
            except Exception:
                text = base
            data.append((text, emotion))
    return data


# ─────────────────────────────────────────────────────────────
# DIALOGUE RANKER — query + personality + responses + rankings
# ─────────────────────────────────────────────────────────────

_DIALOGUE_SCENARIOS = [
    {
        "query": "hello",
        "candidates": [
            "Greetings, traveler. What brings you to our humble shop?",
            "Hey. Whaddaya want?",
            "Welcome, friend! Feel free to look around.",
            "Oh, a customer. What do you need?",
            "Good day to you! How can I assist?",
            "Yo, welcome in!",
        ],
        "ideal_ranks": [2, 0, 3, 4, 1, 5],  # personality index → rank among candidates
    },
    {
        "query": "how much for the sword",
        "candidates": [
            "That blade? Fifty gold coins. Non-negotiable.",
            "The sword costs fifty gold. Take it or leave it.",
            "Hmm, for you? Forty-five gold. You've been a good customer.",
            "Fifty gold. Quality steel, worth every coin.",
            "Which sword? We have several. The common one is fifty gold.",
            "50 gold. It's on the wall there.",
        ],
        "ideal_ranks": [2, 4, 1, 0, 5, 3],
    },
    {
        "query": "I need a quest",
        "candidates": [
            "Adventurer, is it? There's a wyvern spotted near the mountain pass.",
            "I've got nothing for you.",
            "Quest? Let me think... yes, the miller has a rat problem.",
            "A quest you say? The blacksmith lost a shipment on the road north.",
            "Nothing right now, sorry.",
            "The guild has postings. But I heard something about wolves near the farmstead.",
        ],
        "ideal_ranks": [5, 2, 0, 3, 1, 4],
    },
    {
        "query": "are you okay",
        "candidates": [
            "I've been better, friend. These are hard times.",
            "None of your business.",
            "Why do you ask? I'm fine. Just tired.",
            "Thank you for caring. It has been... a long day.",
            "I'm great! Ready to trade!",
            "Worried about me? That's kind. I'm holding up.",
        ],
        "ideal_ranks": [3, 5, 2, 0, 1, 4],
    },
]


def generate_dialogue_data(n_expanded: int = 200) -> List[Dict]:
    """Generate dialogue ranking dataset with expanded variations."""
    data = []
    for scenario in _DIALOGUE_SCENARIOS:
        base_query = scenario["query"]
        candidates = scenario["candidates"]
        # Expand with rephrasings of the query
        rephrasings = {
            "hello": ["hi", "hey there", "greetings", "good day", "hello shopkeeper"],
            "how much for the sword": [
                "what's the price of that sword", "how much is the blade",
                "cost of the sword", "how many gold for the steel",
            ],
            "I need a quest": [
                "any jobs for an adventurer", "send me on an adventure",
                "looking for work", "need something to do",
            ],
            "are you okay": [
                "how are you feeling", "is everything alright", "you doing okay",
                "are you well", "you seem troubled",
            ],
        }
        queries = rephrasings.get(base_query, [base_query])
        for _ in range(n_expanded):
            query = random.choice(queries)
            entry = {
                "query": query,
                "candidates": candidates,
                "ideal_ranks": scenario["ideal_ranks"],
            }
            data.append(entry)
    return data


# ─────────────────────────────────────────────────────────────
# LOOT BALANCER — player context → loot tier/values
# ─────────────────────────────────────────────────────────────

_LOOT_TIERS = ["common", "uncommon", "rare", "epic", "legendary"]
_LOOT_ITEMS = {
    "common": ["Wooden Cup", "Copper Ring", "Worn Boots", "Linen Shirt", "Clay Pot"],
    "uncommon": ["Steel Dagger", "Silver Ring", "Leather Armor", "Hunter's Bow", "Potion of Minor Healing"],
    "rare": ["Enchanted Sword", "Ruby Amulet", "Mithril Chain", "Arcane Staff", "Potion of Greater Healing"],
    "epic": ["Vorpal Blade", "Dragon Scale Armor", "Staff of Thunder", "Orb of Power", "Elixir of Giants"],
    "legendary": ["Excalibur", "Crown of the Ancients", "Worldsplitter Axe", "Philosopher's Stone", "Mantle of the Void"],
}


def generate_loot_data(n_samples: int = 500) -> List[Dict]:
    """Generate loot balancing dataset with player context and appropriate rewards."""
    data = []
    player_levels = list(range(1, 31))
    loyalty_levels = list(range(0, 11))
    quest_completions = list(range(0, 21))

    for _ in range(n_samples):
        level = random.choice(player_levels)
        loyalty = random.choice(loyalty_levels)
        quest_done = random.choice(quest_completions)

        # Determine appropriate tier given context
        if level >= 20 and loyalty >= 7:
            tier = random.choices(_LOOT_TIERS, weights=[0.05, 0.10, 0.25, 0.35, 0.25])[0]
        elif level >= 10:
            tier = random.choices(_LOOT_TIERS, weights=[0.20, 0.30, 0.30, 0.15, 0.05])[0]
        else:
            tier = random.choices(_LOOT_TIERS, weights=[0.50, 0.30, 0.15, 0.04, 0.01])[0]

        item = random.choice(_LOOT_ITEMS[tier])
        data.append({
            "player_level": level,
            "loyalty": loyalty,
            "quest_completions": quest_done,
            "tier": tier,
            "item": item,
        })
    return data


# ─────────────────────────────────────────────────────────────
# MAIN — generate all datasets and save to JSON
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Synthesize ML training data for Synthesus organs")
    parser.add_argument("--organ", default="ALL",
                        choices=["INTENT", "SENTIMENT", "BEHAVIOR", "EMOTION", "DIALOGUE", "LOOT", "ALL"])
    parser.add_argument("--size", type=int, default=1500, help="Samples per class for text classifiers")
    parser.add_argument("--output-dir", default="ml/synthetic_data",
                        help="Directory to save synthetic datasets")
    args = parser.parse_args()

    output_dir = REPO_ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    def save(name: str, data):
        path = output_dir / f"{name}_{timestamp}.json"
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Saved {len(data) if isinstance(data, list) else len(data)} entries → {path}")

    organs = {
        "INTENT": lambda: generate_intent_data(n_per_class=args.size),
        "SENTIMENT": lambda: generate_sentiment_data(n_per_class=args.size),
        "BEHAVIOR": lambda: generate_behavior_data(n_samples=args.size),
        "EMOTION": lambda: generate_emotion_data(n_per_class=args.size),
        "DIALOGUE": lambda: generate_dialogue_data(n_expanded=args.size),
        "LOOT": lambda: generate_loot_data(n_samples=args.size),
    }

    if args.organ == "ALL":
        to_run = organs
    else:
        to_run = {args.organ: organs[args.organ]}

    print(f"=== Synthesus ML Data Synthesizer | {timestamp} | {args.size} per class ===")
    for name, gen_fn in to_run.items():
        print(f"Generating {name}...")
        data = gen_fn()
        save(name.lower(), data)

    # Also save a manifest
    manifest = {
        "generated": timestamp,
        "size_per_class": args.size,
        "organs": {k: len(v()) for k, v in organs.items()},
    }
    with open(output_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nDone. Datasets saved to {output_dir}")


if __name__ == "__main__":
    main()
