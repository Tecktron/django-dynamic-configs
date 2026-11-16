import decimal
from decimal import Decimal

import pytest

from dynamic_configs.types import iso4217
from dynamic_configs.types.money import (
    Money,
    MoneyCurrencySerializer,
    MoneySerializer,
    by_currency_then_amount,
    check_amount,
)
from dynamic_configs.types.registry import load_custom_type


def test_amounts_are_kept_with_exactly_two_places():
    assert check_amount(Decimal("10")) == Decimal("10.00")
    assert str(check_amount(Decimal("9.9"))) == "9.90"
    assert str(check_amount(Decimal("1E+1"))) == "10.00"


@pytest.mark.parametrize(
    ("amount", "message"),
    [
        (Decimal("9.990"), "at most 2 decimal places"),
        (Decimal("9.999"), "at most 2 decimal places"),
        (Decimal("NaN"), "finite"),
        (Decimal("1E+40"), "too large"),
    ],
)
def test_amounts_are_rejected_not_rounded(amount, message):
    with pytest.raises(ValueError, match=message):
        check_amount(amount)


def test_money_normalizes_its_amount_and_prints_with_the_currency():
    money = Money(Decimal("10"), "CAD")
    assert money.amount == Decimal("10.00")
    assert str(money) == "10.00 CAD"


def test_equal_money_is_equal_and_hashes_the_same():
    assert Money(Decimal("1"), "CAD") == Money(Decimal("1.00"), "CAD")
    assert len({Money(Decimal("1"), "CAD"), Money(Decimal("1.00"), "CAD")}) == 1


@pytest.mark.parametrize(
    ("amount", "currency", "message"),
    [
        (9.99, "CAD", "must be a Decimal"),
        (Decimal("9.999"), "CAD", "at most 2"),
        (Decimal("9.99"), "cad", "3-letter"),
        (Decimal("9.99"), "CA", "3-letter"),
        (Decimal("9.99"), 5, "3-letter"),
    ],
)
def test_invalid_money_cannot_be_created(amount, currency, message):
    with pytest.raises(ValueError, match=message):
        Money(amount, currency)


def test_the_amount_serializer_round_trips():
    assert MoneySerializer().serialize(Decimal("9.9")) == "9.90"
    assert MoneySerializer().deserialize(" 10 ") == Decimal("10.00")


@pytest.mark.parametrize("text", ["1e3", "1,000", "+5", "NaN", "Infinity", "9.990", "9.999", ""])
def test_the_amount_serializer_rejects_anything_but_plain_amounts(text):
    with pytest.raises(ValueError):
        MoneySerializer().deserialize(text)


def test_the_amount_serializer_rejects_extra_places_from_code():
    with pytest.raises(ValueError, match="at most 2"):
        MoneySerializer().serialize(Decimal("9.999"))


def test_the_currency_serializer_builds_on_the_amount_serializer():
    serializer = MoneyCurrencySerializer()
    assert isinstance(serializer, MoneySerializer)
    assert serializer.serialize(Money(Decimal("9.9"), "CAD")) == "9.90 CAD"
    assert serializer.deserialize(" 9.99 cad ") == Money(Decimal("9.99"), "CAD")


@pytest.mark.parametrize("text", ["9.99", "9.99 CAD extra", "9.999 CAD", "9.99 CADX", "CAD 9.99"])
def test_the_currency_serializer_rejects_bad_text(text):
    with pytest.raises(ValueError):
        MoneyCurrencySerializer().deserialize(text)


MONEY_CURRENCY = {
    "type": "dynamic_configs.types.money.Money",
    "serializer": "dynamic_configs.types.money.MoneyCurrencySerializer",
    "form": "dynamic_configs.forms.money.MoneyCurrencyField",
    "sort_key": "dynamic_configs.types.money.by_currency_then_amount",
}


def test_money_with_currency_sorts_by_currency_then_amount():
    values = [Money(Decimal("20"), "USD"), Money(Decimal("10"), "CAD"), Money(Decimal("5"), "USD")]
    expected = [Money(Decimal("10"), "CAD"), Money(Decimal("5"), "USD"), Money(Decimal("20"), "USD")]
    assert sorted(values, key=by_currency_then_amount) == expected
    # As the design document's entry enables it.
    assert load_custom_type("money_currency", MONEY_CURRENCY).sort(values) == expected


def test_money_ignores_the_threads_decimal_context():
    with decimal.localcontext(decimal.Context(prec=2, traps=[])):
        assert MoneySerializer().serialize(Decimal("1234.56")) == "1234.56"
        assert MoneyCurrencySerializer().serialize(Money(Decimal("1234.56"), "USD")) == "1234.56 USD"
        assert check_amount(Decimal("0.01")) == Decimal("0.01")


def test_an_amount_too_large_is_refused_not_written_as_nan_whatever_the_threads_context():
    with decimal.localcontext(decimal.Context(prec=28, traps=[])):
        with pytest.raises(ValueError, match="too large"):
            MoneySerializer().serialize(Decimal("1E+40"))


