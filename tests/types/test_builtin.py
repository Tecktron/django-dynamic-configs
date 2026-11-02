from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from dynamic_configs.types.builtin import BUILTIN_TYPES

BY_KEY = {config_type.key: config_type for config_type in BUILTIN_TYPES}

SAMPLES = {
    "str": "Example",
    "text": "line one\nline two",
    "int": 42,
    "float": 0.5,
    "decimal": Decimal("19.99"),
    "bool": True,
    "date": date(2026, 11, 2),
    "datetime": datetime(2026, 11, 2, 17, 0, tzinfo=ZoneInfo("America/New_York")),
    "json": {"sizes": [1, 2]},
    "seconds": timedelta(seconds=90),
    "minutes": timedelta(minutes=1.5),
    "hours": timedelta(hours=1.5),
    "days": timedelta(days=2),
    "weeks": timedelta(weeks=1),
}


def test_the_built_in_keys():
    assert set(BY_KEY) == set(SAMPLES)


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_each_built_in_round_trips_a_sample(key):
    config_type = BY_KEY[key]
    assert config_type.from_text(config_type.to_text(SAMPLES[key])) == SAMPLES[key]


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_each_built_in_has_a_label_and_help_text(key):
    assert BY_KEY[key].label
    assert BY_KEY[key].help_text


def test_only_text_and_json_have_no_list_variants():
    assert {key for key, config_type in BY_KEY.items() if not config_type.listable} == {"text", "json"}
