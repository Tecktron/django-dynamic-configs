"""Django app configuration for the django-simple-history integration."""

from django.apps import AppConfig


class SimpleHistoryConfig(AppConfig):
    """The integration's app; it holds the historical model and its migration."""

    name = "dynamic_configs.contrib.simple_history"
    label = "dynamic_configs_simple_history"
    verbose_name = "Dynamic configs history"

    def ready(self) -> None:
        """Import the module that registers the system check."""
        from dynamic_configs.contrib.simple_history import checks  # noqa: F401 - imported for its registration
