from cognitive.response_compositor import ResponseCompositor


def test_response_compositor_labels_classic_template_as_explicit_npc_script():
    compositor = ResponseCompositor()

    surface = compositor.compose_labeled(
        pattern={"response_template": "Welcome back, traveler."},
        context={},
    )

    assert surface.text == "Welcome back, traveler."
    assert surface.surface == "explicit_npc_script"
    assert surface.boundary == "response_compositor"
    assert surface.user_facing is True
    assert surface.legacy_template_signature_present is False


def test_response_compositor_string_wrapper_preserves_legacy_api():
    compositor = ResponseCompositor()

    response = compositor.compose(
        pattern={"response_template": "The old route still receives text."},
        context={},
    )

    assert response == "The old route still receives text."
