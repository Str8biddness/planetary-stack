#!/usr/bin/env python3
"""
UNPC Engine - Pattern Generator
Generates massive synthetic pattern datasets for character genomes
Input: Character archetype (description, traits, backstory)
Output: Complete patterns.json genome for left hemisphere loading
"""

import json
import random
from typing import List, Dict, Any
from datetime import datetime, timezone

class PatternGenerator:
    def __init__(self):
        self.pattern_id_counter = 1
        self.confidence_base = 0.85
        
    def generate_character_genome(self, archetype: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes character archetype and generates complete pattern genome.
        
        Args:
            archetype: {
                'name': str,
                'role': str (e.g., 'software_engineer'),
                'age': int,
                'backstory': str,
                'traits': List[str],
                'expertise': List[str],
                'personality': str
            }
        
        Returns:
            Complete patterns.json genome with synthetic + generic patterns
        """
        character_id = archetype['name'].lower().replace(' ', '_')
        hemisphere_id = random.randint(100, 999)  # Unique ID
        
        # Generate massive pattern sets
        synthetic_patterns = []
        
        # 1. EXPERTISE PATTERNS (technical/domain knowledge)
        synthetic_patterns.extend(
            self._generate_expertise_patterns(archetype['expertise'], archetype['role'])
        )
        
        # 2. BACKSTORY PATTERNS (life history, experiences)
        synthetic_patterns.extend(
            self._generate_backstory_patterns(archetype['backstory'], archetype['age'])
        )
        
        # 3. PERSONALITY PATTERNS (trait-based responses)
        synthetic_patterns.extend(
            self._generate_personality_patterns(archetype['traits'], archetype['personality'])
        )
        
        # 4. CONTEXTUAL PATTERNS (situational responses)
        synthetic_patterns.extend(
            self._generate_contextual_patterns(archetype['role'])
        )
        
        # 5. OPINION PATTERNS (beliefs, preferences)
        synthetic_patterns.extend(
            self._generate_opinion_patterns(archetype)
        )
        
        # Generic patterns (universal greetings, acknowledgments)
        generic_patterns = self._generate_generic_patterns(character_id, archetype['personality'])
        
        genome = {
            'character_id': character_id,
            'hemisphere_id': hemisphere_id,
            'pattern_schema': 'ppbrs_v2',
            'synthetic_patterns': synthetic_patterns,
            'generic_patterns': generic_patterns,
            'fallback': f"I'm {archetype['name']}, a {archetype['role']}. Could you rephrase that?",
            'meta': {
                'archetype': archetype['role'],
                'generated_by': 'UNPC_Engine_v1',
                'pattern_count': len(synthetic_patterns),
                'created': datetime.now(timezone.utc).isoformat() + 'Z'
            },
            'version': '1.0.0'
        }
        
        return genome
    
    def _generate_expertise_patterns(self, expertise: List[str], role: str) -> List[Dict]:
        """
        Generate patterns for technical/domain expertise.
        Expands each expertise area into 10-20 specific patterns.
        """
        patterns = []
        
        for domain in expertise:
            # Generate variations of expertise questions
            base_triggers = [
                f"how do you {domain.replace('_', ' ')}",
                f"explain {domain.replace('_', ' ')}",
                f"what's your approach to {domain.replace('_', ' ')}",
                f"best practices for {domain.replace('_', ' ')}",
                f"help with {domain.replace('_', ' ')}",
                f"debug {domain.replace('_', ' ')}",
                f"{domain.replace('_', ' ')} issue",
                f"{domain.replace('_', ' ')} problem"
            ]
            
            # Create multiple patterns per expertise domain
            for i, trigger_set in enumerate([base_triggers[j:j+3] for j in range(0, len(base_triggers), 3)]):
                pattern_id = f"SP_EXPERT_{self.pattern_id_counter:04d}"
                self.pattern_id_counter += 1
                
                patterns.append({
                    'id': pattern_id,
                    'trigger': trigger_set,
                    'response_template': f"Based on my experience in {domain}, I typically approach this by: [expertise-specific methodology]. In my work as a {role}, I've found this to be effective.",
                    'confidence': round(self.confidence_base + random.uniform(0.05, 0.15), 2),
                    'domain': domain
                })
        
        return patterns
    
    def _generate_backstory_patterns(self, backstory: str, age: int) -> List[Dict]:
        """
        Generate patterns from character backstory and life history.
        Creates realistic biographical patterns with temporal context.
        """
        patterns = []
        
        # Parse backstory into key life events
        life_events = self._parse_backstory(backstory)
        
        for event in life_events:
            triggers = [
                f"tell me about your {event['category']}",
                f"what about your {event['category']}",
                f"your {event['category']}",
                f"have you {event['verb']}",
                f"when did you {event['verb']}"
            ]
            
            pattern_id = f"SP_STORY_{self.pattern_id_counter:04d}"
            self.pattern_id_counter += 1
            
            patterns.append({
                'id': pattern_id,
                'trigger': triggers[:3],  # Use first 3 variations
                'response_template': event['narrative'],
                'confidence': round(self.confidence_base + 0.08, 2),
                'domain': 'backstory',
                'temporal_context': event.get('timeframe', 'past')
            })
        
        # Age-based patterns
        age_triggers = ["how old are you", "your age", "age"]
        patterns.append({
            'id': f"SP_STORY_{self.pattern_id_counter:04d}",
            'trigger': age_triggers,
            'response_template': f"I'm {age} years old.",
            'confidence': 0.99,
            'domain': 'personal_info'
        })
        self.pattern_id_counter += 1
        
        return patterns
    
    def _generate_personality_patterns(self, traits: List[str], personality: str) -> List[Dict]:
        """
        Generate patterns that reflect character personality traits.
        Maps traits to response behaviors.
        """
        patterns = []
        
        trait_response_map = {
            'analytical': ['methodical', 'logical', 'data-driven'],
            'creative': ['innovative', 'outside-the-box', 'imaginative'],
            'empathetic': ['understanding', 'supportive', 'compassionate'],
            'direct': ['straightforward', 'honest', 'blunt'],
            'humorous': ['witty', 'lighthearted', 'playful'],
            'serious': ['focused', 'professional', 'no-nonsense'],
            'optimistic': ['positive', 'hopeful', 'encouraging'],
            'cautious': ['careful', 'risk-averse', 'prudent']
        }
        
        for trait in traits:
            if trait in trait_response_map:
                modifiers = trait_response_map[trait]
                
                triggers = [
                    f"what's your personality",
                    f"describe yourself",
                    f"what are you like",
                    f"tell me about yourself"
                ]
                
                pattern_id = f"SP_TRAIT_{self.pattern_id_counter:04d}"
                self.pattern_id_counter += 1
                
                patterns.append({
                    'id': pattern_id,
                    'trigger': triggers,
                    'response_template': f"I'd say I'm quite {trait}. People often describe me as {modifiers[0]} and {modifiers[1]}.",
                    'confidence': 0.92,
                    'domain': 'personality'
                })
        
        return patterns
    
    def _generate_contextual_patterns(self, role: str) -> List[Dict]:
        """
        Generate situational/contextual patterns based on role.
        """
        patterns = []
        
        # Role-specific situational patterns
        role_contexts = {
            'software_engineer': [
                ('work on a project', 'I usually start by breaking down requirements, then prototype core functionality'),
                ('code review', 'I focus on readability, edge cases, and performance bottlenecks'),
                ('debug an issue', 'I reproduce the bug, check logs, use breakpoints, and trace the execution flow'),
                ('choose a tech stack', 'I evaluate based on scalability, team expertise, and ecosystem maturity')
            ],
            'doctor': [
                ('diagnose a patient', 'I take a thorough history, examine symptoms, order relevant tests'),
                ('treat a condition', 'I consider evidence-based protocols and patient-specific factors'),
                ('handle an emergency', 'I prioritize stabilization, ABCs, and rapid assessment')
            ],
            'teacher': [
                ('teach a difficult concept', 'I use analogies, break it into smaller parts, and check for understanding'),
                ('handle a struggling student', 'I identify gaps, provide additional support, and adjust my approach'),
                ('plan a lesson', 'I set clear objectives, engage multiple learning styles, and build in assessment')
            ]
        }
        
        contexts = role_contexts.get(role, [])
        for situation, response in contexts:
            triggers = [
                f"how do you {situation}",
                f"what do you do when you {situation}",
                f"your approach to {situation}"
            ]
            
            pattern_id = f"SP_CONTEXT_{self.pattern_id_counter:04d}"
            self.pattern_id_counter += 1
            
            patterns.append({
                'id': pattern_id,
                'trigger': triggers,
                'response_template': response,
                'confidence': 0.91,
                'domain': 'situational'
            })
        
        return patterns
    
    def _generate_opinion_patterns(self, archetype: Dict[str, Any]) -> List[Dict]:
        """
        Generate patterns for character opinions, beliefs, preferences.
        """
        patterns = []
        
        # Generate opinion triggers based on role
        opinion_topics = [
            'favorite programming language',
            'best practice',
            'industry trends',
            'biggest challenge',
            'what motivates you',
            'career goals',
            'work philosophy'
        ]
        
        for topic in opinion_topics:
            triggers = [
                f"what's your {topic}",
                f"your {topic}",
                f"tell me about your {topic}"
            ]
            
            pattern_id = f"SP_OPINION_{self.pattern_id_counter:04d}"
            self.pattern_id_counter += 1
            
            patterns.append({
                'id': pattern_id,
                'trigger': triggers,
                'response_template': f"Regarding {topic}, I believe [opinion tied to {archetype['personality']} personality and {archetype['role']} experience].",
                'confidence': 0.88,
                'domain': 'opinions'
            })
        
        return patterns
    
    def _generate_generic_patterns(self, character_id: str, personality: str) -> List[Dict]:
        """
        Generate universal greeting/acknowledgment patterns.
        """
        greeting_style = {
            'warm': "Hello! It's great to meet you.",
            'professional': "Hello. How can I assist you?",
            'casual': "Hey there!",
            'formal': "Greetings. How may I help you today?"
        }
        
        thanks_style = {
            'warm': "You're very welcome! Happy to help.",
            'professional': "You're welcome.",
            'casual': "No problem!",
            'formal': "It is my pleasure to assist."
        }
        
        style = personality if personality in greeting_style else 'professional'
        
        return [
            {
                'id': 'GP_GENERIC_001',
                'trigger': ['hello', 'hi', 'hey'],
                'response_template': greeting_style[style],
                'confidence': 0.99
            },
            {
                'id': 'GP_GENERIC_002',
                'trigger': ['thank you', 'thanks'],
                'response_template': thanks_style[style],
                'confidence': 0.99
            },
            {
                'id': 'GP_GENERIC_003',
                'trigger': ['bye', 'goodbye', 'see you'],
                'response_template': 'Goodbye! Take care.',
                'confidence': 0.99
            }
        ]
    
    def _parse_backstory(self, backstory: str) -> List[Dict]:
        """
        Parse backstory text into structured life events.
        This is a simplified parser - production version would use NLP.
        """
        # For now, split by sentences and create event structures
        sentences = backstory.split('. ')
        events = []
        
        for i, sentence in enumerate(sentences):
            if sentence.strip():
                events.append({
                    'category': f'experience_{i}',
                    'verb': 'experience this',
                    'narrative': sentence.strip(),
                    'timeframe': 'past'
                })
        
        return events


# CLI Interface
def main():
    """
    Command-line interface for generating character genomes.
    
    Usage:
        python pattern_generator.py --archetype archetype.json --output character_name.json
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='UNPC Engine - Generate character pattern genomes')
    parser.add_argument('--archetype', required=True, help='Path to archetype JSON input')
    parser.add_argument('--output', required=True, help='Output path for generated patterns.json')
    parser.add_argument('--expand', type=int, default=100, help='Pattern expansion factor (default: 100)')
    
    args = parser.parse_args()
    
    # Load archetype
    with open(args.archetype, 'r') as f:
        archetype = json.load(f)
    
    # Generate genome
    generator = PatternGenerator()
    genome = generator.generate_character_genome(archetype)
    
    # Save to output
    with open(args.output, 'w') as f:
        json.dump(genome, f, indent=2)
    
    print(f"Generated {len(genome['synthetic_patterns'])} synthetic patterns for {archetype['name']}")
    print(f"Genome saved to: {args.output}")
    print(f"Hemisphere ID: {genome['hemisphere_id']}")


if __name__ == '__main__':
    main()