import asyncio
import pytest
from core.synthesus_master import SynthesusMaster


@pytest.mark.asyncio
async def test_kernel_analyze_allowed():
    master = SynthesusMaster()
    # Leave allow_kernel_actions = False (default)

    result = await master.safe_kernel_action("analyze", {})
    assert "error" not in result  # analyze should work even if disabled


@pytest.mark.asyncio
async def test_kernel_takeover_denied():
    master = SynthesusMaster()
    # allow_kernel_actions = False

    result = await master.safe_kernel_action("autonomous_takeover", {"target_device": "localhost"})
    assert "error" in result
    assert "disabled in this environment" in result["error"]


@pytest.mark.asyncio
async def test_kernel_security_check():
    master = SynthesusMaster()
    master.allow_kernel_actions = True  # Enable for test
    # No user_authenticated or admin_privileges_granted facts set

    result = await master.safe_kernel_action("analyze", {})
    assert "error" in result
    assert "Security preconditions not met" in result["error"]


@pytest.mark.asyncio
async def test_kernel_unknown_action():
    master = SynthesusMaster()
    master.allow_kernel_actions = True
    # Set security facts
    master.state.crystallized.facts["user_authenticated"] = True
    master.state.crystallized.facts["admin_privileges_granted"] = True

    result = await master.safe_kernel_action("unknown_action", {})
    assert "error" in result
    assert "Unknown kernel action" in result["error"]
