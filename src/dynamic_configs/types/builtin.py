"""The built-in config types."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from dynamic_configs.types import serializers
from dynamic_configs.types.base import ConfigType

BUILTIN_TYPES: tuple[ConfigType, ...] = (
    ConfigType("str", "String", str, serializers.StrSerializer(), help_text="A single line of text."),
    ConfigType(
        "text",
        "Text",
        str,
        serializers.TextSerializer(),
        help_text="Text, which may span several lines.",
        listable=False,
    ),
    ConfigType("int", "Integer", int, serializers.IntSerializer(), help_text="A whole number, e.g. 42."),
    ConfigType("float", "Float", float, serializers.FloatSerializer(), help_text="A number, e.g. 0.5."),
    ConfigType(
        "decimal", "Decimal", Decimal, serializers.DecimalSerializer(), help_text="A decimal number, e.g. 19.99."
    ),
    ConfigType(
        "bool",
        "Boolean",
        bool,
        serializers.BoolSerializer(),
        help_text="true or false (yes/no, on/off and 1/0 also work).",
    ),
    ConfigType("date", "Date", date, serializers.DateSerializer(), help_text="A date as YYYY-MM-DD, e.g. 2026-11-02."),
    ConfigType(
        "datetime",
        "Date and time",
        datetime,
        serializers.DateTimeSerializer(),
        help_text=(
            "A date and time as YYYY-MM-DD HH:MM, optionally with seconds and a UTC offset; "
            "without an offset the site's time zone is used."
        ),
    ),
    ConfigType(
        "json", "JSON", (dict, list), serializers.JSONSerializer(), help_text="A JSON object or array.", listable=False
    ),
    ConfigType(
        "seconds",
        "Seconds",
        timedelta,
        serializers.SecondsSerializer(),
        help_text="A number of seconds, e.g. 90 or 1.5.",
    ),
    ConfigType(
        "minutes", "Minutes", timedelta, serializers.MinutesSerializer(), help_text="A number of minutes, e.g. 1.5."
    ),
    ConfigType("hours", "Hours", timedelta, serializers.HoursSerializer(), help_text="A number of hours, e.g. 1.5."),
    ConfigType("days", "Days", timedelta, serializers.DaysSerializer(), help_text="A number of days, e.g. 2."),
    ConfigType("weeks", "Weeks", timedelta, serializers.WeeksSerializer(), help_text="A number of weeks, e.g. 1."),
)
