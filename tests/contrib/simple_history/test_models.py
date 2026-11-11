import pytest
from django.core.management import call_command

import dynamic_configs
from dynamic_configs.models import Config

pytestmark = pytest.mark.django_db


def test_changes_from_code_are_recorded():
    dynamic_configs.get_or_create("SITE_NAME", "str", "Example")
    dynamic_configs.update("SITE_NAME", "Renamed")
    dynamic_configs.delete("SITE_NAME")
    history = Config.history.filter(name="SITE_NAME").order_by("history_date", "history_id")
    assert [(row.history_type, row.value) for row in history] == [("+", "Example"), ("~", "Renamed"), ("-", "Renamed")]


def test_the_history_lives_in_the_sub_app():
    assert Config.history.model._meta.app_label == "dynamic_configs_simple_history"


def test_the_migrations_match_the_models():
    call_command("makemigrations", "dynamic_configs_simple_history", check=True, dry_run=True)
