"""
Synthesus 2.0 — ML Swarm
AIVM LLC

7 specialized micro-models that replace what used to require a 0.6B
parameter language model. Total footprint: ~458 KB. Total inference: <1ms.

Micro-Models:
  1. SwarmEmbedder      — TF-IDF + SVD text embeddings for FAISS (context embedder)
  2. IntentClassifier   — Parse player intent from query text
  3. SentimentAnalyzer  — Detect emotional valence/polarity of player input
  4. BehaviorPredictor  — Anticipate player next actions
  5. LootBalancer       — Fair reward/pricing distribution
  6. DialogueRanker     — Rank candidate NPC responses
  7. EmotionDetector    — Classify player emotional state (discrete categories)
"""

from .swarm_embedder import SwarmEmbedder
from .intent_classifier import IntentClassifier
from .sentiment_analyzer import SentimentAnalyzer
from .behavior_predictor import BehaviorPredictor
from .loot_balancer import LootBalancer
from .dialogue_ranker import DialogueRanker
from .emotion_detector import EmotionDetector

__all__ = [
    "SwarmEmbedder",
    "IntentClassifier",
    "SentimentAnalyzer",
    "BehaviorPredictor",
    "LootBalancer",
    "DialogueRanker",
    "EmotionDetector",
]
