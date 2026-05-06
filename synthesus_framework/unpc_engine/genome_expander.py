#!/usr/bin/env python3
"""
UNPC Engine - Genome Expander with LLM Integration
Uses the right hemisphere (TinyLlama/LLM) to massively expand pattern genomes.
Input: Base patterns.json (100-500 patterns)
Output: Expanded patterns.json (5000-50,000 patterns)
"""

import json
import requests
from typing import List, Dict, Any
import sys

class GenomeExpander:
    def __init__(self, llm_endpoint: str = "http://localhost:5000/api/generate"):
        """
        Initialize genome expander with LLM endpoint.
        
        Args:
            llm_endpoint: URL to Synthesus right hemisphere API
        """
        self.llm_endpoint = llm_endpoint
        self.expansion_factor = 10  # Each pattern → 10 variations
        
    def expand_genome(self, base_genome: Dict[str, Any], target_count: int = 5000) -> Dict[str, Any]:
        """
        Expand a base genome using LLM to generate pattern variations.
        
        Args:
            base_genome: Basic patterns.json from PatternGenerator
            target_count: Target number of synthetic patterns
        
        Returns:
            Massively expanded patterns.json
        """
        print(f"Starting genome expansion for character: {base_genome['character_id']}")
        print(f"Base patterns: {len(base_genome['synthetic_patterns'])}")
        print(f"Target patterns: {target_count}")
        
        expanded_patterns = []
        
        # Keep original patterns
        expanded_patterns.extend(base_genome['synthetic_patterns'])
        
        # Expand each existing pattern using LLM
        for pattern in base_genome['synthetic_patterns']:
            variations = self._generate_pattern_variations(
                pattern, 
                base_genome['character_id'],
                num_variations=self.expansion_factor
            )
            expanded_patterns.extend(variations)
            
            if len(expanded_patterns) >= target_count:
                break
        
        # Update genome with expanded patterns
        expanded_genome = base_genome.copy()
        expanded_genome['synthetic_patterns'] = expanded_patterns[:target_count]
        expanded_genome['meta']['expansion_version'] = 'LLM_Expander_v1'
        expanded_genome['meta']['pattern_count'] = len(expanded_genome['synthetic_patterns'])
        expanded_genome['meta']['expanded_from'] = len(base_genome['synthetic_patterns'])
        
        print(f"Expansion complete: {len(expanded_genome['synthetic_patterns'])} patterns generated")
        
        return expanded_genome
    
    def _generate_pattern_variations(self, base_pattern: Dict, character_id: str, num_variations: int = 10) -> List[Dict]:
        """
        Use LLM to generate variations of a base pattern.
        
        Sends prompt to right hemisphere asking for N variations of the pattern
        with different triggers but similar semantic meaning.
        """
        variations = []
        
        # Build LLM prompt
        prompt = f"""
You are generating synthetic pattern variations for an NPC character named {character_id}.

Base Pattern:
Triggers: {base_pattern['trigger']}
Response: {base_pattern['response_template']}
Domain: {base_pattern.get('domain', 'general')}

Generate {num_variations} variations of this pattern with:
1. Different trigger phrasings (synonyms, rewordings, casual/formal variations)
2. Response templates with similar meaning but different wording
3. Maintain character consistency

Output as JSON array of patterns with 'trigger' and 'response_template' fields.
"""
        
        try:
            # Call right hemisphere LLM
            response = requests.post(
                self.llm_endpoint,
                json={'prompt': prompt, 'max_tokens': 2000},
                timeout=30
            )
            
            if response.status_code == 200:
                llm_output = response.json()
                generated_variations = self._parse_llm_output(llm_output.get('text', '{}'))
                
                # Format variations with proper IDs
                for i, var in enumerate(generated_variations[:num_variations]):
                    pattern_id = f"{base_pattern['id']}_VAR_{i:03d}"
                    variations.append({
                        'id': pattern_id,
                        'trigger': var.get('trigger', base_pattern['trigger']),
                        'response_template': var.get('response_template', base_pattern['response_template']),
                        'confidence': base_pattern['confidence'] - 0.05,  # Slightly lower confidence for variants
                        'domain': base_pattern.get('domain', 'general'),
                        'variant_of': base_pattern['id']
                    })
            else:
                print(f"LLM request failed: HTTP {response.status_code}")
                
        except Exception as e:
            print(f"Error generating variations for {base_pattern['id']}: {e}")
            # Fallback: generate simple variations programmatically
            variations = self._fallback_variations(base_pattern, num_variations)
        
        return variations
    
    def _parse_llm_output(self, llm_text: str) -> List[Dict]:
        """
        Parse LLM JSON output into pattern list.
        Handles malformed JSON gracefully.
        """
        try:
            # Try to parse as JSON
            data = json.loads(llm_text)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and 'patterns' in data:
                return data['patterns']
            else:
                return []
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code blocks
            if '```json' in llm_text:
                json_start = llm_text.find('```json') + 7
                json_end = llm_text.find('```', json_start)
                if json_end > json_start:
                    try:
                        return json.loads(llm_text[json_start:json_end])
                    except:
                        pass
            return []
    
    def _fallback_variations(self, base_pattern: Dict, num_variations: int) -> List[Dict]:
        """
        Generate simple pattern variations without LLM.
        Used as fallback when LLM is unavailable.
        """
        variations = []
        
        # Create basic trigger variations using synonyms
        trigger_variations = [
            base_pattern['trigger'],
            [t.replace(' ', '_') for t in base_pattern['trigger']],
            [t.upper() for t in base_pattern['trigger']],
            [f"can you {t}" for t in base_pattern['trigger']],
            [f"tell me {t}" for t in base_pattern['trigger']]
        ]
        
        for i, trig_set in enumerate(trigger_variations[:num_variations]):
            pattern_id = f"{base_pattern['id']}_VAR_{i:03d}"
            variations.append({
                'id': pattern_id,
                'trigger': trig_set if isinstance(trig_set, list) else [trig_set],
                'response_template': base_pattern['response_template'],
                'confidence': base_pattern['confidence'] - 0.05,
                'domain': base_pattern.get('domain', 'general'),
                'variant_of': base_pattern['id'],
                'fallback_generated': True
            })
        
        return variations


