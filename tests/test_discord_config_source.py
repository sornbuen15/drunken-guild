# mypy: ignore-errors
"""The daemon's Discord identity comes from the registry, like everything else.

DT-242 moved the MCP servers onto the registry and DT-246 moved the daemon's
Jira access. Discord stayed on ``.env``, which left the registry's
``discord.channel_id`` written by ``drunken-init`` and read by nobody —
``drunken-doctor`` reported SKIP for two projects while a single channel was in
fact serving all three.

One Discord identity, referenced by every project, is the honest shape now that
the multi-tenant daemon is cut: nobody drives more than one project at a time.
"""

import json

import pytest

from service import discord_utils


@pytest.fixture()  # type: ignore[misc]
def registry(tmp_path, monkeypatch):
    secrets = tmp_path / "secrets.json"
    secrets.write_text(json.dumps({"discord": {"default": "registry-bot-token"}}))

    registry_file = tmp_path / "projects.json"
    registry_file.write_text(
        json.dumps(
            {
                "version": 2,
                "projects": {
                    "drunken-team": {
                        "path": str(tmp_path),
                        "discord": {
                            "channel_id": "999",
                            "credential": f"file://{secrets}#discord.default",
                        },
                    }
                },
            }
        )
    )
    monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry_file))
    for var in ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(discord_utils, "find_config", lambda: None)
    monkeypatch.setattr(discord_utils, "load_dotenv", lambda: None)
    return tmp_path


class TestTheRegistryIsTheSource:
    def test_channel_and_token_come_from_the_registry(self, registry) -> None:
        config = discord_utils.load_config()

        assert config["channel_id"] == "999"
        assert config["bot_token"] == "registry-bot-token"

    def test_the_environment_still_wins_when_set(self, registry, monkeypatch) -> None:
        """Overriding for one run is a legitimate thing to do, and it is how a
        container passes a different bot in without rewriting the registry."""
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "111")

        assert discord_utils.load_config()["channel_id"] == "111"


class TestItStillStartsWithNothingRegistered:
    def test_an_absent_registry_falls_back_rather_than_raising(
        self, tmp_path, monkeypatch
    ) -> None:
        """First run, before `drunken-init` has been used. Raising here would
        take the daemon down at import — principle 8, and §1.1 before it."""
        monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(tmp_path / "absent.json"))
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "from-env")
        monkeypatch.setenv("DISCORD_CHANNEL_ID", "222")
        monkeypatch.setattr(discord_utils, "find_config", lambda: None)
        monkeypatch.setattr(discord_utils, "load_dotenv", lambda: None)

        config = discord_utils.load_config()

        assert config == {"bot_token": "from-env", "channel_id": "222"}

    def test_an_unresolvable_credential_does_not_kill_the_daemon(
        self, tmp_path, monkeypatch
    ) -> None:
        """A reference pointing at a file that is gone must degrade to the
        environment, not raise on the way up."""
        registry_file = tmp_path / "projects.json"
        registry_file.write_text(
            json.dumps(
                {
                    "version": 2,
                    "projects": {
                        "p": {
                            "discord": {
                                "channel_id": "333",
                                "credential": "file:///nonexistent#discord.default",
                            }
                        }
                    },
                }
            )
        )
        monkeypatch.setenv("DRUNKEN_REGISTRY_PATH", str(registry_file))
        monkeypatch.setenv("DISCORD_BOT_TOKEN", "fallback-token")
        # Explicitly cleared: another test in the suite loads the real .env
        # into os.environ, and the environment outranks the registry, so
        # leaving this set makes the assertion depend on test ordering.
        monkeypatch.delenv("DISCORD_CHANNEL_ID", raising=False)
        monkeypatch.setattr(discord_utils, "find_config", lambda: None)
        monkeypatch.setattr(discord_utils, "load_dotenv", lambda: None)

        config = discord_utils.load_config()

        assert config["channel_id"] == "333"
        assert config["bot_token"] == "fallback-token"
