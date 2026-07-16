"""
Synthesus 4.0 — Core Package
AIVM LLC

Orchestration and high-level runtime components.
"""

# Top-level names are exported LAZILY (PEP 562): importing a lightweight submodule
# (e.g. core.chal.devices.llm_device) must NOT force-load the entire heavy runtime
# (synth_runtime -> kernel -> hemisphere -> ...). `from core import SynthRuntime`
# still works — it resolves on first access.
__all__ = [
    "SynthRuntime",
    "QuadbrainMaster",
]


def __getattr__(name):
    if name == "SynthRuntime":
        from synth_runtime import SynthRuntime
        return SynthRuntime
    if name == "QuadbrainMaster":
        from quadbrain_master import QuadbrainMaster
        return QuadbrainMaster
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
