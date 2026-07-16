from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
KERNEL_BUILD = ROOT / "packages" / "kernel" / "build"
MODULES = sorted(KERNEL_BUILD.glob("_synthesus_kernel*.so"))


@pytest.fixture()
def native_kernel():
    if not MODULES:
        pytest.skip("native _synthesus_kernel module is not built")
    sys.path.insert(0, str(KERNEL_BUILD))
    return __import__("_synthesus_kernel")


def test_vpd_pybind_dump_exposes_parameter_partition_metadata(native_kernel):
    engine = native_kernel.EmulEngine()
    engine.set_parameter_lookup(lambda parameter_id: b"abcdef" if parameter_id == "chal:param:test" else b"")

    assert engine.map_parameter("chal:param:test") is True
    assert engine.mapped_parameter_count() == 1

    dump = engine.dump_vpd()
    selected = dump["selected_parameter"]

    assert dump["device"] == "VirtualParameterDevice"
    assert dump["parameter_count"] == 1
    assert dump["data_window_offset"] == 0x100
    assert selected["available"] is True
    assert selected["index"] == 0
    assert selected["key"] == "chal:param:test"
    assert selected["version"] == 1
    assert selected["size"] == 6
    assert selected["data_offset"] == 0
    assert selected["data_length"] == 0
    assert selected["bytes"] == [97, 98, 99, 100, 101, 102]