def test_currency_must_be_three_ascii_letters():
    with pytest.raises(ValueError):
        Money(Decimal("1"), "ıso")
    with pytest.raises(ValueError, match="currency"):
        MoneyCurrencySerializer().deserialize("1 ıso")
    assert MoneyCurrencySerializer().deserialize("1 usd") == Money(Decimal("1"), "USD")


@pytest.mark.parametrize(
    ("rounding", "text", "stored"),
    [
        (decimal.ROUND_HALF_UP, "9.946", "9.95"),
        (decimal.ROUND_HALF_UP, "9.945", "9.95"),
        (decimal.ROUND_HALF_EVEN, "9.945", "9.94"),
        (decimal.ROUND_DOWN, "-9.949", "-9.94"),
    ],
)
def test_money_rounds_entered_text(rounding, text, stored):
    serializer = MoneySerializer(rounding=rounding)
    assert serializer.serialize(serializer.deserialize(text)) == stored


def test_money_rounds_a_value_written_from_code():
    assert MoneySerializer(rounding=decimal.ROUND_HALF_UP).serialize(Decimal("9.946")) == "9.95"


@pytest.mark.parametrize(
    ("rounding", "amount"),
    [(decimal.ROUND_HALF_UP, "-0.004"), (None, "-0")],
    ids=["rounds_to_zero", "negative_zero"],
)
def test_a_zero_amount_is_stored_without_a_sign(rounding, amount):
    serializer = MoneySerializer(rounding=rounding)
    assert serializer.serialize(Decimal(amount)) == "0.00"
    assert str(serializer.deserialize(amount)) == "0.00"


def test_the_rounding_given_decides_not_the_thread_context():
    with decimal.localcontext() as context:
        context.rounding = decimal.ROUND_DOWN
        assert check_amount(Decimal("9.946"), rounding=decimal.ROUND_HALF_UP) == Decimal("9.95")


@pytest.mark.parametrize("serializer", [MoneySerializer(), MoneySerializer(rounding=None)])
def test_money_without_rounding_still_refuses_three_places(serializer):
    with pytest.raises(ValueError, match="at most 2 decimal places"):
        serializer.deserialize("9.946")


def test_rounding_still_refuses_an_amount_that_is_too_large():
    with pytest.raises(ValueError, match="too large"):
        check_amount(Decimal("1E+40"), rounding=decimal.ROUND_HALF_UP)


@pytest.mark.parametrize("rounding", sorted(MoneySerializer.ROUNDINGS))
def test_money_takes_each_of_decimals_roundings(rounding):
    assert MoneySerializer(rounding=rounding).rounding == rounding


@pytest.mark.parametrize("rounding", ["ROUND_SIDEWAYS", 1, ""])
def test_money_refuses_another_rounding(rounding):
    with pytest.raises(ValueError, match=r"rounding must be one of decimal's ROUND_\* constants"):
        MoneySerializer(rounding=rounding)


def test_money_currency_rounds_entered_text():
    s = MoneyCurrencySerializer(rounding=decimal.ROUND_HALF_UP)
    assert s.deserialize("9.946 cad") == Money(Decimal("9.95"), "CAD")


def test_money_currency_without_rounding_refuses_three_places():
    with pytest.raises(ValueError, match="at most 2 decimal places"):
        MoneyCurrencySerializer().deserialize("9.946 CAD")


def test_money_itself_still_refuses_three_places():
    with pytest.raises(ValueError, match="at most 2 decimal places"):
        Money(Decimal("9.946"), "CAD")


def test_the_currency_serializer_suggests_the_iso_list_by_default():
    assert MoneyCurrencySerializer().currencies == iso4217.CURRENCIES
    assert MoneyCurrencySerializer(currencies=None).currencies == iso4217.CURRENCIES


@pytest.mark.parametrize(
    ("currencies", "expected"),
    [
        (["USD", "CAD"], {"USD": "US Dollar", "CAD": "Canadian Dollar"}),
        (("CAD",), {"CAD": "Canadian Dollar"}),
        (["ABC"], {"ABC": ""}),
        ({"ABC": "Alphabet", "CAD": "Loonies"}, {"ABC": "Alphabet", "CAD": "Loonies"}),
        ({"ABC": ""}, {"ABC": ""}),
        ([], {}),
        ({}, {}),
    ],
)
def test_the_currency_serializer_normalizes_the_currencies_it_suggests(currencies, expected):
    serializer = MoneyCurrencySerializer(currencies=currencies)
    assert serializer.currencies == expected
    assert list(serializer.currencies) == list(expected)


@pytest.mark.parametrize(
    "currencies", ["CAD", ["cad"], ["CA"], ["CADX"], ["C1D"], [1], [None], 5, {"cad": "x"}, {"CAD": 1}]
)
def test_the_currency_serializer_refuses_bad_currencies(currencies):
    with pytest.raises(ValueError, match="currencies"):
        MoneyCurrencySerializer(currencies=currencies)


@pytest.mark.parametrize("currencies", [None, ["CAD"], []])
def test_suggestions_never_restrict_what_the_currency_serializer_reads(currencies):
    serializer = MoneyCurrencySerializer(currencies=currencies)
    assert serializer.deserialize("9.99 xyz") == Money(Decimal("9.99"), "XYZ")
