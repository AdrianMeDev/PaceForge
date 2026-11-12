from django.apps import AppConfig


class SampleConfig(AppConfig):
    """Test-only app that provides a concrete ``OwnedModel`` (no migrations; tables are synced)."""

    name = "core.tests.sample"
    label = "core_sample"
