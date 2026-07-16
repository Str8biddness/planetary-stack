"""Template leakage guard for Synthesus 5 surface boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


LEGACY_TEMPLATE_SIGNATURES = (
    "[module]",
    "[fallback]",
    "response_template",
    "Handled:",
    "No route matched",
)


class TemplateSurface(str, Enum):
    """Surface classes that determine whether fixed text is allowed."""

    NORMAL = "normal"
    SAFETY = "safety"
    PLATFORM = "platform"
    IDENTITY_RIGHTS = "identity_rights"
    EXPLICIT_NPC_SCRIPT = "explicit_npc_script"


@dataclass(frozen=True)
class TemplateGuardResult:
    """Result of checking a candidate surface for legacy template leakage."""

    text: str
    allowed: bool
    rewritten: bool = False
    matched_signatures: list[str] = field(default_factory=list)
    surface: TemplateSurface = TemplateSurface.NORMAL

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "rewritten": self.rewritten,
            "matched_signatures": list(self.matched_signatures),
            "surface": self.surface.value,
        }


class TemplateLeakageGuard:
    """Prevent legacy PPBRS/template signatures from crossing normal output paths."""

    def __init__(self, signatures: tuple[str, ...] = LEGACY_TEMPLATE_SIGNATURES):
        self.signatures = signatures

    def inspect(
        self,
        text: str,
        *,
        surface: TemplateSurface | str = TemplateSurface.NORMAL,
    ) -> TemplateGuardResult:
        active_surface = self._coerce_surface(surface)
        matches = [signature for signature in self.signatures if signature in text]
        if not matches:
            return TemplateGuardResult(text=text, allowed=True, surface=active_surface)
        if active_surface is not TemplateSurface.NORMAL:
            return TemplateGuardResult(
                text=text,
                allowed=True,
                matched_signatures=matches,
                surface=active_surface,
            )
        return TemplateGuardResult(
            text=self._rewrite_normal_surface(text),
            allowed=False,
            rewritten=True,
            matched_signatures=matches,
            surface=active_surface,
        )

    def _coerce_surface(self, surface: TemplateSurface | str) -> TemplateSurface:
        if isinstance(surface, TemplateSurface):
            return surface
        try:
            return TemplateSurface(str(surface))
        except ValueError:
            return TemplateSurface.NORMAL

    def _rewrite_normal_surface(self, text: str) -> str:
        if not text.strip():
            return text
        return (
            "The normal response path produced a legacy template-shaped surface. "
            "Synthesus 5 has quarantined it; reroute through CHAL firmware, grounded rendering, and critic arbitration."
        )
