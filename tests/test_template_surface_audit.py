from tools.audit_template_surfaces import CLASSIFICATIONS, audit


def test_template_surface_audit_has_no_unclassified_package_hits():
    result = audit()
    assert result["signature_count"] > 0
    assert result["unclassified"] == []


def test_template_surface_audit_keeps_legacy_api_emitters_labeled():
    legacy_required = {
        "packages/api/fastapi_server.py",
        "packages/api/production_server.py",
    }

    for path in legacy_required:
        classification = CLASSIFICATIONS[path]
        assert classification.status == "legacy_quarantine_required"
        assert classification.boundary


def test_template_surface_audit_tracks_generation_spine_as_labeled_degraded_state():
    classification = CLASSIFICATIONS["packages/reasoning/generation/spine.py"]

    assert classification.status == "labeled_degraded_state"
    assert classification.boundary == "generation_spine_degraded_state"


def test_template_surface_audit_tracks_response_compositor_as_labeled_npc_script():
    classification = CLASSIFICATIONS["packages/core/cognitive/response_compositor.py"]

    assert classification.status == "allowed_labeled_exception"
    assert classification.boundary == "explicit_npc_script"


def test_template_surface_audit_labels_allowed_exceptions():
    allowed = [
        item
        for item in CLASSIFICATIONS.values()
        if item.status == "allowed_labeled_exception"
    ]

    assert allowed
    assert {item.boundary for item in allowed} <= {"explicit_npc_script", "platform"}
