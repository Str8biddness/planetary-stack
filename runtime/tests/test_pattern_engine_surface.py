import sqlite3

from pattern_engine import PATTERN_TEMPLATE_SURFACE, PatternEngine


def test_pattern_engine_labels_stored_templates_as_candidate_storage(tmp_path):
    engine = PatternEngine(db_path=str(tmp_path / "patterns.db"))

    pattern = engine.add_pattern(
        character_id="synth",
        pattern_type="response",
        trigger="hello",
        response_template="Welcome back.",
        metadata={"template_surface": {"user_facing": True, "surface": "caller_claim"}},
    )

    stored = engine.get_pattern(pattern.id)

    assert stored is not None
    assert stored.metadata["template_surface"]["surface"] == "caller_claim"
    assert stored.metadata["template_surface"]["boundary"] == "core_pattern_engine"
    assert stored.metadata["template_surface"]["user_facing"] is False


def test_pattern_engine_backfills_surface_on_legacy_rows(tmp_path):
    db_path = tmp_path / "patterns.db"
    engine = PatternEngine(db_path=str(db_path))

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO patterns
            (id, character_id, pattern_type, trigger, response_template,
             weight, usage_count, success_rate, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy",
                "synth",
                "response",
                "status",
                "Legacy candidate text.",
                1.0,
                0,
                0.0,
                "2026-06-02T00:00:00+00:00",
                "2026-06-02T00:00:00+00:00",
                "{}",
            ),
        )

    stored = engine.get_pattern("legacy")

    assert stored is not None
    assert stored.metadata["template_surface"] == PATTERN_TEMPLATE_SURFACE
