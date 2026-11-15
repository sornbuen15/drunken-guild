# mypy: ignore-errors
import os
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from core.registry import ProjectRegistry


@pytest.fixture  # type: ignore[misc]
def mock_registry_path(tmp_path: Any) -> str:
    return os.path.join(tmp_path, "projects.json")


def test_registry_default_ignores_the_working_directory(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Was: the default resolved to '<cwd>/.agents/projects.json'.

    That is the §1.2 root cause — the registry a server read depended on which
    directory the host happened to launch it from, so two clients could disagree
    about what a project even was. It now comes from $DRUNKEN_HOME.
    """
    monkeypatch.delenv("DRUNKEN_REGISTRY_PATH", raising=False)
    state = tmp_path / "state"
    monkeypatch.setenv("DRUNKEN_HOME", str(state))

    with mock.patch("os.getcwd", autospec=True, return_value="/mock/cwd"):
        registry = ProjectRegistry()

    assert registry.registry_path == str(state / "projects.json")


def test_registry_default_honours_the_registry_env_override(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Antigravity's mcp_config.json already sets this, and does so correctly."""
    override = tmp_path / "elsewhere" / "projects.json"
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(override))

    assert ProjectRegistry().registry_path == str(override)


def test_registry_initialization_custom(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    assert registry.registry_path == mock_registry_path


def test_get_projects_empty(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    assert registry.get_projects() == {}


def test_add_and_get_project(mock_registry_path: str, tmp_path: Path) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)

    project_path = str(tmp_path / "test-proj")
    registry.add_project("test-proj", project_path, "Test project")

    projects = registry.get_projects()
    assert "test-proj" in projects
    assert projects["test-proj"]["path"] == project_path
    assert projects["test-proj"]["description"] == "Test project"

    project = registry.get_project("test-proj")
    assert project is not None
    assert project["path"] == project_path


def test_add_project_relative_path_raises_error(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    with pytest.raises(ValueError, match="Project path must be absolute"):
        registry.add_project("test-proj", "relative/path")


def test_remove_project(mock_registry_path: str, tmp_path: Path) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    registry.add_project("p1", str(tmp_path / "p1"))
    registry.add_project("p2", str(tmp_path / "p2"))

    assert registry.remove_project("p1") is True
    assert registry.get_project("p1") is None
    assert registry.get_project("p2") is not None

    assert registry.remove_project("non_existent") is False


def test_load_malformed_json(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    os.makedirs(os.path.dirname(mock_registry_path), exist_ok=True)
    with open(mock_registry_path, "w", encoding="utf-8") as f:
        f.write("invalid json {")

    # Should gracefully return empty dict
    assert registry.get_projects() == {}


def test_load_non_dict_json(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    os.makedirs(os.path.dirname(mock_registry_path), exist_ok=True)
    with open(mock_registry_path, "w", encoding="utf-8") as f:
        f.write('["list", "instead", "of", "dict"]')

    # Should gracefully return empty dict
    assert registry.get_projects() == {}