# CLI Interface
def main():
    """
    Command-line interface for genome expansion.
    
    Usage:
        python genome_expander.py --input base_genome.json --output expanded_genome.json --target 5000
    """
    import argparse
    
    parser = argparse.ArgumentParser(description='UNPC Engine - Expand character genomes using LLM')
    parser.add_argument('--input', required=True, help='Path to base patterns.json')
    parser.add_argument('--output', required=True, help='Output path for expanded genome')
    parser.add_argument('--target', type=int, default=5000, help='Target pattern count (default: 5000)')
    parser.add_argument('--llm-endpoint', default='http://localhost:5000/api/generate', help='LLM API endpoint')
    
    args = parser.parse_args()
    
    # Load base genome
    with open(args.input, 'r') as f:
        base_genome = json.load(f)
    
    # Expand using LLM
    expander = GenomeExpander(llm_endpoint=args.llm_endpoint)
    expanded_genome = expander.expand_genome(base_genome, target_count=args.target)
    
    # Save expanded genome
    with open(args.output, 'w') as f:
        json.dump(expanded_genome, f, indent=2)
    
    print(f"\nExpanded genome saved to: {args.output}")
    print(f"Base patterns: {expanded_genome['meta']['expanded_from']}")
    print(f"Final patterns: {len(expanded_genome['synthetic_patterns'])}")
    print(f"Expansion ratio: {len(expanded_genome['synthetic_patterns']) / expanded_genome['meta']['expanded_from']:.1f}x")


if __name__ == '__main__':
    main()