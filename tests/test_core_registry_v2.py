# mypy: ignore-errors
"""Schema v2 must carry full project identity without ever carrying a secret,
and must not break a registry written by the previous release."""

import json

import pytest

from core.errors import RegistryError, ValidationError
from core.registry import (
    SCHEMA_VERSION,
    ProjectRegistry,
    validate_project_id,
)

V1_DOCUMENT = {
    "alpha": {"path": "/abs/alpha-workspace", "description": "Alpha Web App"},
    "beta": {"path": "/abs/beta", "description": "BETA"},
}

V2_DOCUMENT = {
    "version": 2,
    "projects": {
        "alpha": {
            "path": "/abs/alpha-workspace",
            "git_root": "alpha",
            "description": "Alpha Web App",
            "jira": {
                "url": "https://example.atlassian.net/",
                "email": "someone@example.com",
                "project_key": "ALPHA",
                "credential": "env://JIRA_TOKEN_ALPHA",
            },
            "discord": {"channel_id": "123456789012345678"},
            "board": {"dir": ".claude/board"},
        },
        "api-only": {
            "jira": {
                "url": "https://example.atlassian.net",
                "email": "someone@example.com",
                "project_key": "API",
                "credential": "env://JIRA_TOKEN_API",
            }
        },
    },
}


def write_registry(tmp_path, document) -> str:
    target = tmp_path / "projects.json"
    target.write_text(json.dumps(document), encoding="utf-8")
    return str(target)


class TestProjectIdValidation:
    @pytest.mark.parametrize(
        "project_id", ["alpha", "beta", "drunken-guild", "a", "p_1"]
    )
    def test_accepts_well_formed_ids(self, project_id: str) -> None:
        assert validate_project_id(project_id) == project_id

    @pytest.mark.parametrize(
        "project_id",
        [
            "../etc",
            "../../root",
            "alpha/../beta",
            "ALPHA",
            "-leading-dash",
            "with space",
            "with.dot",
            "",
            "x" * 65,
        ],
    )
    def test_rejects_anything_that_could_escape_a_path_or_a_query(
        self, project_id: str
    ) -> None:
        """Ids arrive as agent input and end up in path joins and JQL."""
        with pytest.raises(ValidationError):
            validate_project_id(project_id)

    def test_rejects_non_strings(self) -> None:
        with pytest.raises(ValidationError):
            validate_project_id(None)


class TestV1Compatibility:
    def test_a_v1_registry_still_loads(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V1_DOCUMENT))
        assert set(registry.get_projects()) == {"alpha", "beta"}

    def test_v1_is_reported_as_version_1(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V1_DOCUMENT))
        assert registry.schema_version() == 1

    def test_v1_project_parses_into_a_typed_config(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V1_DOCUMENT))

        config = registry.get_project_config("alpha")

        assert config.path == "/abs/alpha-workspace"
        assert config.jira is None, "a v1 entry simply has no Jira identity yet"

    def test_writing_to_a_v1_file_does_not_silently_upgrade_it(self, tmp_path) -> None:
        """Rewriting the schema under the operator would make downgrading a
        one-way door; the upgrade happens in memory only."""
        path = write_registry(tmp_path, V1_DOCUMENT)
        registry = ProjectRegistry(path)

        registry.add_project("newproj", "/abs/newproj", "New")

        on_disk = json.loads(open(path, encoding="utf-8").read())
        assert "version" not in on_disk
        assert on_disk["newproj"]["path"] == "/abs/newproj"


