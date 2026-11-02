"""The Config model: one row per setting, its value stored as text."""

import re

from django.core.validators import RegexValidator
from django.db import models

from dynamic_configs.exceptions import ConfigError

# \Z rather than $, which would also accept a trailing newline.
NAME_REGEX = re.compile(r"\A[A-Z][A-Z0-9_]*\Z")
name_validator = RegexValidator(
    NAME_REGEX,
    "Names must be UPPER_SNAKE_CASE: a capital letter, then capital letters, digits and underscores.",
)


class Config(models.Model):
    """A runtime setting: a unique name, a type key from the registry, and the value stored as text."""

    name = models.CharField(
        max_length=255,
        primary_key=True,
        validators=[name_validator],
        help_text="UPPER_SNAKE_CASE; code reads the setting by this name.",
    )
    # No choices=: Django writes choices into migrations, so every project that added a custom type would get a
    # spurious migration. The admin and the API validate the type against the registry instead.
    type = models.CharField(max_length=64)
    value = models.TextField(null=True, blank=True, help_text="The value as stored text; empty (NULL) means None.")
    allow_null = models.BooleanField(default=False, help_text="Whether the value may be empty (None).")
    description = models.TextField(blank=True, default="", help_text="Optional notes for admins.")
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)

    class Meta:
        """Model options: list configs by name."""

        ordering = ["name"]
        verbose_name = "config"
        verbose_name_plural = "configs"

    def __str__(self) -> str:
        """Return the setting's name."""
        return self.name


class ConfigDoesNotExist(ConfigError, Config.DoesNotExist):  # noqa: N818 - named like Django's DoesNotExist
    """The config doesn't exist; also catchable as ``Config.DoesNotExist`` and ``ObjectDoesNotExist``."""
