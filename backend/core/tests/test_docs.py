"""The backup guide and the README are compared with the code, so that they cannot drift."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOC = (ROOT / "docs" / "backup-and-restore.md").read_text()
DEPLOYMENT = (ROOT / "docs" / "deployment.md").read_text()
README = (ROOT / "README.md").read_text()
SETTINGS = (ROOT / "backend" / "config" / "settings.py").read_text()
COMPOSE = (ROOT / "compose.prod.yaml").read_text()
COMMANDS = ROOT / "backend" / "core" / "management" / "commands"

BACKUP_VARIABLES = sorted(set(re.findall(r'env\.(?:str|int)\("(BACKUP_[A-Z_]+)"', SETTINGS)))


def row(text: str, name: str) -> str:
    """The table row of a variable in ``text``."""
    (line,) = [line for line in text.splitlines() if line.startswith(f"| `{name}`")]
    return line


class TestTheVariables:
    def test_every_backup_variable_is_in_the_readme(self) -> None:
        assert len(BACKUP_VARIABLES) == 5
        for name in BACKUP_VARIABLES:
            assert f"`{name}`" in README, name

    def test_every_backup_variable_is_in_the_guide(self) -> None:
        for name in BACKUP_VARIABLES:
            assert f"`{name}`" in DOC, name

    def test_the_documented_defaults_are_those_of_the_settings(self) -> None:
        for name, default in re.findall(r'env\.int\("(BACKUP_[A-Z_]+)", default=(\d+)\)', SETTINGS):
            assert f"`{default}`" in row(DOC, name), name
            assert f"`{default}`" in row(README, name), name

    def test_the_documented_ranges_are_those_of_the_settings(self) -> None:
        for lower, name, upper in re.findall(r"(\d+) <= (BACKUP_[A-Z_]+) <= (\d+)", SETTINGS):
            assert f"`{lower}` to `{upper}`" in row(DOC, name), name


class TestTheProxyTrust:
    def test_the_trust_setting_defaults_to_false_in_the_settings(self) -> None:
        assert 'env.bool("DJANGO_TRUST_PROXY_HEADERS", default=False)' in SETTINGS

    def test_the_readme_documents_the_trust_setting_and_its_default(self) -> None:
        assert "`false`" in row(README, "DJANGO_TRUST_PROXY_HEADERS")

    def test_the_deployment_guide_documents_the_trust_setting_and_its_default(self) -> None:
        assert "`DJANGO_TRUST_PROXY_HEADERS` defaults to `false`" in " ".join(DEPLOYMENT.split())


class TestTheCommands:
    def test_the_guide_names_the_commands_that_exist(self) -> None:
        for command in ("backup_db", "run_backups", "restore_db"):
            assert (COMMANDS / f"{command}.py").is_file(), command
            assert f"manage.py {command}" in DOC, command

    def test_the_guide_names_the_profile_of_the_backup_service(self) -> None:
        assert "profiles: [backup]" in COMPOSE
        assert "--profile backup" in DOC


class TestTheLinks:
    def test_the_readme_links_to_the_guide(self) -> None:
        assert "docs/backup-and-restore.md" in README
        assert "(#backup-and-restore)" in README

    def test_the_guide_links_to_existing_files(self) -> None:
        assert "(deployment.md" in DOC
        assert (ROOT / "docs" / "deployment.md").is_file()
        assert (ROOT / "README.md").is_file()


class TestTheDatabaseCredentials:
    def test_no_file_contains_the_old_development_password(self) -> None:
        files = [
            *ROOT.glob("compose*.yaml"),
            *ROOT.glob(".env*example"),
            ROOT / "backend" / "config" / "settings_test.py",
            ROOT / "README.md",
            ROOT / "docs" / "deployment.md",
            ROOT / "docs" / "backup-and-restore.md",
        ]
        assert len(files) >= 7
        for path in files:
            # The Compose project name `paceforge-dev` is not a password.
            text = path.read_text().replace("name: paceforge-dev", "")
            assert "paceforge-dev" not in text, path.name

    def test_the_deployment_guide_does_not_restrict_the_password(self) -> None:
        text = " ".join((ROOT / "docs" / "deployment.md").read_text().lower().split())
        assert "letters and digits only" not in text
        assert "letters and digits" not in text

    def test_the_readme_does_not_restrict_the_password(self) -> None:
        assert "letters and digits only" not in " ".join(README.lower().split())

    def test_existing_volumes_are_documented(self) -> None:
        deployment = (ROOT / "docs" / "deployment.md").read_text()
        for text in (README, deployment):
            assert "existing `pgdata` volume" in " ".join(text.split())
