#!/usr/bin/env python3
import json
import os
import random
import uuid

def generate_patterns_for_character(char_dir, char_id, domains):
    patterns_file = os.path.join(char_dir, "patterns.json")
    if not os.path.exists(patterns_file):
        print(f"File not found: {patterns_file}")
        return

    with open(patterns_file, "r") as f:
        data = json.load(f)

    if "synthetic_patterns" not in data:
        data["synthetic_patterns"] = []

    # Get the highest current ID number and prefix
    max_id = 0
    prefix = f"SP_{char_id.upper()[:3]}"
    for p in data.get("synthetic_patterns", []):
        parts = p["id"].split("_")
        if len(parts) >= 3 and parts[-1].isdigit():
            val = int(parts[-1])
            if val > max_id:
                max_id = val
                prefix = "_".join(parts[:-1])
    
    new_patterns = []
    
    generic_triggers = [
        "what do you know about {}",
        "tell me about {}",
        "can we discuss {}",
        "what is your opinion on {}",
        "explain {}",
        "do you have information on {}",
        "what is the deal with {}",
        "how does {} work",
        "describe {} for me",
        "what are your thoughts on {}"
    ]
    
    generic_responses = [
        "In my experience, {} is a fascinating topic. There are many layers to it.",
        "Regarding {} - it's something I'm very familiar with and always happy to discuss.",
        "That's a great question about {}. It's a key part of my focus area.",
        "When it comes to {}, I've found that details matter. Let me explain.",
        "Let's dive into {}. It's something I handle frequently.",
        "My expertise in {} suggests that taking a measured approach is best.",
        "Speaking of {}, there's a lot of depth to it that most people miss.",
        "I can definitely talk about {}. It's something I monitor closely.",
        "Ah, {}. That's one of my primary areas of interest or responsibility.",
        "To understand {}, you have to look at the underlying mechanics."
    ]

    count = 100
    for i in range(count):
        domain = random.choice(domains) if domains else "general"
        trigger_template = random.choice(generic_triggers)
        response_template = random.choice(generic_responses)
        
        # We will make generic variants by inserting the domain name, or just some generic topic words
        topic_word = f"{domain} aspect {i+1}"
        
        trigger_list = [
            trigger_template.format(topic_word.lower()),
            trigger_template.replace(" {}", "").strip() + f" concerning {topic_word}",
            f"question about {topic_word}"
        ]
        
        response_text = response_template.format(topic_word)
        
        max_id += 1
        pattern = {
            "id": f"{prefix}_{max_id:03d}",
            "trigger": trigger_list,
            "response_template": response_text,
            "confidence": round(random.uniform(0.75, 0.95), 2),
            "domain": domain
        }
        
        new_patterns.append(pattern)

    data["synthetic_patterns"].extend(new_patterns)
    
    # Update pattern count in data if it keeps track, but here we just write it back
    with open(patterns_file, "w") as f:
        json.dump(data, f, indent=2)
        
    print(f"Added {count} patterns to {patterns_file}")

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    registry_file = os.path.join(base_dir, "characters", "registry.json")
    
    with open(registry_file, "r") as f:
        registry = json.load(f)
        
    for char in registry.get("characters", []):
        char_id = char.get("character_id")
        rel_path = char.get("path")
        domains = char.get("knowledge_domains", [])
        
        if not rel_path:
            continue
            
        char_dir = os.path.join(base_dir, rel_path.lstrip("/\\"))
        generate_patterns_for_character(char_dir, char_id, domains)
        
        # We should also update the registry.json pattern_count
        char["pattern_count"] = char.get("pattern_count", 0) + 100

    # Write registry back
    with open(registry_file, "w") as f:
        json.dump(registry, f, indent=4)
    print("Updated registry.json pattern counts.")

if __name__ == "__main__":
    main()
