"""Subscription plans.

Two things under test. The limits themselves — because a wrong number here is
revenue or a broken promise. And the *shape* of the free tier, because the
commercial design depends on free running the whole product at small scale
rather than being a demo with features missing.
"""

from __future__ import annotations

import pytest

from services.plans import (
    PLANS,
    UNLIMITED,
    PlanLimitExceeded,
    all_plans_wire,
    check_custom_characters,
    check_devices,
    check_mesh_compute,
    check_render,
    get_plan,
    plan_wire,
)

FREE = PLANS["free"]
PERSONAL = PLANS["personal"]
ENTERPRISE = PLANS["enterprise"]


# ------------------------------------------------- the free tier's shape


def test_free_runs_the_whole_product_not_a_subset():
    """Free limits SCALE, not features. Every capability is reachable at some
    size — a free user sees the real product, just a small one."""
    assert FREE.max_devices >= 1
    assert FREE.max_characters >= 1
    assert FREE.max_renders_per_day > 0
    assert FREE.max_render_pixels >= 512 * 512, "free must render a usable image"
    assert FREE.max_identity_entries > 0, "memory must persist on free"


def test_free_is_genuinely_free():
    assert FREE.price_monthly_cents == 0


def test_the_mesh_is_the_upgrade():
    """A single machine is a nice local AI; the second device is the product.
    Free therefore stops exactly where the mesh begins."""
    assert FREE.max_devices == 1
    assert FREE.mesh_compute is False
    assert PERSONAL.mesh_compute is True
    assert PERSONAL.max_devices > FREE.max_devices


# ------------------------------------------------------ limits are ordered


@pytest.mark.parametrize("attr", [
    "max_devices", "max_characters", "max_render_pixels",
    "max_renders_per_day", "max_identity_entries",
])
def test_paid_is_never_worse_than_free(attr):
    free_v = getattr(FREE, attr)
    paid_v = getattr(PERSONAL, attr)
    assert paid_v == UNLIMITED or paid_v >= free_v, (
        f"{attr}: personal ({paid_v}) must not be below free ({free_v})"
    )


def test_enterprise_lifts_every_scale_limit():
    for attr in ("max_devices", "max_characters", "max_renders_per_day",
                 "max_identity_entries"):
        assert getattr(ENTERPRISE, attr) == UNLIMITED, f"{attr} should be unlimited"


# ------------------------------------------------------------ enforcement


def test_second_device_is_refused_on_free_and_names_the_upgrade():
    check_devices(FREE, 0)  # the first device is fine
    with pytest.raises(PlanLimitExceeded) as excinfo:
        check_devices(FREE, 1)
    assert excinfo.value.limit == "max_devices"
    assert excinfo.value.upgrade_to == "personal", "the prompt must name a real plan"


def test_render_ceiling_is_enforced_and_stated_in_pixels_the_user_sees():
    check_render(FREE, 512, 512, renders_today=0)
    with pytest.raises(PlanLimitExceeded, match="512×512"):
        check_render(FREE, 1024, 1024, renders_today=0)


def test_daily_render_cap_is_enforced():
    check_render(FREE, 256, 256, renders_today=FREE.max_renders_per_day - 1)
    with pytest.raises(PlanLimitExceeded, match="renders a day"):
        check_render(FREE, 256, 256, renders_today=FREE.max_renders_per_day)


def test_paid_plans_have_no_daily_cap_or_ceiling():
    check_render(PERSONAL, 2048, 2048, renders_today=10_000)
    check_devices(PERSONAL, 9)
    check_mesh_compute(PERSONAL)
    check_custom_characters(PERSONAL)


def test_mesh_and_custom_characters_are_refused_on_free():
    with pytest.raises(PlanLimitExceeded, match="another device"):
        check_mesh_compute(FREE)
    with pytest.raises(PlanLimitExceeded, match="your own characters"):
        check_custom_characters(FREE)


def test_unknown_plan_falls_back_to_free_rather_than_granting_everything():
    """A bad or missing plan id must not accidentally unlock the product."""
    for value in (None, "", "  ", "platinum", 42, {"plan": "enterprise"}):
        assert get_plan(value).plan_id == "free"


def test_plan_ids_are_case_and_space_insensitive():
    assert get_plan(" Personal ").plan_id == "personal"
    assert get_plan("ENTERPRISE").plan_id == "enterprise"


# ----------------------------------------------------------------- wire


def test_wire_exposes_limits_rather_than_hiding_them():
    """The UI must be able to show a user exactly what they have before they
    hit it. A limit discovered by something breaking is a bug."""
    wire = plan_wire(FREE)
    assert wire["limits"]["max_devices"] == 1
    assert wire["limits"]["max_renders_per_day"] == FREE.max_renders_per_day
    assert wire["features"]["mesh_compute"] is False
    assert wire["highlights"], "each plan needs plain-language highlights"


def test_all_plans_are_ordered_cheapest_first():
    ids = [p["plan_id"] for p in all_plans_wire()]
    assert ids == ["free", "personal", "enterprise"]


def test_enterprise_price_is_open_rather_than_zero():
    """None means 'talk to us'. Zero would read as free in the UI."""
    assert ENTERPRISE.price_monthly_cents is None
    assert plan_wire(ENTERPRISE)["price_monthly_cents"] is None
