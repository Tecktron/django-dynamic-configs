from django.apps import apps
from django.core import checks

from dynamic_configs.contrib.simple_history.checks import check_simple_history_installed


def test_the_sub_app_needs_simple_history_installed(mocker):
    mocker.patch.object(apps, "is_installed", return_value=False)
    [error] = check_simple_history_installed()
    assert (error.id, error.level) == ("dynamic_configs.E101", checks.ERROR)
    assert error.msg == (
        'dynamic_configs.contrib.simple_history is installed, but "simple_history" isn\'t in INSTALLED_APPS.'
    )
    assert error.hint == 'Add "simple_history" to INSTALLED_APPS.'


def test_with_simple_history_installed_there_is_no_error():
    assert check_simple_history_installed() == []
