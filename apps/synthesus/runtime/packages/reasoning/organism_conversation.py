#!/usr/bin/env python3
"""
Conversation Organism (ability #4) — Synthesus 5
=================================================

The "converse" ability: detect the query's intent AND its sentiment with two
co-trained organs, then choose a response conditioned on both. Gated by the
framework — the converse ability requires this organism (trained + measured).

  ability "converse" ──requires──▶ ConversationOrganism
        organs (dependencies): intent_detector   (query → intent)
                               sentiment_detector(query → tone)
                               response           (intent + tone → reply)

Honest scope: intent+sentiment-conditioned response *selection/composition*
(scoped dialogue — the validated approach). It genuinely converses over a
domain; it isn't open-ended novel generation. Measured bar: intent accuracy on
held-out queries (drives correct response choice).

Run:  ./venv/bin/python packages/reasoning/organism_conversation.py
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from amplification_organism import AmplificationOrganism, Organ, Synthesus, CapabilityUnavailable  # noqa: E402
from sklearn.feature_extraction.text import TfidfVectorizer  # noqa: E402
from sklearn.linear_model import LogisticRegression          # noqa: E402
from sklearn.pipeline import Pipeline                        # noqa: E402


def _clf(train: dict):
    X = [q for qs in train.values() for q in qs]
    y = [c for c, qs in train.items() for _ in qs]
    return Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2))),
                     ("clf", LogisticRegression(max_iter=1000))]).fit(X, y)


class IntentOrgan(Organ):
    TRAIN = {
        "greeting":   ["hi", "hello there", "hey", "good morning", "whats up", "greetings",
                       "yo", "hiya", "howdy", "good evening"],
        "question":   ["what is mana", "how does magic work", "tell me about dragons",
                       "why is the sky blue", "can you explain quests", "what do dragons eat",
                       "how do i start", "where is the castle", "what happened here"],
        "shop_buy":   ["i want to buy a sword", "ill take the shield", "give me a potion",
                       "purchase the armor", "id like to buy a bow", "sell me a dagger",
                       "can i buy that axe", "ill purchase the helmet"],
        "compliment": ["youre amazing", "great shop", "youre wonderful", "nice work",
                       "youre the best", "what a great place", "youre fantastic", "well done"],
        "insult":     ["youre stupid", "youre an idiot", "you suck", "youre useless",
                       "i hate you", "youre pathetic", "what a fool", "youre worthless"],
        "farewell":   ["goodbye", "see you", "bye", "farewell", "take care", "im leaving",
                       "see you later", "i must go now"],
    }
    def __init__(self): super().__init__("intent_detector"); self.pipe = None
    def train(self, _=None): self.pipe = _clf(self.TRAIN); self.trained = True
    def detect(self, q): return self.pipe.predict([q.lower()])[0]


class SentimentOrgan(Organ):
    TRAIN = {
        "positive": ["this is great", "i love it", "wonderful", "thank you so much",
                     "that helped a lot", "youre amazing", "perfect", "so happy with this"],
        "negative": ["this sucks", "i hate this", "terrible", "im so frustrated",
                     "this is awful", "youre useless", "im angry", "what a waste"],
        "neutral":  ["what is the time", "tell me about dragons", "i want to buy a sword",
                     "where is the shop", "hello", "how does this work", "see you", "okay"],
    }
    def __init__(self): super().__init__("sentiment_detector"); self.pipe = None
    def train(self, _=None): self.pipe = _clf(self.TRAIN); self.trained = True
    def detect(self, q): return self.pipe.predict([q.lower()])[0]


class ResponseOrgan(Organ):
    BASE = {"greeting": "Well met, traveler!", "question": "Let me share what I know...",
            "shop_buy": "A fine choice — that'll be 10 gold.",
            "compliment": "You're too kind — thank you!",
            "insult": "I'd rather we kept things civil.",
            "farewell": "Safe travels, friend."}
    def __init__(self): super().__init__("response")
    def train(self, _=None): self.trained = True
    def compose(self, intent, sentiment):
        base = self.BASE.get(intent, "I'm not sure how to help with that.")
        if sentiment == "negative" and intent != "insult":
            return "I hear your frustration. " + base
        if sentiment == "positive" and intent != "compliment":
            return base + " Glad you're enjoying it!"
        return base


class ConversationOrganism(AmplificationOrganism):
    ability = "converse"
    bar = 0.7
    def __init__(self):
        super().__init__()
        self.intent = IntentOrgan(); self.sent = SentimentOrgan(); self.resp = ResponseOrgan()
        self.organs = {"intent_detector": self.intent,
                       "sentiment_detector": self.sent, "response": self.resp}
    def train(self, _=None):
        self.intent.train(); self.sent.train(); self.resp.train()
    def run(self, query):
        i = self.intent.detect(query); s = self.sent.detect(query)
        return self.resp.compose(i, s)
    def measure(self, test):       # test: list of (query, expected_intent)
        hit = sum(self.intent.detect(q) == t for q, t in test)
        self._score = hit / len(test) if test else 0.0
        return self._score


def main():
    s = Synthesus()
    print("=== converse is gated on its organism ===")
    print(f"can('converse') before organism: {s.can('converse')}")
    try: s.do("converse", "hey there")
    except CapabilityUnavailable as e: print(f"  do() -> BLOCKED: {e}")

    org = ConversationOrganism(); s.register(org); org.train()
    test = [("howdy stranger", "greeting"), ("what do wolves eat", "question"),
            ("ill buy that shield", "shop_buy"), ("this place is lovely", "compliment"),
            ("youre so dumb", "insult"), ("i must be going", "farewell")]
    score = org.measure(test)
    print(f"\ntrained + measured. intent accuracy = {score*100:.0f}%  (bar {org.bar*100:.0f}%)")
    print(f"can('converse') now: {s.can('converse')}")
    print("  organs (dependencies):", list(org.organs))
    print("\n  --- a conversation (intent + sentiment -> response) ---")
    for q in ["hey there!", "what do dragons eat?", "i want to buy a potion",
              "youre the best shopkeeper", "this is useless and youre an idiot",
              "this shop is great but im a bit lost", "see you later"]:
        print(f"  USER : {q}\n  SYNTH: {s.do('converse', q)}")
    print("\nAbility #4: the converse ability requires this organism (blocked above without")
    print("it). Intent+sentiment co-trained organs -> conditioned response. Earned by measurement.")


if __name__ == "__main__":
    main()
