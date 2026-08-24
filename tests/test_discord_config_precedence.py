# mypy: ignore-errors
"""A stray ``.env`` above the working directory must not outrank the registry.

DG-254. S3's parent-walk was recorded as closed by DG-224, and it was — for
``jira_mcp``. The same pattern in ``service/discord_utils.py`` was never in
scope, so ``load_dotenv()`` kept climbing to the filesystem root, loading the
first ``.env`` it met into ``os.environ``. Since the environment outranks the
registry per field, that made an unrelated project's credential win.

This is the mechanism that already cost the project months once: a dead Jira
token in TWA's ``.env`` answered every search with HTTP 200 and an empty list,
so the board simply read as empty and nothing looked like a failure (S4).

These tests construct the disagreement deliberately. On a machine where the
``.env`` and the registry happen to agree — which is every machine the
acceptance run was performed on — the defect is invisible.
"""

import json

import pytest

from service import discord_utils


@pytest.fixture()  # type: ignore[misc]
def registry_and_decoy(tmp_path, monkeypatch):
    """A registry saying "registry-wins", and a decoy ``.env`` two levels up."""
    secrets = tmp_path / "secrets.json"
    secrets.write_text(json.dumps({"discord": {"default": "registry-wins"}}))

    project_dir = tmp_path / "wrapper" / "project"
    (project_dir / ".agents").mkdir(parents=True)

    registry_file = tmp_path / "projects.json"
    registry_file.write_text(
        json.dumps(
            {
                "version": 2,
                "projects": {
                    "drunken-guild": {
                        "path": str(project_dir),
                        "discord": {
                            "channel_id": "registry-channel",
                            "credential": f"file://{secrets}#discord.default",
                        },
                    }
                },
            }
        )
    )

    # The trap: a .env belonging to something else, sitting above the project.
    (tmp_path / ".env").write_text(
        "DISCORD_BOT_TOKEN=decoy-from-stray-dotenv\nDISCORD_CHANNEL_ID=decoy-channel\n"
    )

    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry_file))
    for var in ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(project_dir)
    return project_dir


class TestAStrayDotenvDoesNotOutrankTheRegistry:
    def test_the_token_comes_from_the_registry_not_the_parent_dotenv(
        self, registry_and_decoy
    ) -> None:
        """The finding itself. Before DG-254 this returned the decoy, because
        load_dotenv() climbed out of the project and injected it into the
        environment, which load_config() then preferred over the registry."""
        assert discord_utils.load_config()["bot_token"] == "registry-wins"

    def test_the_channel_comes_from_the_registry_too(self, registry_and_decoy) -> None:
        """Asserted separately because precedence is per field: a partial win
        would have been the worse outcome, pairing one project's token with
        another's channel."""
        assert discord_utils.load_config()["channel_id"] == "registry-channel"

    def test_a_stray_dotenv_does_not_leak_into_the_process_environment(
        self, registry_and_decoy
    ) -> None:
        """Not merely that load_config() ignores it — that nothing reads it at
        all. load_dotenv() mutated os.environ as a side effect, so the decoy
        outlived the call and reached every later reader in the process. The
        existing suite already had to defend against exactly this: a test in
        test_discord_config_source.py clears DISCORD_CHANNEL_ID with a comment
        explaining that another test loads the real .env."""
        import os

        discord_utils.load_config()

        assert "DISCORD_BOT_TOKEN" not in os.environ
        assert "DISCORD_CHANNEL_ID" not in os.environ


class TestAnExplicitEnvironmentVariableStillWins:
    def test_a_real_env_var_outranks_the_registry(
        self, registry_and_decoy, monkeypatch
    ) -> None:
        """The override that survives DG-254, and the distinction the ticket
        turns on. A variable set in the process environment is explicit and
        named — that is how a container passes a different bot in. A file
        discovered by climbing the tree is neither."""
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "explicitly-set")

        assert discord_utils.load_config()["bot_token"] == "explicitly-set"


class TestMultipleProjectsRegistered:
    """DG-306. ``_discord_project()`` looped the registry and returned the
    first entry carrying a ``discord`` key, full stop -- the exact guess
    ``default_project_id()`` was already fixed for, three functions above
    this one in the same module, and that fix never reached this function.

    Live impact: with drunken-team registered before drunken-guild, every
    approval request from drunken-guild resolved to drunken-team's channel,
    and nothing reached the Boss on Discord."""

    @pytest.fixture()  # type: ignore[misc]
    def two_projects_registered(self, tmp_path, monkeypatch):
        registry_file = tmp_path / "projects.json"
        registry_file.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {
                        "drunken-team": {
                            "path": str(tmp_path / "drunken-team"),
                            "discord": {"channel_id": "team-channel"},
                        },
                        "drunken-guild": {
                            "path": str(tmp_path / "drunken-guild"),
                            "discord": {"channel_id": "guild-channel"},
                        },
                    },
                }
            )
        )
        monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry_file))
        for var in ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID", "DRUNKEN_PROJECT"):
            monkeypatch.delenv(var, raising=False)

    def test_without_drunken_project_the_first_registered_one_is_the_fallback(
        self, two_projects_registered
    ) -> None:
        """Unchanged by the fix: this is the documented fallback, not the
        rule, and only applies when nothing named a project explicitly."""
        assert discord_utils.load_config()["channel_id"] == "team-channel"

    def test_drunken_project_selects_the_named_project_instead(
        self, two_projects_registered, monkeypatch
    ) -> None:
        """The finding itself, seen failing first: before the fix this
        still returned team-channel regardless of DRUNKEN_PROJECT, because
        nothing on this path ever read the variable."""
        monkeypatch.setenv("DRUNKEN_PROJECT", "drunken-guild")

        assert discord_utils.load_config()["channel_id"] == "guild-channel"

    def test_an_explicit_miss_is_not_answered_by_a_neighbors_channel(
        self, two_projects_registered, monkeypatch
    ) -> None:
        """DRUNKEN_PROJECT naming a project with no discord config (or no
        registry entry at all) must not fall through to a different
        project's channel -- that would be a wrong answer that looks right."""
        monkeypatch.setenv("DRUNKEN_PROJECT", "isac")

        assert discord_utils.load_config()["channel_id"] is None


class TestConfigIsNotLocatedByClimbing:
    def test_a_discord_config_above_the_project_is_not_adopted(
        self, registry_and_decoy, tmp_path
    ) -> None:
        """find_config()'s walk is the same defect wearing different clothes:
        .agents/ belongs to the project it is in, and locating one by climbing
        until something matches adopts a stranger's."""
        stranger = tmp_path / ".agents"
        stranger.mkdir()
        (stranger / "discord_config.json").write_text(json.dumps({"bot_token": "x"}))

        found = discord_utils.find_config()

        assert found is None or not str(found).startswith(str(stranger))
