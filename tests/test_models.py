import pytest
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.management import call_command

from dynamic_configs.exceptions import ConfigError
from dynamic_configs.models import Config, ConfigDoesNotExist


def test_str_is_the_name():
    assert str(Config(name="SITE_NAME")) == "SITE_NAME"


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["SITE_NAME", "A", "MAX_2_RETRIES"])
def test_upper_snake_case_names_are_valid(name):
    Config(name=name, type="str", value="x").full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("name", ["site_name", "2FAST", "SITE NAME", "SITE_NAME\n", "_SITE"])
def test_other_names_are_invalid(name):
    with pytest.raises(ValidationError) as error:
        Config(name=name, type="str", value="x").full_clean()
    assert "name" in error.value.error_dict


def test_does_not_exist_is_catchable_three_ways():
    assert issubclass(ConfigDoesNotExist, ConfigError)
    assert issubclass(ConfigDoesNotExist, Config.DoesNotExist)
    assert issubclass(ConfigDoesNotExist, ObjectDoesNotExist)


@pytest.mark.django_db
def test_migrations_match_the_model():
    call_command("makemigrations", "dynamic_configs", check=True, dry_run=True)