class TestV2Schema:
    def test_reports_its_declared_version(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))
        assert registry.schema_version() == SCHEMA_VERSION

    def test_projects_are_read_from_the_projects_key(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))
        assert registry.project_ids() == ["alpha", "api-only"]

    def test_jira_identity_is_parsed(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))

        jira = registry.get_project_config("alpha").jira

        assert jira.project_key == "ALPHA"
        assert jira.email == "someone@example.com"
        assert jira.credential == "env://JIRA_TOKEN_ALPHA"

    def test_trailing_slash_is_stripped_from_the_jira_url(self, tmp_path) -> None:
        """Every call site joins '/rest/api/3/...' onto this."""
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))
        assert (
            registry.get_project_config("alpha").jira.url
            == "https://example.atlassian.net"
        )

    def test_discord_and_board_identities_are_parsed(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))

        config = registry.get_project_config("alpha")

        assert config.discord.channel_id == "123456789012345678"
        assert config.board_dir == ".claude/board"
        assert config.git_root == "alpha"

    def test_the_registry_holds_a_reference_never_a_value(self, tmp_path) -> None:
        """The whole point of the file being committable."""
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))
        assert registry.get_project_config("alpha").jira.credential.startswith("env://")

    def test_unknown_keys_are_preserved_for_forward_compatibility(
        self, tmp_path
    ) -> None:
        document = {
            "version": 99,
            "projects": {"alpha": {"path": "/abs/alpha", "future_field": "keep me"}},
        }
        registry = ProjectRegistry(write_registry(tmp_path, document))

        assert registry.get_project_config("alpha").raw["future_field"] == "keep me"

    def test_writing_to_a_v2_file_keeps_it_v2(self, tmp_path) -> None:
        path = write_registry(tmp_path, V2_DOCUMENT)
        registry = ProjectRegistry(path)

        registry.add_project("newproj", "/abs/newproj")

        on_disk = json.loads(open(path, encoding="utf-8").read())
        assert on_disk["version"] == SCHEMA_VERSION
        assert on_disk["projects"]["newproj"]["path"] == "/abs/newproj"

    def test_updating_a_project_preserves_its_other_identity_fields(
        self, tmp_path
    ) -> None:
        """add_project is the path-registration command; it must not wipe Jira."""
        path = write_registry(tmp_path, V2_DOCUMENT)
        registry = ProjectRegistry(path)

        registry.add_project("alpha", "/abs/moved", "Moved")

        config = registry.get_project_config("alpha")
        assert config.path == "/abs/moved"
        assert config.jira.project_key == "ALPHA"


class TestOptionalPath:
    def test_a_project_without_a_path_is_valid(self, tmp_path) -> None:
        """A containerised Jira server has no host checkout to point at."""
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))
        assert registry.get_project_config("api-only").path is None

    def test_require_path_explains_why_it_is_needed(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))

        with pytest.raises(RegistryError, match="no 'path'") as caught:
            registry.get_project_config("api-only").require_path("the board")

        assert "drunken-register" not in caught.value.remediation
        assert "optional" in caught.value.remediation


class TestUnknownProject:
    def test_error_lists_what_is_registered(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))

        with pytest.raises(RegistryError, match="Unknown project") as caught:
            registry.get_project_config("nosuch")

        assert "alpha" in caught.value.remediation

    def test_remediation_names_a_command_that_still_exists(self, tmp_path) -> None:
        """A remediation is only worth carrying if it can be followed.

        This one told the reader to run ``drunken-register``, retired in S11 —
        so the one error whose entire job is to say "here is the fix" handed
        out a command that exits 127.
        """
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))

        with pytest.raises(RegistryError) as caught:
            registry.get_project_config("nosuch")

        assert "drunken-register" not in caught.value.remediation
        assert "drunken-init" in caught.value.remediation

    def test_error_on_an_empty_registry_names_the_file(self, tmp_path) -> None:
        registry = ProjectRegistry(str(tmp_path / "absent.json"))

        with pytest.raises(RegistryError) as caught:
            registry.get_project_config("alpha")

        assert "absent.json" in caught.value.remediation

    def test_a_malformed_id_is_rejected_before_any_lookup(self, tmp_path) -> None:
        registry = ProjectRegistry(write_registry(tmp_path, V2_DOCUMENT))
        with pytest.raises(ValidationError):
            registry.get_project_config("../../etc/passwd")


class TestCorruptRegistry:
    def test_a_corrupt_file_reads_as_empty_rather_than_crashing_startup(
        self, tmp_path
    ) -> None:
        """Raising here would kill the server at import; an 'unknown project'
        error from a tool call is something the agent can actually report."""
        path = tmp_path / "projects.json"
        path.write_text("{ not json", encoding="utf-8")

        assert ProjectRegistry(str(path)).get_projects() == {}

    def test_non_dict_entries_are_ignored(self, tmp_path) -> None:
        path = write_registry(tmp_path, {"alpha": "should be an object"})
        assert ProjectRegistry(path).get_projects() == {}
