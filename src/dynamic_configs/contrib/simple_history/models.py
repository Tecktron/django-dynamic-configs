"""Record ``Config``'s history with django-simple-history, keeping the historical model in this app."""

import simple_history

from dynamic_configs.models import Config

simple_history.register(Config, app="dynamic_configs.contrib.simple_history")
