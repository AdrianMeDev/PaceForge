"""The CI workflow generates its Django and encryption keys for every run."""

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
