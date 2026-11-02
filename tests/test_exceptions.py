from dynamic_configs.exceptions import ConfigError, ConfigTypeError, ConfigValueError


def test_type_errors_are_config_errors_and_type_errors():
    assert issubclass(ConfigTypeError, ConfigError)
    assert issubclass(ConfigTypeError, TypeError)


def test_value_errors_are_config_errors_and_value_errors():
    assert issubclass(ConfigValueError, ConfigError)
    assert issubclass(ConfigValueError, ValueError)
