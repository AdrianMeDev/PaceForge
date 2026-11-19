from django.apps import AppConfig
from django.core.checks import register


class CoreConfig(AppConfig):
    name = "core"

    def ready(self) -> None:
        from .checks import check_deployment, check_encryption_keys

        register(check_encryption_keys)
        register(check_deployment, deploy=True)
