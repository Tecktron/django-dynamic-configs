import re
from datetime import date

from dynamic_configs.types import iso4217


def test_codes_are_sorted_three_capitals():
    codes = list(iso4217.CURRENCIES)
    assert codes == sorted(codes)
    assert all(re.fullmatch(r"[A-Z]{3}", code) for code in codes)


def test_names_are_not_empty():
    assert all(name.strip() == name and name for name in iso4217.CURRENCIES.values())


def test_the_common_currencies_are_present():
    assert iso4217.CURRENCIES["CAD"] == "Canadian Dollar"
    assert {"USD", "EUR", "GBP", "JPY"} <= set(iso4217.CURRENCIES)


def test_testing_funds_and_metals_are_absent():
    assert not {"XTS", "XXX", "USN", "XAU"} & set(iso4217.CURRENCIES)


def test_published_is_a_date():
    assert date.fromisoformat(iso4217.PUBLISHED)


def test_source_is_the_six_group_list():
    assert iso4217.SOURCE.startswith("https://www.six-group.com/")
