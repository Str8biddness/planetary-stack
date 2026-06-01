"""Audit legacy template/fallback surfaces for Synthesus 5 Phase 6."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOT = REPO_ROOT / "packages"

SIGNATURES = (
    "response_template",
    "[fallback]",
    "[module]",
    "Handled:",
    "No route matched",
    "fallback_text",
    "_generate_fallback",
    "prompt_template",
)


@dataclass(frozen=True)
class SurfaceClassification:
    path: str
    surface: str
    status: str
    boundary: str
    notes: str


CLASSIFICATIONS: dict[str, SurfaceClassification] = {
    "packages/api/fastapi_server.py": SurfaceClassification(
        path="packages/api/fastapi_server.py",
        surface="legacy_api_character_pattern",
        status="legacy_quarantine_required",
        boundary="outside_explicit_synthesus5_chal_path",
        notes="Direct character-pattern response_template and fallback strings remain in the legacy FastAPI character router.",
    ),
    "packages/api/production_server.py": SurfaceClassification(
        path="packages/api/production_server.py",
        surface="legacy_api_pattern_storage_and_lookup",
        status="legacy_quarantine_required",
        boundary="outside_explicit_synthesus5_chal_path",
        notes="Pattern ingestion and lookup still preserve response_template text for legacy character/API compatibility.",
    ),
    "packages/core/reasoning_core.py": SurfaceClassification(
        path="packages/core/reasoning_core.py",
        surface="trace_only_pattern_recall",
        status="non_user_facing",
        boundary="reasoning_trace",
        notes="Pattern text is appended to reasoning trace steps rather than emitted as a final response.",
    ),
    "packages/core/chal/quad_brain.py": SurfaceClassification(
        path="packages/core/chal/quad_brain.py",
        surface="quad_brain_template_guard_signatures",
        status="guard_definition",
        boundary="critic_template_guard",
        notes="Quad Brain critic checks known legacy signatures before serialized arbitration selects final text.",
    ),
    "packages/core/character_factory_v2.py": SurfaceClassification(
        path="packages/core/character_factory_v2.py",
        surface="explicit_npc_script_factory",
        status="allowed_labeled_exception",
        boundary="explicit_npc_script",
        notes="Factory-authored NPC response templates are explicit script data; legacy API paths that emit them directly remain separately quarantined.",
    ),
    "packages/core/cognitive/cognitive_engine.py": SurfaceClassification(
        path="packages/core/cognitive/cognitive_engine.py",
        surface="legacy_cognitive_character_fallback",
        status="legacy_quarantine_required",
        boundary="outside_explicit_synthesus5_chal_path",
        notes="The legacy cognitive engine still reads pattern response templates and fallback text for direct character behavior outside the CHAL hypervisor path.",
    ),
    "packages/core/cognitive/response_compositor.py": SurfaceClassification(
        path="packages/core/cognitive/response_compositor.py",
        surface="legacy_response_compositor_template",
        status="legacy_quarantine_required",
        boundary="outside_explicit_synthesus5_chal_path",
        notes="The older response compositor can realize classic response_template strings directly.",
    ),
    "packages/core/els_bridge.py": SurfaceClassification(
        path="packages/core/els_bridge.py",
        surface="legacy_pattern_storage_bridge",
        status="legacy_quarantine_required",
        boundary="outside_explicit_synthesus5_chal_path",
        notes="ELS pattern storage persists response_template data for legacy pattern recall.",
    ),
    "packages/core/pattern_engine.py": SurfaceClassification(
        path="packages/core/pattern_engine.py",
        surface="legacy_pattern_engine_storage",
        status="legacy_quarantine_required",
        boundary="outside_explicit_synthesus5_chal_path",
        notes="PatternEngine stores templated output structures; Synthesus 5 must consume them through firmware/generation boundaries.",
    ),
    "packages/core/unpc_engine/genome_expander.py": SurfaceClassification(
        path="packages/core/unpc_engine/genome_expander.py",
        surface="explicit_npc_script_generation",
        status="allowed_labeled_exception",
        boundary="explicit_npc_script",
        notes="Genome expansion produces NPC script pattern candidates, not normal assistant fallback text.",
    ),
    "packages/core/unpc_engine/pattern_generator.py": SurfaceClassification(
        path="packages/core/unpc_engine/pattern_generator.py",
        surface="explicit_npc_script_generation",
        status="allowed_labeled_exception",
        boundary="explicit_npc_script",
        notes="Pattern generation creates explicit NPC script data and must not be treated as normal final wording ownership.",
    ),
    "packages/core/world/quests.py": SurfaceClassification(
        path="packages/core/world/quests.py",
        surface="explicit_npc_script",
        status="allowed_labeled_exception",
        boundary="explicit_npc_script",
        notes="Quest title, description, objective, and reward templates generate scripted game content, not normal assistant fallback prose.",
    ),
    "packages/core/world/scheduling.py": SurfaceClassification(
        path="packages/core/world/scheduling.py",
        surface="explicit_world_simulation_template",
        status="allowed_labeled_exception",
        boundary="explicit_npc_script",
        notes="Routine templates model simulated world schedules and are not normal conversational fallbacks.",
    ),
    "packages/core/world/economy.py": SurfaceClassification(
        path="packages/core/world/economy.py",
        surface="world_seed_template",
        status="allowed_labeled_exception",
        boundary="explicit_npc_script",
        notes="Template references describe seed world data, not final user-facing response text.",
    ),
    "packages/core/world/coordinator.py": SurfaceClassification(
        path="packages/core/world/coordinator.py",
        surface="world_seed_template",
        status="allowed_labeled_exception",
        boundary="explicit_npc_script",
        notes="Template references describe seed world data, not final user-facing response text.",
    ),
    "packages/core/manifestation_engine.py": SurfaceClassification(
        path="packages/core/manifestation_engine.py",
        surface="platform_boot_template",
        status="allowed_labeled_exception",
        boundary="platform",
        notes="Bootloader/IPXE templates are platform artifacts, not response surfaces.",
    ),
    "packages/frontend/character_studio.py": SurfaceClassification(
        path="packages/frontend/character_studio.py",
        surface="explicit_npc_script_authoring",
        status="allowed_labeled_exception",
        boundary="explicit_npc_script",
        notes="Character Studio writes scripted NPC pattern data for authoring; it does not own Synthesus 5 final wording.",
    ),
    "packages/kernel/operations.py": SurfaceClassification(
        path="packages/kernel/operations.py",
        surface="internal_prompt_template",
        status="non_user_facing",
        boundary="tool_model_prompt",
        notes="Prompt templates are internal rollout prompts, not emitted fallback responses.",
    ),
    "packages/reasoning/breach/exploit_modeler.py": SurfaceClassification(
        path="packages/reasoning/breach/exploit_modeler.py",
        surface="security_attack_tree_template",
        status="allowed_labeled_exception",
        boundary="platform",
        notes="Security attack-tree templates are explicit platform/security artifacts.",
    ),
    "packages/reasoning/generation/spine.py": SurfaceClassification(
        path="packages/reasoning/generation/spine.py",
        surface="generation_degraded_fallback",
        status="labeled_degraded_state",
        boundary="generation_spine_degraded_state",
        notes="Last-resort generation wording now carries explicit degraded-state metadata and avoids legacy template signatures.",
    ),
    "packages/reasoning/generation/template_guard.py": SurfaceClassification(
        path="packages/reasoning/generation/template_guard.py",
        surface="template_guard_signature_registry",
        status="guard_definition",
        boundary="critic_template_guard",
        notes="This is the signature registry and quarantine mechanism for template leakage.",
    ),
    "packages/reasoning/intent_classifier.py": SurfaceClassification(
        path="packages/reasoning/intent_classifier.py",
        surface="training_variant_template",
        status="non_user_facing",
        boundary="training_data_augmentation",
        notes="Templates create classifier training variants and are not final responses.",
    ),
    "packages/reasoning/pattern_classifier.py": SurfaceClassification(
        path="packages/reasoning/pattern_classifier.py",
        surface="pattern_schema_storage",
        status="firmware_context_only",
        boundary="ppbrs_firmware_signal",
        notes="response_template is stored on patterns; PPBRS normal output passes it only as bounded template_context metadata.",
    ),
    "packages/reasoning/reasoning_chain.py": SurfaceClassification(
        path="packages/reasoning/reasoning_chain.py",
        surface="ppbrs_firmware_template_context",
        status="firmware_context_only",
        boundary="ppbrs_firmware_signal",
        notes="Legacy templates are placed in chal_firmware_signal.module_message.payload.template_context, not response.",
    ),
    "packages/reasoning/reranker.py": SurfaceClassification(
        path="packages/reasoning/reranker.py",
        surface="commented_fallback_boundary",
        status="non_user_facing",
        boundary="reranker_comment",
        notes="The match is documentation/commentary for deterministic fallback ranking behavior.",
    ),
    "packages/reasoning/reasoning_core.py": SurfaceClassification(
        path="packages/reasoning/reasoning_core.py",
        surface="trace_only_pattern_recall",
        status="non_user_facing",
        boundary="reasoning_trace",
        notes="Pattern response templates are summarized into internal reasoning trace text, not emitted as final PPBRS wording.",
    ),
    "packages/reasoning/sentiment_analyzer.py": SurfaceClassification(
        path="packages/reasoning/sentiment_analyzer.py",
        surface="training_variant_template",
        status="non_user_facing",
        boundary="training_data_augmentation",
        notes="Templates create sentiment training variants and are not final responses.",
    ),
    "packages/knowledge/kaggle_loader.py": SurfaceClassification(
        path="packages/knowledge/kaggle_loader.py",
        surface="knowledge_ingest_question_template",
        status="non_user_facing",
        boundary="knowledge_ingest",
        notes="Question templates normalize knowledge-ingest rows, not runtime responses.",
    ),
}


def iter_hits(root: Path = SEARCH_ROOT) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel_path = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(signature in line for signature in SIGNATURES):
                classification = CLASSIFICATIONS.get(rel_path)
                hits.append(
                    {
                        "path": rel_path,
                        "line": line_no,
                        "text": line.strip(),
                        "classified": classification is not None,
                        "classification": asdict(classification) if classification else None,
                    }
                )
    return hits


def audit() -> dict[str, object]:
    hits = iter_hits()
    unclassified = [hit for hit in hits if not hit["classified"]]
    by_status: dict[str, int] = {}
    classified_paths = {
        str(hit["path"])
        for hit in hits
        if hit["classified"]
    }
    for path in classified_paths:
        classification = CLASSIFICATIONS[path]
        by_status[classification.status] = by_status.get(classification.status, 0) + 1
    return {
        "schema": "synthesus.template_surface_audit.v1",
        "search_root": SEARCH_ROOT.relative_to(REPO_ROOT).as_posix(),
        "signature_count": len(hits),
        "classified_path_count": len(classified_paths),
        "unclassified_count": len(unclassified),
        "status_counts": by_status,
        "unclassified": unclassified,
        "hits": hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print the full audit as JSON.")
    parser.add_argument("--fail-on-unclassified", action="store_true", help="Exit non-zero if a matched surface lacks classification.")
    args = parser.parse_args()

    result = audit()
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "Template surface audit: "
            f"{result['signature_count']} signatures, "
            f"{result['classified_path_count']} classified paths, "
            f"{result['unclassified_count']} unclassified hits"
        )
        for status, count in sorted(result["status_counts"].items()):
            print(f"- {status}: {count}")
    return 1 if args.fail_on_unclassified and result["unclassified_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
