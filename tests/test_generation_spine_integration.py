import asyncio
import importlib
import inspect

import pytest
from fastapi.testclient import TestClient

from core.generation import decoder
from core.generation.spine import GenerationSpine, SpineInput


def _import_production_server():
    try:
        return importlib.import_module("api.production_server")
    except Exception as exc:
        pytest.skip(f"production_server import unavailable in this environment: {exc}")


def test_startup_declares_generation_spine_global():
    ps = _import_production_server()
    startup_src = inspect.getsource(ps.startup)
    assert "_generation_spine" in startup_src
    assert "global _amplification_plane, _symbolic_core, _generation_spine" in startup_src


def test_generation_spine_applies_halt_and_confirmation():
    spine = GenerationSpine()

    halt_out = spine.generate(
        SpineInput(
            raw_text="Safe response text",
            query="test",
            execution_recommendation="HALT",
            risk_score=0.95,
            session_id="sess-halt",
        )
    )
    assert halt_out.safety_passed is False
    assert halt_out.final_text == "[Response halted per risk assessment]"

    confirm_out = spine.generate(
        SpineInput(
            raw_text="Please restart the service when ready.",
            query="test",
            execution_recommendation="REQUEST_CONFIRMATION",
            risk_score=0.6,
            session_id="sess-confirm",
        )
    )
    assert confirm_out.safety_passed is True
    assert confirm_out.final_text.startswith("[Please confirm] ")


def test_generation_spine_sets_decoder_models_dir(tmp_path):
    models_dir = str(tmp_path / "models")
    GenerationSpine(models_dir=models_dir)
    assert decoder.MODELS_DIR == models_dir


def test_amplification_metrics_domain_breakdown_schema():
    ps = _import_production_server()

    class FakeSpine:
        def get_metrics(self):
            return {
                "total_calls": 8,
                "by_domain": {"chat": 5, "sysops": 2, "gm": 1},
                "safety_violations": 1,
                "recommendations": {"PROCEED": 6, "REQUEST_CONFIRMATION": 1, "HALT": 1},
                "risk_distribution": {"low": 4, "medium": 3, "high": 1},
                "constraints_satisfied_rate": 0.875,
                "avg_latency_ms": 12.3,
            }

    ps.HAS_GENERATION_SPINE = True
    ps._generation_spine = FakeSpine()

    payload = asyncio.run(ps.amplification_metrics())
    breakdown = payload["domain_breakdown"]

    assert isinstance(breakdown, dict)
    for domain in ("chat", "sysops", "gm", "multimodal", "general"):
        assert domain in breakdown
        assert set(breakdown[domain].keys()) == {"calls", "avg_latency_ms"}
        assert isinstance(breakdown[domain]["calls"], int)


def test_generation_spine_empty_raw_text_prefers_finalize_path():
    spine = GenerationSpine()
    out = spine.generate(
        SpineInput(
            raw_text="",
            query="",
            session_id="sess-empty",
            source_confidence=0.77,
            execution_recommendation="PROCEED",
        )
    )
    # Empty-but-provided raw text should still be finalized as-is, not generated from context.
    assert out.text == ""
    assert out.final_text == ""
    assert out.trace is not None
    assert out.trace.mean_logprob == 0.77


def test_amplification_metrics_endpoint_contract():
    ps = _import_production_server()

    class FakeSpine:
        def get_metrics(self):
            return {
                "total_calls": 3,
                "by_domain": {"chat": 3},
                "safety_violations": 0,
                "recommendations": {"PROCEED": 3},
                "risk_distribution": {"low": 3, "medium": 0, "high": 0},
                "constraints_satisfied_rate": 1.0,
                "avg_latency_ms": 9.5,
            }

    ps.HAS_GENERATION_SPINE = True
    ps._generation_spine = FakeSpine()
    client = TestClient(ps.app)
    res = client.get("/api/v1/amplification/metrics")
    assert res.status_code == 200
    payload = res.json()
    breakdown = payload["domain_breakdown"]
    assert isinstance(breakdown, dict)
    assert set(breakdown["chat"].keys()) == {"calls", "avg_latency_ms"}


def test_legacy_payload_normalization_maps_text_and_mode():
    ps = _import_production_server()
    normalized = ps._normalize_legacy_query_payload(
        ps.LegacyQueryRequest(text="legacy hello", mode="sysops", character="synth")
    )
    assert normalized.query == "legacy hello"
    assert normalized.mode == "auto"
    assert normalized.character == "synth"
