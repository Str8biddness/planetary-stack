#!/usr/bin/env python3
"""
Synthesus Character Genome Validator
Validates a character directory against the official JSON schemas.

Usage:
    python validate_character.py <character_dir>
    python validate_character.py characters/garen
    python validate_character.py --all                    # validate all characters
    python validate_character.py --all --fix-registry     # also rebuild registry.json

Exit codes:
    0 = all valid
    1 = validation errors found
    2 = missing required files
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Schema Definitions (inlined for zero-dependency usage) ──

REQUIRED_BIO_FIELDS = ["character_id", "name", "version", "type", "status", "description", "persona"]
REQUIRED_PERSONA_FIELDS = ["tone", "style"]
VALID_STATUSES = {"active", "draft", "deprecated", "testing"}
VALID_ENTITY_TYPES = {"person", "place", "item", "faction", "event", "concept"}
VALID_DEPTHS = {"intimate", "familiar", "acquainted", "rumor", "unknown"}
VALID_ARCHETYPES = {"merchant", "guard", "innkeeper", "scholar", "healer", "custom"}
VALID_INTENTS = {
    "song", "joke", "favorite", "opinion", "personal", "philosophical",
    "compliment_response", "insult_response", "creative_request", "rumor", "advice"
}
CHAR_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
PATTERN_ID_RE = re.compile(r"^[A-Z]{2}_[A-Z]+_\d{3}$")
MATCH_QUALITY_THRESHOLD = 0.55


class ValidationResult:
    def __init__(self, char_id: str):
        self.char_id = char_id
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.files_found: List[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    def add_info(self, msg: str):
        self.info.append(msg)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        status = "✅ VALID" if self.valid else "❌ INVALID"
        lines = [f"\n{'='*60}", f"  {self.char_id}: {status}", f"{'='*60}"]
        lines.append(f"  Files: {', '.join(self.files_found) or 'none'}")
        if self.info:
            lines.append(f"\n  ℹ️  Info:")
            for i in self.info:
                lines.append(f"     • {i}")
        if self.warnings:
            lines.append(f"\n  ⚠️  Warnings:")
            for w in self.warnings:
                lines.append(f"     • {w}")
        if self.errors:
            lines.append(f"\n  ❌ Errors:")
            for e in self.errors:
                lines.append(f"     • {e}")
        return "\n".join(lines)


def _load_json(path: Path) -> Optional[Dict]:
    """Load and parse a JSON file, return None on failure."""
    try:
        with open(path) as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        return None
    except FileNotFoundError:
        return None


def validate_bio(data: Dict, char_dir_name: str, result: ValidationResult) -> Dict:
    """Validate bio.json and return the parsed data."""
    # Required fields
    for field in REQUIRED_BIO_FIELDS:
        if field not in data:
            result.error(f"bio.json: missing required field '{field}'")

    # character_id consistency
    char_id = data.get("character_id", "")
    if char_id != char_dir_name:
        result.error(f"bio.json: character_id '{char_id}' doesn't match directory name '{char_dir_name}'")

    if char_id and not CHAR_ID_PATTERN.match(char_id):
        result.error(f"bio.json: character_id '{char_id}' must be lowercase alphanumeric + underscore, 2-32 chars")

    # Legacy 'id' field consistency
    if "id" in data and data["id"] != char_id:
        result.warn(f"bio.json: 'id' field ('{data['id']}') differs from 'character_id' ('{char_id}'). Use character_id.")

    # Version format
    version = data.get("version", "")
    if version and not VERSION_PATTERN.match(version):
        result.error(f"bio.json: version '{version}' must be semver (e.g., '1.0.0')")

    # Status
    status = data.get("status", "")
    if status and status not in VALID_STATUSES:
        result.error(f"bio.json: status '{status}' not in {VALID_STATUSES}")

    # Persona validation
    persona = data.get("persona", {})
    if isinstance(persona, dict):
        for field in REQUIRED_PERSONA_FIELDS:
            if field not in persona:
                result.error(f"bio.json: persona missing required field '{field}'")
    elif "persona" in data:
        result.error("bio.json: 'persona' must be an object")

    # Name checks
    name = data.get("name", "")
    if not name:
        result.error("bio.json: 'name' is empty")
    elif len(name) > 64:
        result.warn(f"bio.json: 'name' is {len(name)} chars (max recommended: 64)")

    # Description length
    desc = data.get("description", "")
    if len(desc) < 10:
        result.warn("bio.json: 'description' is very short (< 10 chars)")

    # Archetype hint
    archetype = data.get("archetype", "")
    if archetype and archetype not in VALID_ARCHETYPES:
        result.warn(f"bio.json: archetype '{archetype}' not in built-in set {VALID_ARCHETYPES}")

    # Hemisphere ID
    hid = data.get("hemisphere_id")
    if hid is not None:
        if not isinstance(hid, int) or hid < 1 or hid > 255:
            result.error(f"bio.json: hemisphere_id must be 1-255, got {hid}")
    else:
        result.warn("bio.json: no hemisphere_id set (needed for kernel routing)")

    # Stats
    domains = data.get("knowledge_domains", [])
    result.add_info(f"Name: {name}")
    result.add_info(f"Type: {data.get('type', '?')}")
    result.add_info(f"Domains: {', '.join(domains) if domains else 'none'}")

    return data


def validate_patterns(data: Dict, bio_data: Dict, result: ValidationResult) -> None:
    """Validate patterns.json against the schema and bio.json."""
    synthetic = data.get("synthetic_patterns", [])
    generic = data.get("generic_patterns", [])

    if not isinstance(synthetic, list):
        result.error("patterns.json: 'synthetic_patterns' must be an array")
        return
    if not isinstance(generic, list):
        result.error("patterns.json: 'generic_patterns' must be an array")
        return

    if not data.get("fallback"):
        result.warn("patterns.json: no 'fallback' text defined")

    all_patterns = synthetic + generic
    seen_ids = set()
    bio_domains = set(bio_data.get("knowledge_domains", []))

    for i, pat in enumerate(all_patterns):
        pat_id = pat.get("id", f"[index {i}]")

        # ID format
        if "id" not in pat:
            result.error(f"patterns.json: pattern at index {i} missing 'id'")
        elif pat_id in seen_ids:
            result.error(f"patterns.json: duplicate pattern ID '{pat_id}'")
        else:
            seen_ids.add(pat_id)
            if not PATTERN_ID_RE.match(pat_id):
                result.warn(f"patterns.json: '{pat_id}' doesn't match format XX_NAME_NNN")

        # Required fields
        if "trigger" not in pat:
            result.error(f"patterns.json: '{pat_id}' missing 'trigger'")
        else:
            triggers = pat["trigger"]
            if isinstance(triggers, str):
                triggers = [triggers]
            if not triggers:
                result.error(f"patterns.json: '{pat_id}' has empty trigger list")

        if "response_template" not in pat:
            result.error(f"patterns.json: '{pat_id}' missing 'response_template'")

        conf = pat.get("confidence", 0)
        if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
            result.error(f"patterns.json: '{pat_id}' confidence must be 0-1, got {conf}")
        elif conf < MATCH_QUALITY_THRESHOLD:
            result.warn(f"patterns.json: '{pat_id}' confidence {conf} < threshold {MATCH_QUALITY_THRESHOLD} — will never fire")

        # Domain cross-reference
        domain = pat.get("domain")
        if domain and bio_domains and domain not in bio_domains:
            result.warn(f"patterns.json: '{pat_id}' domain '{domain}' not in bio.knowledge_domains")

    result.add_info(f"Patterns: {len(synthetic)} synthetic, {len(generic)} generic")


def validate_knowledge(data: Dict, result: ValidationResult) -> None:
    """Validate knowledge.json against the schema."""
    entities = data.get("entities", {})
    if not isinstance(entities, dict):
        result.error("knowledge.json: 'entities' must be an object")
        return

    type_counts = {}
    for eid, edata in entities.items():
        if not isinstance(edata, dict):
            result.error(f"knowledge.json: entity '{eid}' must be an object")
            continue

        # Required fields
        for field in ["entity_type", "display_name", "description"]:
            if field not in edata:
                result.error(f"knowledge.json: entity '{eid}' missing required field '{field}'")

        etype = edata.get("entity_type", "")
        if etype and etype not in VALID_ENTITY_TYPES:
            result.error(f"knowledge.json: entity '{eid}' has invalid type '{etype}'")
        type_counts[etype] = type_counts.get(etype, 0) + 1

        depth = edata.get("depth", "acquainted")
        if depth not in VALID_DEPTHS:
            result.error(f"knowledge.json: entity '{eid}' has invalid depth '{depth}'")

        # Description quality
        desc = edata.get("description", "")
        if len(desc) < 10:
            result.warn(f"knowledge.json: entity '{eid}' description is very short")

        # Related entity references
        related = edata.get("related_entities", [])
        for rel_id in related:
            if rel_id not in entities:
                result.warn(f"knowledge.json: entity '{eid}' references unknown entity '{rel_id}'")

        # Trust-gated validation
        if edata.get("secret_description") and "trust_threshold" not in edata:
            result.warn(f"knowledge.json: entity '{eid}' has secret_description but no trust_threshold (defaults to 70)")

    type_summary = ", ".join(f"{v} {k}" for k, v in sorted(type_counts.items()))
    result.add_info(f"Knowledge: {len(entities)} entities ({type_summary})")


def validate_personality(data: Dict, result: ValidationResult) -> None:
    """Validate personality.json against the schema."""
    responses = data.get("responses", {})
    if not isinstance(responses, dict):
        result.error("personality.json: 'responses' must be an object")
        return

    total_responses = 0
    intent_counts = {}

    for intent_str, resp_list in responses.items():
        if intent_str not in VALID_INTENTS:
            result.warn(f"personality.json: intent '{intent_str}' not in standard set — will need custom handling")

        if not isinstance(resp_list, list) or len(resp_list) == 0:
            result.error(f"personality.json: intent '{intent_str}' must have at least 1 response")
            continue

        for j, resp in enumerate(resp_list):
            if not isinstance(resp, dict):
                result.error(f"personality.json: {intent_str}[{j}] must be an object")
                continue
            if not resp.get("text"):
                result.error(f"personality.json: {intent_str}[{j}] missing 'text'")
            total_responses += 1

            # Count emotion variants
            variants = resp.get("emotion_variants", {})
            if variants and not isinstance(variants, dict):
                result.error(f"personality.json: {intent_str}[{j}] emotion_variants must be an object")

        intent_counts[intent_str] = len(resp_list)

    # Coverage check
    missing_intents = VALID_INTENTS - set(responses.keys())
    if missing_intents:
        result.warn(f"personality.json: missing intents: {', '.join(sorted(missing_intents))}")

    result.add_info(f"Personality: {len(responses)} intents, {total_responses} total responses")


def validate_character(char_dir: str) -> ValidationResult:
    """Validate a complete character genome directory."""
    char_path = Path(char_dir)
    char_name = char_path.name
    result = ValidationResult(char_name)

    if not char_path.is_dir():
        result.error(f"'{char_dir}' is not a directory")
        return result

    # ── bio.json (REQUIRED) ──
    bio_path = char_path / "bio.json"
    if not bio_path.exists():
        result.error("Missing required file: bio.json")
        return result

    result.files_found.append("bio.json")
    bio_data = _load_json(bio_path)
    if bio_data is None:
        result.error("bio.json: invalid JSON")
        return result

    bio_data = validate_bio(bio_data, char_name, result)

    # ── patterns.json (OPTIONAL but recommended) ──
    pat_path = char_path / "patterns.json"
    if pat_path.exists():
        result.files_found.append("patterns.json")
        pat_data = _load_json(pat_path)
        if pat_data is None:
            result.error("patterns.json: invalid JSON")
        else:
            validate_patterns(pat_data, bio_data, result)
    else:
        result.warn("No patterns.json — character will only use cognitive fallback modules")

    # ── knowledge.json (OPTIONAL) ──
    kg_path = char_path / "knowledge.json"
    if kg_path.exists():
        result.files_found.append("knowledge.json")
        kg_data = _load_json(kg_path)
        if kg_data is None:
            result.error("knowledge.json: invalid JSON")
        else:
            validate_knowledge(kg_data, result)
    else:
        result.add_info("No knowledge.json — Knowledge Graph module will be empty")

    # ── personality.json (OPTIONAL) ──
    pers_path = char_path / "personality.json"
    if pers_path.exists():
        result.files_found.append("personality.json")
        pers_data = _load_json(pers_path)
        if pers_data is None:
            result.error("personality.json: invalid JSON")
        else:
            validate_personality(pers_data, result)
    else:
        result.add_info(f"No personality.json — will use built-in '{bio_data.get('archetype', bio_data.get('type', 'guard'))}' archetype")

    return result


def rebuild_registry(characters_dir: str) -> Dict:
    """Auto-rebuild registry.json from character directories."""
    char_base = Path(characters_dir)
    characters = []
    hemisphere_map = {}

    for subdir in sorted(char_base.iterdir()):
        if not subdir.is_dir() or subdir.name in ("schema",):
            continue
        bio_path = subdir / "bio.json"
        if not bio_path.exists():
            continue
        bio = _load_json(bio_path)
        if bio is None:
            continue

        char_id = bio.get("character_id", subdir.name)
        hid = bio.get("hemisphere_id")
        pat_path = subdir / "patterns.json"
        pat_count = 0
        if pat_path.exists():
            pdata = _load_json(pat_path)
            if pdata:
                pat_count = len(pdata.get("synthetic_patterns", [])) + len(pdata.get("generic_patterns", []))

        # Determine genome completeness
        files = []
        for fname in ["bio.json", "patterns.json", "knowledge.json", "personality.json"]:
            if (subdir / fname).exists():
                files.append(fname)

        entry = {
            "character_id": char_id,
            "display_name": bio.get("name", bio.get("display_name", char_id)),
            "version": bio.get("version", "0.0.0"),
            "hemisphere_id": hid,
            "type": bio.get("type", "unknown"),
            "status": bio.get("status", "draft"),
            "description": bio.get("description", ""),
            "path": f"characters/{subdir.name}/",
            "knowledge_domains": bio.get("knowledge_domains", []),
            "pattern_count": pat_count,
            "genome_files": files,
            "created": bio.get("created", ""),
        }
        characters.append(entry)
        if hid is not None:
            hemisphere_map[str(hid)] = char_id

    # Find next available hemisphere ID
    used_ids = {int(k) for k in hemisphere_map.keys()}
    next_id = max(used_ids, default=0) + 10
    # Round up to next 10
    next_id = ((next_id + 9) // 10) * 10

    registry = {
        "version": "2.0.0",
        "schema_version": "character_genome_v2",
        "description": "Synthesus Character Registry — Auto-generated from character directories",
        "hemisphere_allocation": {
            **{str(k): v for k, v in sorted(hemisphere_map.items(), key=lambda x: int(x[0]))},
            "next_available": next_id,
            "marketplace_range": "100-199",
            "enterprise_range": "200-255"
        },
        "characters": characters
    }
    return registry


def main():
    parser = argparse.ArgumentParser(description="Validate Synthesus character genomes")
    parser.add_argument("char_dir", nargs="?", help="Character directory to validate")
    parser.add_argument("--all", action="store_true", help="Validate all characters")
    parser.add_argument("--fix-registry", action="store_true", help="Rebuild registry.json from character dirs")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Find the characters root
    script_dir = Path(__file__).parent
    if (script_dir / "characters").is_dir():
        chars_root = script_dir / "characters"
    elif script_dir.name == "characters":
        chars_root = script_dir
    else:
        chars_root = Path("characters")

    results = []

    if args.all:
        for subdir in sorted(chars_root.iterdir()):
            if subdir.is_dir() and subdir.name != "schema" and (subdir / "bio.json").exists():
                results.append(validate_character(str(subdir)))
    elif args.char_dir:
        results.append(validate_character(args.char_dir))
    else:
        parser.print_help()
        sys.exit(0)

    if args.json:
        output = []
        for r in results:
            output.append({
                "character_id": r.char_id,
                "valid": r.valid,
                "files": r.files_found,
                "errors": r.errors,
                "warnings": r.warnings,
                "info": r.info,
            })
        print(json.dumps(output, indent=2))
    else:
        for r in results:
            print(r.summary())

        # Final summary
        total = len(results)
        valid = sum(1 for r in results if r.valid)
        invalid = total - valid
        print(f"\n{'='*60}")
        print(f"  TOTAL: {total} characters | ✅ {valid} valid | ❌ {invalid} invalid")
        print(f"{'='*60}\n")

    # Rebuild registry if requested
    if args.fix_registry:
        registry = rebuild_registry(str(chars_root))
        registry_path = chars_root / "registry.json"
        with open(registry_path, "w") as f:
            json.dump(registry, f, indent=2)
        print(f"  📝 Registry rebuilt: {registry_path} ({len(registry['characters'])} characters)")

    # Exit code
    all_valid = all(r.valid for r in results)
    sys.exit(0 if all_valid else 1)


if __name__ == "__main__":
    main()
