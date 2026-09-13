# mypy: ignore-errors
"""The project is an argument to every tool, not a flag on the server — DG-341.

`~/.claude.json` registered `drunken-jira-mcp` at **user scope** with
`--project drunken-guild`. User scope reaches every session on the machine, so a
session opened in an unrelated project saw DG's Jira and nothing said so. The
fix that was first written down — give every project its own `.mcp.json` and
have the doctor warn about a pinned user-scope entry — treats the symptom: the
flag stays load-bearing, and the same leak returns the next time somebody
registers a server at user scope.

The class fix is that the server has no project at all. Every tool takes the key
as an argument, validated against the registry, and one identical MCP
configuration serves every project. There is then nothing to pin.

Which makes the important tests here the negative ones. A server that *guesses*
is the whole defect: it does not fail, it files work onto somebody else's board
and reports success.
"""

import inspect
import json

import pytest

from core import paths
from core.errors import DrunkenError

REGISTRY = {
    "version": 2,
    "projects": {
        "alpha": {
            "path": "/abs/alpha",
            "jira": {
                "url": "https://alpha.atlassian.net",
                "email": "someone@example.com",
                "project_key": "ALPHA",
                "credential": "env://JIRA_TOKEN_ALPHA",
            },
        },
        "beta": {
            "path": "/abs/beta",
            "jira": {
                "url": "https://beta.atlassian.net",
                "email": "someone@example.com",
                "project_key": "BETA",
                "credential": "env://JIRA_TOKEN_BETA",
            },
        },
    },
}


@pytest.fixture()
def registered(monkeypatch, tmp_path):
    """Two registered projects, and nothing of the operator's own in reach."""
    from core import secrets

    path = tmp_path / "projects.json"
    path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    monkeypatch.setenv(paths.ENV_REGISTRY, str(path))
    monkeypatch.setenv("JIRA_TOKEN_ALPHA", "alpha-token-value")
    monkeypatch.setenv("JIRA_TOKEN_BETA", "beta-token-value")
    secrets.clear_cache()

    import jira_mcp.server as srv

    srv.forget_clients()
    yield srv
    srv.forget_clients()
    secrets.clear_cache()


def _tools(module):
    """Every MCP tool this module exposes, by name.

    Read off the module rather than off a hand-written list, so a tool added
    later is covered without anybody remembering to add it here.
    """
    return {
        name: obj
        for name, obj in vars(module).items()
        if name.startswith("jira_") and inspect.iscoroutinefunction(obj)
    }


class TestTheProjectIsAnArgument:
    def test_every_tool_takes_project_first(self, registered) -> None:
        """The guard that outlives this change.

        A tool added later without the parameter would have no project to act
        on, and the only sources left would be a guess or a global — which is
        the defect this ticket is about, reintroduced by omission.
        """
        tools = _tools(registered)
        assert len(tools) >= 10, f"expected the full tool set, found {sorted(tools)}"

        for name, fn in sorted(tools.items()):
            first = next(iter(inspect.signature(fn).parameters))
            assert first == "project", (
                f"{name}() takes {first!r} first, so it has no project to act on. "
                "Every tool takes the key as its first argument (DG-341)."
            )

    def test_the_launch_flag_is_gone(self, registered) -> None:
        """`--project` on the server is what user scope was able to pin."""
        assert not hasattr(registered, "parse_project_arg")
        assert not hasattr(registered, "ctx")


class TestARefusalRatherThanAGuess:
    def test_an_empty_project_is_refused_and_says_what_is_registered(
        self, registered
    ) -> None:
        with pytest.raises(DrunkenError) as caught:
            registered.get_client("")

        assert caught.value.remediation, (
            "a refusal with no next step leaves an agent stuck"
        )
        assert "alpha" in caught.value.remediation
        assert "beta" in caught.value.remediation

    def test_an_unknown_project_is_refused_and_names_the_known_ones(
        self, registered
    ) -> None:
        """Not a fallback to the only project, and not to the first one. The
        first-key-in-a-json-file default is how a daemon came to post every
        project's approvals into one room."""
        with pytest.raises(DrunkenError) as caught:
            registered.get_client("gamma")

        assert "gamma" in str(caught.value)
        assert "alpha" in caught.value.remediation

    def test_a_traversal_id_is_refused(self, registered) -> None:
        """The key reaches a path join and a JQL string, so it is input."""
        with pytest.raises(DrunkenError):
            registered.get_client("../../etc/passwd")


class TestOneServerServesEveryProject:
    def test_two_projects_in_one_process_get_their_own_client(self, registered) -> None:
        """The finding itself, as an assertion. One process, two calls, two
        different Jira sites — with no restart and no second configuration."""
        alpha = registered.get_client("alpha")
        beta = registered.get_client("beta")

        assert alpha is not beta
        assert (alpha.project_key, beta.project_key) == ("ALPHA", "BETA")
        assert alpha.base_url != beta.base_url

    def test_the_same_project_resolves_once(self, registered) -> None:
        """A backend like 1Password prompts for biometrics on every read, so
        resolving per call would make the server unusable."""
        assert registered.get_client("alpha") is registered.get_client("alpha")

    @pytest.mark.asyncio
    async def test_a_search_is_scoped_to_the_project_it_was_asked_about(
        self, registered
    ) -> None:
        """Scoping comes from the argument now, not from what the server was
        started with. A query naming another project must match nothing rather
        than reaching it."""
        seen = {}

        class _Recording:
            project_key = "BETA"

            async def search_issues(self, jql, brief=True):
                seen["jql"] = jql
                return []

        # Written straight into the cache, the way the old tests set the
        # module globals: a production seam for one test is a second way in.
        registered._clients["beta"] = _Recording()
        await registered.jira_search_issues("beta", "status = 'To Do'")

        assert 'project = "BETA"' in seen["jql"]
