"""DG-415. The scheduled dependency-audit workflow must run only the audits
that apply to a project's actual manifests.

Detection lives in `scripts/detect_dependency_manifests.py` rather than
inline workflow shell precisely so it can be exercised here, against
fixture directories, without a real CI run.
"""

from pathlib import Path

from scripts import detect_dependency_manifests as detect


class TestDetectManifests:
    def test_only_composer_lock_runs_only_the_composer_step(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "composer.lock").write_text("{}", encoding="utf-8")

        found = detect.detect_manifests(tmp_path)

        assert found == {"pip": False, "composer": True, "npm": False}

    def test_uv_lock_alone_triggers_pip_only(self, tmp_path: Path) -> None:
        (tmp_path / "uv.lock").write_text("", encoding="utf-8")

        found = detect.detect_manifests(tmp_path)

        assert found == {"pip": True, "composer": False, "npm": False}

    def test_requirements_txt_without_uv_lock_still_triggers_pip(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "requirements-dev.txt").write_text("", encoding="utf-8")

        found = detect.detect_manifests(tmp_path)

        assert found["pip"] is True

    def test_package_lock_json_triggers_npm_only(self, tmp_path: Path) -> None:
        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

        found = detect.detect_manifests(tmp_path)

        assert found == {"pip": False, "composer": False, "npm": True}

    def test_all_three_manifests_present_runs_all_three(self, tmp_path: Path) -> None:
        (tmp_path / "uv.lock").write_text("", encoding="utf-8")
        (tmp_path / "composer.lock").write_text("{}", encoding="utf-8")
        (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

        found = detect.detect_manifests(tmp_path)

        assert found == {"pip": True, "composer": True, "npm": True}

    def test_no_manifests_runs_nothing(self, tmp_path: Path) -> None:
        found = detect.detect_manifests(tmp_path)

        assert found == {"pip": False, "composer": False, "npm": False}


class TestRenderReport:
    def test_reports_both_consulted_and_skipped_sources(self) -> None:
        report = detect.render_report({"pip": True, "composer": False, "npm": False})

        assert "consulted: pip" in report
        assert "skipped:   composer" in report
        assert "skipped:   npm" in report
