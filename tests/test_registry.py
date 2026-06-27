import os
from typing import Any
from unittest import mock

import pytest
from drunken_team.core.registry import ProjectRegistry


@pytest.fixture  # type: ignore[misc]
def mock_registry_path(tmp_path: Any) -> str:
    return os.path.join(tmp_path, "projects.json")


def test_registry_initialization_default() -> None:
    with mock.patch("os.getcwd", autospec=True, return_value="/mock/cwd"):
        registry = ProjectRegistry()
        assert registry.registry_path == "/mock/cwd/.agents/projects.json"


def test_registry_initialization_custom(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    assert registry.registry_path == mock_registry_path


def test_get_projects_empty(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    assert registry.get_projects() == {}


def test_add_and_get_project(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)

    registry.add_project("test-proj", "/absolute/path/test-proj", "Test project")

    projects = registry.get_projects()
    assert "test-proj" in projects
    assert projects["test-proj"]["path"] == "/absolute/path/test-proj"
    assert projects["test-proj"]["description"] == "Test project"

    project = registry.get_project("test-proj")
    assert project is not None
    assert project["path"] == "/absolute/path/test-proj"


def test_add_project_relative_path_raises_error(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    with pytest.raises(ValueError, match="Project path must be absolute"):
        registry.add_project("test-proj", "relative/path")


def test_remove_project(mock_registry_path: str) -> None:
    registry = ProjectRegistry(registry_path=mock_registry_path)
    registry.add_project("p1", "/absolute/p1")
    registry.add_project("p2", "/absolute/p2")

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
