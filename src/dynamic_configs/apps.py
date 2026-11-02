"""Django app configuration for django-dynamic-configs."""

from django.apps import AppConfig


class DynamicConfigsConfig(AppConfig):
    """The app's configuration; registers the system checks and signal receivers."""

    name = "dynamic_configs"
    verbose_name = "Dynamic configs"

    def ready(self) -> None:
        """Import the modules that register checks and signal receivers."""
        from dynamic_configs import checks, signals  # noqa: F401 - imported for their registration side effects
