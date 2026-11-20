"""The backup guide and the README are compared with the code, so that they cannot drift."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOC = (ROOT / "docs" / "backup-and-restore.md").read_text()
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
