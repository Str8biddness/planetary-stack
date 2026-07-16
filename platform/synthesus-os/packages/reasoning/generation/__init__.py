# core/generation/__init__.py
from .cgpu import CGPUCandidate, CGPUFrame, CGPUOutputFrame, CGPURenderer
from .response_plan import ResponsePlan, GenerationConfig, GenerationTrace
from .template_guard import (
    LEGACY_TEMPLATE_SIGNATURES,
    TemplateGuardResult,
    TemplateLeakageGuard,
    TemplateSurface,
)

__all__ = [
    "CGPUCandidate",
    "CGPUFrame",
    "CGPUOutputFrame",
    "CGPURenderer",
    "GenerationConfig",
    "GenerationTrace",
    "LEGACY_TEMPLATE_SIGNATURES",
    "ResponsePlan",
    "TemplateGuardResult",
    "TemplateLeakageGuard",
    "TemplateSurface",
]
