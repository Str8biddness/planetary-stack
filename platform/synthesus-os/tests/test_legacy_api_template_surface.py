import ast
import sys
import types
from pathlib import Path
from typing import Any, Dict, Optional


class _StubCognitiveEngine:
    pass


class _StubKnowledgeCloud:
    pass


class _StubUniversalSubstrate:
    pass


def _install_stub_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules.setdefault(name, module)


_install_stub_module("cognitive.cognitive_engine", CognitiveEngine=_StubCognitiveEngine)
_install_stub_module("core.knowledge_cloud", KnowledgeCloud=_StubKnowledgeCloud)
_install_stub_module("core.universal_substrate", UniversalSubstrate=_StubUniversalSubstrate)
_install_stub_module("kernel.mirror_sync_bridge", MirrorSyncBridge=object)

from packages.api import fastapi_server


def _load_production_surface_helpers():
    source = Path("packages/api/production_server.py").read_text()
    tree = ast.parse(source)
    wanted = {
        "API_PATTERN_STORAGE_SURFACE",
        "API_PATTERN_RECALL_SURFACE",
        "_pattern_surface",
        "_find_response_for_pattern",
    }
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            names = {target.id for target in node.targets if isinstance(target, ast.Name)}
            if names & wanted:
                nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            nodes.append(node)
    module = ast.Module(body=nodes, type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"Optional": Optional, "Dict": Dict, "Any": Any, "_character_cache": {}}
    exec(compile(module, "production_server_surface_helpers", "exec"), namespace)
    return namespace


def test_fastapi_character_pattern_response_is_labeled_npc_script(monkeypatch):
    monkeypatch.setattr(
        fastapi_server,
        "_character_cache",
        {
            "merchant": {
                "bio": {"name": "Merchant"},
                "patterns": {
                    "synthetic_patterns": [
                        {
                            "id": "trade.greeting",
                            "trigger": ["trade goods"],
                            "response_template": "Fine wares for careful buyers.",
                            "confidence": 0.95,
                        }
                    ],
                    "generic_patterns": [],
                },
            }
        },
    )

    result = fastapi_server._character_fallback("trade goods", "merchant")

    assert result["response"] == "Fine wares for careful buyers."
    assert result["debug"]["template_surface"]["boundary"] == "explicit_npc_script"
    assert result["debug"]["template_surface"]["normal_assistant_path"] is False


def test_production_api_pattern_recall_returns_labeled_candidate(monkeypatch):
    helpers = _load_production_surface_helpers()
    helpers["_character_cache"] = {
        "synth": {
            "patterns": {
                "synthetic_patterns": [
                    {
                        "trigger": ["status check"],
                        "response_template": "Status is stable.",
                    }
                ],
                "generic_patterns": [],
            },
        }
    }

    result = helpers["_find_response_for_pattern"]("status check", "synth")

    assert result is not None
    assert result["response"] == "Status is stable."
    assert result["template_surface"]["boundary"] == "explicit_npc_script"
    assert result["template_surface"]["normal_assistant_path"] is False


def test_production_api_pattern_ingest_surface_is_non_user_facing():
    helpers = _load_production_surface_helpers()
    surface = helpers["_pattern_surface"]("pattern_ingest", "synth", "status check")

    assert surface["boundary"] == "legacy_api_pattern_storage"
    assert surface["user_facing"] is False
