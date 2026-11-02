"""The built-in config types and the form field each uses in the admin."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import partial

from django import forms

from dynamic_configs.forms.fields import DurationUnitField
from dynamic_configs.forms.json import JSONTextField
from dynamic_configs.types import serializers
from dynamic_configs.types.base import ConfigType

BUILTIN_TYPES: tuple[ConfigType, ...] = (
    ConfigType(
        "str",
        "String",
        str,
        serializers.StrSerializer(),
        help_text="A single line of text.",
        form_class=forms.CharField,
    ),
    ConfigType(
        "text",
        "Text",
        str,
        serializers.TextSerializer(),
        help_text="Text, which may span several lines.",
        listable=False,
        # strip=False: leading spaces and blank lines in multi-line text are meaningful.
        form_class=partial(forms.CharField, widget=forms.Textarea, strip=False),
    ),
    ConfigType(
        "int",
        "Integer",
        int,
        serializers.IntSerializer(),
        help_text="A whole number, e.g. 42.",
        form_class=forms.IntegerField,
    ),
    ConfigType(
        "float",
        "Float",
        float,
        serializers.FloatSerializer(),
        help_text="A number, e.g. 0.5.",
        form_class=forms.FloatField,
    ),
    ConfigType(
        "decimal",
        "Decimal",
        Decimal,
        serializers.DecimalSerializer(),
        help_text="A decimal number, e.g. 19.99.",
        form_class=forms.DecimalField,
    ),
    ConfigType(
        "bool",
        "Boolean",
        bool,
        serializers.BoolSerializer(),
        help_text="true or false (yes/no, on/off and 1/0 also work).",
        form_class=forms.BooleanField,
    ),
    ConfigType(
        "date",
        "Date",
        date,
        serializers.DateSerializer(),
        help_text="A date as YYYY-MM-DD, e.g. 2026-11-02.",
        form_class=forms.DateField,
    ),
    ConfigType(
        "datetime",
        "Date and time",
        datetime,
        serializers.DateTimeSerializer(),
        help_text=(
            "A date and time as YYYY-MM-DD HH:MM, optionally with seconds and a UTC offset; "
            "without an offset the site's time zone is used."
        ),
        form_class=forms.SplitDateTimeField,
    ),
    ConfigType(
        "json",
        "JSON",
        (dict, list),
        serializers.JSONSerializer(),
        help_text="A JSON object or array.",
        listable=False,
        form_class=JSONTextField,
    ),
    ConfigType(
        "seconds",
        "Seconds",
        timedelta,
        serializers.SecondsSerializer(),
        help_text="A number of seconds, e.g. 90 or 1.5.",
        form_class=partial(DurationUnitField, "seconds"),
    ),
    ConfigType(
        "minutes",
        "Minutes",
        timedelta,
        serializers.MinutesSerializer(),
        help_text="A number of minutes, e.g. 1.5.",
        form_class=partial(DurationUnitField, "minutes"),
    ),
    ConfigType(
        "hours",
        "Hours",
        timedelta,
        serializers.HoursSerializer(),
        help_text="A number of hours, e.g. 1.5.",
        form_class=partial(DurationUnitField, "hours"),
    ),
    ConfigType(
        "days",
        "Days",
        timedelta,
        serializers.DaysSerializer(),
        help_text="A number of days, e.g. 2.",
        form_class=partial(DurationUnitField, "days"),
    ),
    ConfigType(
        "weeks",
        "Weeks",
        timedelta,
        serializers.WeeksSerializer(),
        help_text="A number of weeks, e.g. 1.",
        form_class=partial(DurationUnitField, "weeks"),
    ),
)
