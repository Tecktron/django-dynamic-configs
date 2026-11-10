import pytest
from django.core.management import call_command

from dynamic_configs.checks import check_settings

COLOR = {"type": "tests.custom_types.Color", "serializer": "tests.custom_types.ColorSerializer"}


def ids(messages):
    return [message.id for message in messages]


def test_defaults_pass():
    assert check_settings() == []


def test_the_check_runs_with_manage_py_check():
    call_command("check")


def test_a_valid_full_setting_passes(settings):
    settings.DYNAMIC_CONFIGS = {"CACHE": None, "TIMEOUT": None, "TYPES": {"color": COLOR}, "REGISTER_ADMIN": False}
    assert check_settings() == []


def test_the_setting_must_be_a_dict(settings):
    settings.DYNAMIC_CONFIGS = ["CACHE"]
    assert ids(check_settings()) == ["dynamic_configs.E001"]


def test_unknown_keys_are_reported_with_a_hint(settings):
    settings.DYNAMIC_CONFIGS = {"CACHES": "default"}
    [message] = check_settings()
    assert message.id == "dynamic_configs.E001"
    assert "'CACHES'" in message.msg
    assert "CACHE, TIMEOUT, TYPES, REGISTER_ADMIN" in message.hint


@pytest.mark.parametrize(("cache", "expected"), [(5, "dynamic_configs.E001"), ("missing", "dynamic_configs.E005")])
def test_the_cache_must_be_a_configured_alias(settings, cache, expected):
    settings.DYNAMIC_CONFIGS = {"CACHE": cache}
    assert ids(check_settings()) == [expected]


@pytest.mark.parametrize("timeout", [True, "300", -1, 1.5])
def test_the_timeout_must_be_a_non_negative_whole_number(settings, timeout):
    settings.DYNAMIC_CONFIGS = {"TIMEOUT": timeout}
    assert ids(check_settings()) == ["dynamic_configs.E001"]


def test_register_admin_must_be_a_boolean(settings):
    settings.DYNAMIC_CONFIGS = {"REGISTER_ADMIN": "yes"}
    assert ids(check_settings()) == ["dynamic_configs.E001"]


def test_types_must_be_a_dict(settings):
    settings.DYNAMIC_CONFIGS = {"TYPES": ["color"]}
    assert ids(check_settings()) == ["dynamic_configs.E001"]


def test_each_bad_type_is_reported_with_its_own_id(settings):
    settings.DYNAMIC_CONFIGS = {
        "TYPES": {
            "missing": {**COLOR, "type": "tests.custom_types.Missing"},
            "badform": {**COLOR, "form": "tests.custom_types.Color"},
            "color": COLOR,
        }
    }
    assert sorted(ids(check_settings())) == ["dynamic_configs.E002", "dynamic_configs.E004"]


@pytest.mark.parametrize("value", [True, False, None])
def test_strip_strings_accepts_true_false_or_none(settings, value):
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": value}
    assert check_settings() == []


@pytest.mark.parametrize("value", ["yes", 1, 0])
def test_strip_strings_must_be_true_false_or_none(settings, value):
    # 1 and 0 compare equal to True and False, so the check must test the type, not membership.
    settings.DYNAMIC_CONFIGS = {"STRIP_STRINGS": value}
    [message] = check_settings()
    assert message.id == "dynamic_configs.E001"
    assert message.msg == "DYNAMIC_CONFIGS['STRIP_STRINGS'] must be True, False or None."
