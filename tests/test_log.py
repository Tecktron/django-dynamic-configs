import logging

from dynamic_configs.log import log

logger = logging.getLogger("dynamic_configs.tests")


def test_records_carry_the_config_name_and_type(caplog):
    caplog.set_level(logging.INFO, logger="dynamic_configs")
    log(logger, logging.INFO, "Read config %r", "SITE_NAME", config_name="SITE_NAME", config_type="str")
    [record] = caplog.records
    assert record.getMessage() == "Read config 'SITE_NAME'"
    assert record.config_name == "SITE_NAME"
    assert record.config_type == "str"


def test_extras_are_left_off_when_not_given(caplog):
    caplog.set_level(logging.INFO, logger="dynamic_configs")
    log(logger, logging.INFO, "Built the registry")
    [record] = caplog.records
    assert not hasattr(record, "config_name")
    assert not hasattr(record, "config_type")


def test_nothing_is_logged_below_the_logger_level(caplog):
    caplog.set_level(logging.WARNING, logger="dynamic_configs")
    log(logger, logging.DEBUG, "Cache hit")
    assert caplog.records == []


def test_exception_details_are_attached_when_asked(caplog):
    try:
        raise ConnectionError("cache down")
    except ConnectionError:
        log(logger, logging.WARNING, "Cache read failed", exc_info=True)
    [record] = caplog.records
    assert record.exc_info[0] is ConnectionError


def test_logging_from_inside_a_handler_is_suppressed():
    class Reentrant(logging.Handler):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def emit(self, record):
            self.calls += 1
            log(logger, logging.WARNING, "nested")

    handler = Reentrant()
    logger.addHandler(handler)
    try:
        log(logger, logging.WARNING, "outer")
    finally:
        logger.removeHandler(handler)
    assert handler.calls == 1
