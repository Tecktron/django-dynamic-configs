from dynamic_configs.conf import DEFAULTS, get_settings


def test_defaults_apply_when_the_setting_is_absent():
    assert dict(get_settings()) == DEFAULTS


def test_project_values_override_the_defaults(settings):
    settings.DYNAMIC_CONFIGS = {"TIMEOUT": 60}
    assert get_settings()["TIMEOUT"] == 60
    assert get_settings()["CACHE"] == "default"


def test_a_setting_that_is_not_a_dict_falls_back_to_the_defaults(settings):
    # The system checks report the mistake; at runtime the defaults keep things working.
    settings.DYNAMIC_CONFIGS = "not a dict"
    assert dict(get_settings()) == DEFAULTS


def test_changes_to_other_settings_keep_the_cached_values(settings):
    first = get_settings()
    settings.USE_TZ = True
    assert get_settings() is first
