# mypy: ignore-errors
"""The routing scenarios, sent to Claude Code — DG-398. Spends tokens.

Deselected by default. Run it on purpose:

    pytest -m routing tests/test_routing_claude_code.py -s

or, for the same report without pytest, `python scripts/run_routing_scenarios.py`.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import run_routing_scenarios as runner  # noqa: E402

pytestmark = pytest.mark.routing


def test_every_scenario_routes_at_two_of_three(tmp_path: Path) -> None:
    if not shutil.which("claude"):
        pytest.fail("`claude` is not on PATH: routing was not checked, not passed")

    out = tmp_path / "routing-claude-code.txt"
    code = runner.main(["--report", str(out)])

    assert code == 0, out.read_text(encoding="utf-8")
