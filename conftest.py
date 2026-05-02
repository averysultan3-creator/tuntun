"""conftest.py — pytest configuration for TUNTUN test suite.

The following files are standalone scripts that call asyncio.run() at module
level OR define async def test_*() functions consumed by an internal main().
They are NOT proper pytest tests and must be run with `python <file>.py`.
"""

collect_ignore = [
    "test_simulation.py",
    "test_final_stability.py",
    "test_api_cost_routing.py",
    "test_upgrade.py",
    "test_ux_behavior.py",
]
