#!/usr/bin/env python3
"""
A/B Test: Chaining vs PatternEngine at scale.
Compares quality and performance of pattern chaining vs traditional synthesis.
"""

import json
import time
from pathlib import Path
from typing import List, Dict, Any
import statistics
import sys

sys.path.insert(0, '.')

# Import our modules
from core.knowledge_cloud import KnowledgeCloud
from cognitive.sequence_linker import SequenceLinker
from cognitive.slot_filler import SlotFiller
from cognitive.pattern_engine import PatternEngine  # Assuming exists

class ABTester:
    """A/B test framework for comparing synthesis methods."""

    def __init__(self, knowledge_cloud: KnowledgeCloud):
        self.knowledge_cloud = knowledge_cloud
        self.linker = SequenceLinker()
        self.filler = SlotFiller()
        self.pattern_engine = PatternEngine()  # Fallback engine

    def synthesize_with_chaining(self, query: str, emotion: str = "neutral",
                               trust: float = 50.0) -> Dict[str, Any]:
        """Synthesize response using pattern chaining."""
        start_time = time.time()

        # Get relevant patterns
        cloud_results = self.knowledge_cloud.lookup_multi(query, emotion=emotion, trust=trust)

        if not cloud_results:
            return {
                "method": "chaining",
                "response": "",
                "quality_score": 0.0,
                "latency_ms": (time.time() - start_time) * 1000,
                "error": "no_results"
            }

        # Build chain
        context_vector = {'intent': 'inform', 'emotion': emotion}
        world_state = {'entities': [r['entity_id'] for r in cloud_results[:3]]}
        chain_plan = self.linker.build_chain(cloud_results, context_vector, world_state)

        if not chain_plan.steps:
            return {
                "method": "chaining",
                "response": "",
                "quality_score": 0.0,
                "latency_ms": (time.time() - start_time) * 1000,
                "error": "no_chain"
            }

        # Fill slots
        dialogue_memory = []
        fill_result = self.filler.fill_slots(
            chain_plan=chain_plan,
            world_state=world_state,
            dialogue_memory=dialogue_memory,
            query=query,
            context_vector=context_vector
        )

        if not fill_result.all_satisfied:
            return {
                "method": "chaining",
                "response": "",
                "quality_score": 0.0,
                "latency_ms": (time.time() - start_time) * 1000,
                "error": "slots_not_filled"
            }

        # Render response
        response = self.linker.render_chain_text(chain_plan, fill_result.bindings)

        # Quality scoring
        quality_score = self.score_response_quality(response, query, emotion)

        return {
            "method": "chaining",
            "response": response,
            "quality_score": quality_score,
            "latency_ms": (time.time() - start_time) * 1000,
            "chain_length": len(chain_plan.steps),
            "slots_filled": len(fill_result.bindings)
        }

    def synthesize_with_pattern_engine(self, query: str, emotion: str = "neutral",
                                     trust: float = 50.0) -> Dict[str, Any]:
        """Synthesize response using traditional PatternEngine."""
        start_time = time.time()

        # Get knowledge texts
        cloud_results = self.knowledge_cloud.lookup_multi(query, emotion=emotion, trust=trust)

        if not cloud_results:
            return {
                "method": "pattern_engine",
                "response": "",
                "quality_score": 0.0,
                "latency_ms": (time.time() - start_time) * 1000,
                "error": "no_results"
            }

        # Extract raw materials
        knowledge_texts = [r.get("response", "") for r in cloud_results]
        voice_samples = []  # Would come from character profiles
        temperature = 0.7

        try:
            # Use pattern engine synthesis
            response = self.pattern_engine.synthesize_knowledge(
                knowledge_texts=knowledge_texts,
                voice_texts=voice_samples,
                query=query,
                temperature=temperature
            )

            if not response or len(response.split()) < 3:
                return {
                    "method": "pattern_engine",
                    "response": "",
                    "quality_score": 0.0,
                    "latency_ms": (time.time() - start_time) * 1000,
                    "error": "synthesis_failed"
                }

            quality_score = self.score_response_quality(response, query, emotion)

            return {
                "method": "pattern_engine",
                "response": response,
                "quality_score": quality_score,
                "latency_ms": (time.time() - start_time) * 1000
            }

        except Exception as e:
            return {
                "method": "pattern_engine",
                "response": "",
                "quality_score": 0.0,
                "latency_ms": (time.time() - start_time) * 1000,
                "error": str(e)
            }

    def score_response_quality(self, response: str, query: str, emotion: str) -> float:
        """Score response quality on coherence, relevance, and engagement."""
        if not response:
            return 0.0

        score = 0.0
        words = response.split()

        # Length bonus (prefer substantial responses)
        if len(words) >= 10:
            score += 1.0
        elif len(words) >= 5:
            score += 0.5

        # Multi-sentence bonus
        sentences = response.split('.')
        if len(sentences) >= 2:
            score += 1.0
        elif len(sentences) >= 3:
            score += 0.5

        # Query relevance (simple keyword matching)
        query_words = set(query.lower().split())
        response_words = set(response.lower().split())
        overlap = len(query_words.intersection(response_words))
        relevance = min(overlap / max(len(query_words), 1), 1.0)
        score += relevance

        # Emotion-appropriate language
        emotion_indicators = {
            "afraid": ["fear", "danger", "scary", "terrifying", "caution"],
            "excited": ["amazing", "wonderful", "exciting", "thrilling"],
            "curious": ["interesting", "mysterious", "wonder", "learn"],
            "angry": ["furious", "outraged", "terrible", "unacceptable"]
        }

        emotion_words = emotion_indicators.get(emotion, [])
        emotion_matches = sum(1 for word in emotion_words if word in response.lower())
        if emotion_matches > 0:
            score += 0.5

        # Coherence (avoid repetition, nonsensical phrases)
        if "..." not in response and response.count(",") <= 2:
            score += 0.5

        return min(score, 5.0)  # Cap at 5.0

    def run_test_suite(self, test_queries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run comprehensive A/B test suite."""
        results = {
            "chaining": [],
            "pattern_engine": [],
            "summary": {}
        }

        print("Running A/B test suite...")

        for i, test_case in enumerate(test_queries):
            query = test_case["query"]
            emotion = test_case.get("emotion", "neutral")
            trust = test_case.get("trust", 50.0)

            print(f"  Test {i+1}/{len(test_queries)}: '{query}' ({emotion})")

            # Run both methods
            chaining_result = self.synthesize_with_chaining(query, emotion, trust)
            pattern_result = self.synthesize_with_pattern_engine(query, emotion, trust)

            results["chaining"].append(chaining_result)
            results["pattern_engine"].append(pattern_result)

            # Show results
            print(f"    Chaining: {chaining_result['quality_score']:.1f} ({chaining_result['latency_ms']:.0f}ms)")
            print(f"    Pattern:  {pattern_result['quality_score']:.1f} ({pattern_result['latency_ms']:.0f}ms)")

            if chaining_result["response"]:
                print(f"    Chain: '{chaining_result['response'][:60]}...'")
            if pattern_result["response"]:
                print(f"    Pattern: '{pattern_result['response'][:60]}...'")

        # Calculate summary statistics
        results["summary"] = self.calculate_summary(results)
        return results

    def calculate_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate summary statistics for the test run."""
        summary = {}

        for method in ["chaining", "pattern_engine"]:
            method_results = [r for r in results[method] if r["quality_score"] > 0]

            if method_results:
                quality_scores = [r["quality_score"] for r in method_results]
                latencies = [r["latency_ms"] for r in method_results]

                summary[method] = {
                    "avg_quality": round(statistics.mean(quality_scores), 2),
                    "median_quality": round(statistics.median(quality_scores), 2),
                    "avg_latency_ms": round(statistics.mean(latencies), 1),
                    "success_rate": round(len(method_results) / len(results[method]), 3),
                    "total_tests": len(results[method])
                }
            else:
                summary[method] = {
                    "avg_quality": 0.0,
                    "median_quality": 0.0,
                    "avg_latency_ms": 0.0,
                    "success_rate": 0.0,
                    "total_tests": len(results[method])
                }

        # Comparison metrics
        chaining_qual = summary["chaining"]["avg_quality"]
        pattern_qual = summary["pattern_engine"]["avg_quality"]

        summary["comparison"] = {
            "quality_improvement": round(chaining_qual - pattern_qual, 2),
            "latency_ratio": round(summary["chaining"]["avg_latency_ms"] / max(summary["pattern_engine"]["avg_latency_ms"], 1), 2)
        }

        return summary

def main():
    """Run A/B test suite."""
    # Load knowledge cloud
    print("Loading Knowledge Cloud...")
    cloud = KnowledgeCloud('data/knowledge_cloud')

    # Create tester
    tester = ABTester(cloud)

    # Test queries representing common NPC interactions
    test_queries = [
        {"query": "Tell me about the dragon", "emotion": "curious"},
        {"query": "Is it safe to travel the Northern Road?", "emotion": "afraid"},
        {"query": "How do I become a merchant?", "emotion": "excited"},
        {"query": "What's the best armor for fighting orcs?", "emotion": "determined"},
        {"query": "Where can I buy potions?", "emotion": "neutral"},
        {"query": "What happened to the missing caravans?", "emotion": "curious"},
        {"query": "Tell me about Duke Aldric", "emotion": "interested"},
        {"query": "Are there any quests available?", "emotion": "excited"},
        {"query": "What's the history of Ironhaven?", "emotion": "curious"},
        {"query": "How does magic work here?", "emotion": "wondering"},
        {"query": "Is the forest dangerous?", "emotion": "afraid"},
        {"query": "Where can I find work?", "emotion": "neutral"},
        {"query": "Tell me about the elves", "emotion": "curious"},
        {"query": "How do I craft weapons?", "emotion": "interested"},
        {"query": "What's in the Blackhollow?", "emotion": "afraid"}
    ]

    # Run tests
    results = tester.run_test_suite(test_queries)

    # Print summary
    print("\n" + "="*60)
    print("A/B TEST RESULTS")
    print("="*60)

    summary = results["summary"]
    print(f"Chaining Method:")
    print(f"  Avg Quality: {summary['chaining']['avg_quality']}")
    print(f"  Median Quality: {summary['chaining']['median_quality']}")
    print(f"  Avg Latency: {summary['chaining']['avg_latency_ms']}ms")
    print(f"  Success Rate: {summary['chaining']['success_rate']*100:.1f}%")

    print(f"\nPattern Engine Method:")
    print(f"  Avg Quality: {summary['pattern_engine']['avg_quality']}")
    print(f"  Median Quality: {summary['pattern_engine']['median_quality']}")
    print(f"  Avg Latency: {summary['pattern_engine']['avg_latency_ms']}ms")
    print(f"  Success Rate: {summary['pattern_engine']['success_rate']*100:.1f}%")

    print(f"\nComparison:")
    print(f"  Quality Improvement: {summary['comparison']['quality_improvement']}")
    print(f"  Latency Ratio: {summary['comparison']['latency_ratio']:.2f}x")

    # Save detailed results
    output_path = "data/ab_test_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nDetailed results saved to {output_path}")

    # Recommendation
    if summary['comparison']['quality_improvement'] > 0.3:
        print("\n✅ RECOMMENDATION: Chaining shows significant quality improvement!")
        print("   Consider deploying chaining as the primary synthesis method.")
    elif summary['comparison']['quality_improvement'] > 0:
        print("\n⚖️  RECOMMENDATION: Chaining shows marginal improvement.")
        print("   Keep both methods available with chaining as option.")
    else:
        print("\n❌ RECOMMENDATION: Pattern Engine performs better.")
        print("   Continue using Pattern Engine, investigate chaining issues.")

if __name__ == "__main__":
    main()
