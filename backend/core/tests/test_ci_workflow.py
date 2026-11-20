"""The CI workflow generates its keys for every run and verifies the PostgreSQL APT key."""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from core.checks import check_deployment, check_encryption_keys

WORKFLOW = (Path(__file__).resolve().parents[3] / ".github" / "workflows" / "ci.yml").read_text()
OLD_ENCRYPTION_KEY = "3VhtVIgjC8S15ZApZIqUaGw52HQvk1KVgF2w1PkHWWk="
OLD_SECRET_KEY = "ci-only-secret-key-not-for-production"
PGDG_FINGERPRINT = "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8"
OTHER_FINGERPRINT = "B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CD8"
SUBKEY_FINGERPRINT = "0123456789ABCDEF0123456789ABCDEF01234567"


def generation_step() -> str:
    """The workflow step that generates the keys, up to the next step."""
    start = WORKFLOW.index("- name: Generate Django and encryption keys")
    end = WORKFLOW.index("\n      - ", start + 1)
    return WORKFLOW[start:end]


def generated_value(marker: str) -> str:
    """Run the generator snippet of the workflow that contains ``marker``, as the runner does."""
    (snippet,) = [
        code
        for code in re.findall(r"uv run python -c '([^']+)'", generation_step())
        if marker in code
    ]
    result = subprocess.run(
        [sys.executable, "-c", snippet], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


class TestTheJobHasNoStaticKeys:
    def test_no_key_is_set_in_the_job_environment(self) -> None:
        assert not re.search(r"^\s*(ENCRYPTION_KEY|DJANGO_SECRET_KEY):", WORKFLOW, re.MULTILINE)

    def test_the_former_values_are_gone(self) -> None:
        assert OLD_ENCRYPTION_KEY not in WORKFLOW
        assert OLD_SECRET_KEY not in WORKFLOW


class TestTheGenerationStep:
    def test_it_generates_both_keys_in_the_required_formats(self) -> None:
        step = generation_step()
        assert "Fernet.generate_key().decode()" in step
        assert "secrets.token_urlsafe(48)" in step

    def test_it_exports_both_keys_to_github_env(self) -> None:
        exported = dict(re.findall(r'echo "(\w+)=\$(\w+)" >> "\$GITHUB_ENV"', generation_step()))
        assert exported == {"ENCRYPTION_KEY": "encryption_key", "DJANGO_SECRET_KEY": "secret_key"}

    def test_it_masks_both_values_before_they_are_exported(self) -> None:
        step = generation_step()
        masked = re.findall(r'::add-mask::\$(\w+)"', step)
        assert set(masked) == {"encryption_key", "secret_key"}
        assert step.index("::add-mask::") < step.index("GITHUB_ENV")

    def test_it_runs_after_the_install_and_before_the_migrations_and_tests(self) -> None:
        assert WORKFLOW.index("uv sync --frozen") < WORKFLOW.index(
            "- name: Generate Django and encryption keys"
        )
        assert WORKFLOW.index("- name: Generate Django and encryption keys") < WORKFLOW.index(
            "makemigrations --check"
        )
        assert WORKFLOW.index("- name: Generate Django and encryption keys") < WORKFLOW.index(
            "pytest -n auto"
        )


class TestTheGeneratedKeys:
    def test_each_run_generates_new_keys(self) -> None:
        assert generated_value("Fernet") != generated_value("Fernet")
        assert generated_value("token_urlsafe") != generated_value("token_urlsafe")

    def test_the_encryption_key_passes_check_encryption_keys(self, settings: Any) -> None:
        settings.ENCRYPTION_KEYS = [generated_value("Fernet")]
        assert check_encryption_keys(None) == []

    def test_the_secret_key_passes_check_deployment(
        self, settings: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings.DEBUG = False
        settings.ALLOWED_HOSTS = ["paceforge.example"]
        settings.CSRF_TRUSTED_ORIGINS = []
        monkeypatch.setitem(settings.DATABASES["default"], "PASSWORD", "ci-test-password")
        settings.SECRET_KEY = generated_value("token_urlsafe")
        assert check_deployment(None) == []


def key_step() -> str:
    """The workflow step that verifies and installs the PostgreSQL APT key, up to the next step."""
    start = WORKFLOW.index("- name: Install PostgreSQL 17 client tools")
    end = WORKFLOW.index("\n      - ", start + 1)
    return WORKFLOW[start:end]


def key_step_script() -> str:
    """The shell script of the key step, dedented as the runner sees it."""
    body = key_step().split("run: |\n", 1)[1]
    return "\n".join(line[10:] for line in body.splitlines() if line.strip())


def colon_listing(*records: tuple[str, str]) -> str:
    """Output of ``gpg --show-keys --with-colons``: one record line and one fpr line per key."""
    lines = []
    for record, fingerprint in records:
        lines.append(f"{record}:u:4096:1:{fingerprint[-16:]}:1700000000:::u:::scSC:::::::23::0:")
        lines.append(f"fpr:::::::::{fingerprint}:")
    return "\n".join(lines) + "\n"


def write_fake(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def run_key_step(tmp_path: Path, gpg_output: str) -> tuple[subprocess.CompletedProcess[str], str]:
    """Run the key step with fake curl, gpg and sudo; return the result and the sudo calls."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    gpg_listing = tmp_path / "gpg-listing.txt"
    gpg_listing.write_text(gpg_output)
    sudo_log = tmp_path / "sudo.log"
    # curl: the key file is the argument after -o; gpg prints the canned listing.
    write_fake(bin_dir, "curl", 'printf "fake key" > "$3"')
    write_fake(bin_dir, "gpg", f"cat '{gpg_listing}'")
    write_fake(bin_dir, "sudo", f"printf '%s\\n' \"$*\" >> '{sudo_log}'\ncat > /dev/null")
    script = tmp_path / "key-step.sh"
    script.write_text(key_step_script())
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    result = subprocess.run(
        ["bash", "-eo", "pipefail", str(script)], capture_output=True, text=True, env=env
    )
    sudo_calls = sudo_log.read_text() if sudo_log.exists() else ""
    return result, sudo_calls


class TestThePostgresKeyIsVerifiedBeforeItIsTrusted:
    def test_the_key_is_not_downloaded_into_the_keyring_directory(self) -> None:
        step = key_step()
        assert not [
            line for line in step.splitlines() if "curl" in line and "postgresql-common" in line
        ]
        assert "sudo curl" not in step

    def test_the_full_pgdg_fingerprint_is_checked(self) -> None:
        assert f"expected_fingerprint={PGDG_FINGERPRINT}" in key_step()

    def test_nothing_is_installed_before_the_fingerprint_check(self) -> None:
        step = key_step()
        check = step.index(PGDG_FINGERPRINT)
        assert check < step.index("sudo ")
        assert check < step.index("sudo install -m 0644")
        assert check < step.index("pgdg.list")

    def test_a_matching_key_is_installed_and_registered(self, tmp_path: Path) -> None:
        listing = colon_listing(("pub", PGDG_FINGERPRINT), ("sub", SUBKEY_FINGERPRINT))
        result, sudo_calls = run_key_step(tmp_path, listing)
        assert result.returncode == 0, result.stderr
        assert "install -m 0644" in sudo_calls
        assert "tee /etc/apt/sources.list.d/pgdg.list" in sudo_calls

    def test_a_mismatched_key_is_rejected_before_anything_is_installed(
        self, tmp_path: Path
    ) -> None:
        result, sudo_calls = run_key_step(tmp_path, colon_listing(("pub", OTHER_FINGERPRINT)))
        assert result.returncode != 0
        assert "fingerprint mismatch" in result.stderr
        assert sudo_calls == ""

    def test_a_listing_with_a_second_primary_key_is_rejected(self, tmp_path: Path) -> None:
        listing = colon_listing(("pub", PGDG_FINGERPRINT), ("pub", OTHER_FINGERPRINT))
        result, sudo_calls = run_key_step(tmp_path, listing)
        assert result.returncode != 0
        assert sudo_calls == ""

    def test_the_expected_fingerprint_on_a_subkey_alone_is_rejected(self, tmp_path: Path) -> None:
        listing = colon_listing(("pub", OTHER_FINGERPRINT), ("sub", PGDG_FINGERPRINT))
        result, sudo_calls = run_key_step(tmp_path, listing)
        assert result.returncode != 0
        assert sudo_calls == ""

    def test_an_empty_listing_is_rejected(self, tmp_path: Path) -> None:
        result, sudo_calls = run_key_step(tmp_path, "")
        assert result.returncode != 0
        assert sudo_calls == ""


REPO_ROOT = Path(__file__).resolve().parents[3]
M2_TEST_FILES = [
    ".github/workflows/ci.yml",
    "backend/planning/tests/test_generation.py",
    "backend/season/tests/test_generation.py",
    "backend/chat/tests/test_api.py",
    "backend/chat/tests/test_services.py",
    "backend/coach/tests/test_services.py",
    "backend/jobs/tests/test_commands.py",
    "backend/reviews/tests/test_comment_api.py",
    "backend/season/tests/test_plans_api.py",
    "backend/season/tests/test_reassessment_acceptance.py",
    "frontend/src/app/core/coach/coach-api.spec.ts",
]


class TestNoLiveShapedProviderKeysInM2Files:
    @pytest.mark.parametrize("path", M2_TEST_FILES)
    def test_no_sk_ant_literal_remains(self, path: str) -> None:
        assert "sk-ant-" not in (REPO_ROOT / path).read_text()
