"""Subscription plans: what each tier grants, in one place.

The commercial design, stated so it can be argued with rather than inferred:

**Free is not a crippled product — it is a small one.** Every feature is
present and reachable: the mesh, the forge, characters, identity chains. What
free limits is SCALE — one device, one character, modest render sizes. A user
on free sees exactly what they would get by paying, working, on their own
machine. Nothing is hidden behind a teaser, and nothing pretends to work and
then refuses.

That is deliberate. A free tier that hides features teaches users the product
is small. A free tier that runs the whole product at small scale teaches them
it is real, and the limit they hit is the one that maps to why they would pay:
their second device.

**The mesh is the upgrade.** A single machine is a nice local AI. The moment a
second device joins, it becomes the thing nobody else sells. So the free tier
deliberately includes full mesh UI and one device — the user can see the empty
device list and understand precisely what a subscription buys.

**Limits are honest.** Every cap here is enforced server-side and surfaced in
the UI before it is hit, never as a surprise failure mid-task. A limit the user
discovers by something breaking is a bug, not a business model.

Prices are annotated where they are a judgement call. They belong to the owner
and are trivially changed; the structure is the part worth reviewing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Sentinel for "no limit". Using a number avoids `None` checks at every call
# site and makes comparisons uniform.
UNLIMITED = -1


@dataclass(frozen=True)
class Plan:
    """One subscription tier. Everything a caller needs to enforce it."""

    plan_id: str
    name: str
    tagline: str
    # Price in minor units (cents) per month. 0 for free, None for "talk to us".
    price_monthly_cents: int | None
    # Scale limits — the levers that actually differentiate the tiers.
    max_devices: int
    max_characters: int
    max_render_pixels: int          # width * height ceiling for one render
    max_renders_per_day: int
    max_identity_entries: int       # per character, before rotation
    mesh_compute: bool              # may dispatch work to other nodes
    distributed_render: bool        # may split one render across the mesh
    custom_characters: bool         # may author and import their own
    priority_support: bool
    highlights: tuple[str, ...] = field(default_factory=tuple)


# 512x512 is a real, usable image and roughly 2.7s on the native core.
_FREE_RENDER_PIXELS = 512 * 512
# 2048x2048 is the endpoint's own ceiling.
_PAID_RENDER_PIXELS = 2048 * 2048


PLANS: dict[str, Plan] = {
    "free": Plan(
        plan_id="free",
        name="Free",
        tagline="The whole product, on one machine.",
        price_monthly_cents=0,
        max_devices=1,
        max_characters=1,
        max_render_pixels=_FREE_RENDER_PIXELS,
        max_renders_per_day=25,
        max_identity_entries=1_000,
        mesh_compute=False,
        distributed_render=False,
        custom_characters=False,
        priority_support=False,
        highlights=(
            "Runs entirely on your computer — nothing leaves it",
            "Synthesus, with memory that persists",
            "Image forge up to 512×512, 25 renders a day",
            "Full mesh interface — add a second device to switch it on",
        ),
    ),
    # Judgement call: $12/mo. Below the psychological £15/$15 line, comfortably
    # above the marginal cost (which is near zero — the compute is the user's).
    # The value being sold is the mesh and the character library, not tokens.
    "personal": Plan(
        plan_id="personal",
        name="Personal",
        tagline="Every device you own, working together.",
        price_monthly_cents=1200,
        max_devices=10,
        max_characters=UNLIMITED,
        max_render_pixels=_PAID_RENDER_PIXELS,
        max_renders_per_day=UNLIMITED,
        max_identity_entries=UNLIMITED,
        mesh_compute=True,
        distributed_render=True,
        custom_characters=True,
        priority_support=False,
        highlights=(
            "Up to 10 devices in one private mesh",
            "Old phones and spare machines become workers",
            "Distributed rendering — the whole house on one image",
            "Every character, plus your own",
            "Unlimited history, unlimited renders",
        ),
    ),
    "enterprise": Plan(
        plan_id="enterprise",
        name="Enterprise",
        tagline="Your own infrastructure, under your own terms.",
        price_monthly_cents=None,  # per-seat, negotiated
        max_devices=UNLIMITED,
        max_characters=UNLIMITED,
        max_render_pixels=_PAID_RENDER_PIXELS,
        max_renders_per_day=UNLIMITED,
        max_identity_entries=UNLIMITED,
        mesh_compute=True,
        distributed_render=True,
        custom_characters=True,
        priority_support=True,
        highlights=(
            "Unlimited devices and characters",
            "Signed character issuance for your organisation",
            "Deploy to your own hardware — no vendor infrastructure",
            "Priority support and a named contact",
        ),
    ),
}

DEFAULT_PLAN = "free"


class PlanLimitExceeded(PermissionError):
    """An action was refused because the current plan does not allow it.

    Carries the plan and the limit so the UI can say precisely what was hit and
    what would lift it, rather than showing a generic failure.
    """

    def __init__(self, message: str, *, plan_id: str, limit: str, upgrade_to: str | None):
        super().__init__(message)
        self.plan_id = plan_id
        self.limit = limit
        self.upgrade_to = upgrade_to


def get_plan(plan_id: str | None) -> Plan:
    """Resolve a plan id, falling back to free. Never raises."""
    if not isinstance(plan_id, str):
        return PLANS[DEFAULT_PLAN]
    return PLANS.get(plan_id.strip().lower(), PLANS[DEFAULT_PLAN])


def _next_plan_with(capability: str) -> str | None:
    """The cheapest plan that lifts a given limit, for the upgrade prompt."""
    order = ("free", "personal", "enterprise")
    for plan_id in order:
        plan = PLANS[plan_id]
        value = getattr(plan, capability, None)
        if value is True or value == UNLIMITED:
            return plan_id
    return None


def check_devices(plan: Plan, current_count: int) -> None:
    if plan.max_devices != UNLIMITED and current_count >= plan.max_devices:
        raise PlanLimitExceeded(
            f"{plan.name} includes {plan.max_devices} device"
            f"{'' if plan.max_devices == 1 else 's'}",
            plan_id=plan.plan_id,
            limit="max_devices",
            upgrade_to=_next_plan_with("mesh_compute"),
        )


def check_render(plan: Plan, width: int, height: int, renders_today: int) -> None:
    if width * height > plan.max_render_pixels:
        side = int(plan.max_render_pixels ** 0.5)
        raise PlanLimitExceeded(
            f"{plan.name} renders up to {side}×{side}",
            plan_id=plan.plan_id,
            limit="max_render_pixels",
            upgrade_to=_next_plan_with("distributed_render"),
        )
    if plan.max_renders_per_day != UNLIMITED and renders_today >= plan.max_renders_per_day:
        raise PlanLimitExceeded(
            f"{plan.name} includes {plan.max_renders_per_day} renders a day",
            plan_id=plan.plan_id,
            limit="max_renders_per_day",
            upgrade_to=_next_plan_with("distributed_render"),
        )


def check_mesh_compute(plan: Plan) -> None:
    if not plan.mesh_compute:
        raise PlanLimitExceeded(
            "Sending work to another device needs a paid plan",
            plan_id=plan.plan_id,
            limit="mesh_compute",
            upgrade_to=_next_plan_with("mesh_compute"),
        )


def check_custom_characters(plan: Plan) -> None:
    if not plan.custom_characters:
        raise PlanLimitExceeded(
            "Importing your own characters needs a paid plan",
            plan_id=plan.plan_id,
            limit="custom_characters",
            upgrade_to=_next_plan_with("custom_characters"),
        )


def plan_wire(plan: Plan) -> dict[str, Any]:
    """Serialisable view for the UI. Limits are shown, never hidden."""
    return {
        "plan_id": plan.plan_id,
        "name": plan.name,
        "tagline": plan.tagline,
        "price_monthly_cents": plan.price_monthly_cents,
        "highlights": list(plan.highlights),
        "limits": {
            "max_devices": plan.max_devices,
            "max_characters": plan.max_characters,
            "max_render_pixels": plan.max_render_pixels,
            "max_renders_per_day": plan.max_renders_per_day,
            "max_identity_entries": plan.max_identity_entries,
        },
        "features": {
            "mesh_compute": plan.mesh_compute,
            "distributed_render": plan.distributed_render,
            "custom_characters": plan.custom_characters,
            "priority_support": plan.priority_support,
        },
    }


def all_plans_wire() -> list[dict[str, Any]]:
    return [plan_wire(PLANS[p]) for p in ("free", "personal", "enterprise")]
