"""The retired Hub must not return as a shipped product surface."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]
RETIRED_PATHS = (
    "docs/HUB-DASHBOARD.md",
    "docs/SESSION-DISCOVERY.md",
    "src/core/codex_threads.py",
    "src/core/dashboard.py",
    "src/core/dashboard",
    "src/core/guild_jobs.py",
    "src/core/hub.py",
    "src/core/session_discovery.py",
    "src/core/session_store.py",
)


def test_hub_is_not_shipped_or_documented_as_live() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert "drunken-hub" not in project["project"]["scripts"]
    present = [path for path in RETIRED_PATHS if (ROOT / path).exists()]
    assert present == [], f"retired Hub paths are still shipped: {present}"

    retirement = (ROOT / "RETIRED.md").read_text(encoding="utf-8")
    assert "hub-and-session-monitoring" in retirement
