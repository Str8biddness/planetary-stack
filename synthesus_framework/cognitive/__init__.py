# cognitive/ — The NPC Right Hemisphere
# 9 cognitive modules + SemanticMatcher + SocialFabric give NPCs
# behavioral intelligence without any LLM inference.
# Total footprint: under 1ms per query on CPU. Zero GPU.

from .conversation_tracker import ConversationTracker
from .emotion_state_machine import EmotionStateMachine
from .response_compositor import ResponseCompositor
from .relationship_tracker import RelationshipTracker
from .world_state_reactor import WorldStateReactor
from .escalation_gate import EscalationGate
from .personality_bank import PersonalityBank, load_personality_from_file
from .knowledge_graph import KnowledgeGraph, load_knowledge_from_file, load_knowledge_from_dict
from .context_recall import ContextRecall
from .semantic_matcher import SemanticMatcher
from .social_fabric import SocialFabric
from .cognitive_engine import CognitiveEngine

__all__ = [
    "ConversationTracker",
    "EmotionStateMachine",
    "ResponseCompositor",
    "RelationshipTracker",
    "WorldStateReactor",
    "EscalationGate",
    "PersonalityBank",
    "KnowledgeGraph",
    "load_knowledge_from_file",
    "load_knowledge_from_dict",
    "load_personality_from_file",
    "ContextRecall",
    "SemanticMatcher",
    "SocialFabric",
    "CognitiveEngine",
]
