from decimal import Decimal

import pytest

from dynamic_configs.types.money import Money, MoneyCurrencySerializer, MoneySerializer, check_amount


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
