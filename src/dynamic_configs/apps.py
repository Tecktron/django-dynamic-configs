"""Django app configuration for django-dynamic-configs."""

from django.apps import AppConfig


class DynamicConfigsConfig(AppConfig):
    """The app's configuration; registers the system checks when Django starts."""

    name = "dynamic_configs"
    verbose_name = "Dynamic configs"

    def ready(self) -> None:
        """Import the modules that register checks and signal receivers."""
        from dynamic_configs import checks  # noqa: F401 - imported for its @register side effect
