# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-11-13

### Added

- Typed runtime settings stored in the database (`dynamic_configs.models.Config`): each has a unique name, a type, a
  value and an optional description, and admins can add, edit and delete them.
- The API: `get`, `get_or_create`, `update` and `delete`, with async variants `aget`, `aget_or_create`, `aupdate` and
  `adelete`, and the exceptions `ConfigError`, `ConfigDoesNotExist`, `ConfigTypeError` and `ConfigValueError`. A
  `get` given a default never raises.
- Built-in types: `str`, `text`, `int`, `float`, `decimal`, `bool`, `date`, `datetime` (following Django's time zone
  settings), `json` (an object or array, nested at most 128 levels deep), and the durations `seconds`, `minutes`,
  `hours`, `days` and `weeks`.
- List and set variants of every type except `json` (`list:<key>`, `set:<key>`).
- Custom types declared in `DYNAMIC_CONFIGS["TYPES"]`: a class, a serializer, and optionally a form field, help text,
  raw-mode help text, a sort key or compare function, and `options` (keyword arguments for the serializer). Nothing an
  admin enters is ever imported, evaluated or executed.
- Cached reads through any Django cache, one entry per setting, refreshed when a save or delete commits; a missing
  setting is cached too.
- System checks for the `DYNAMIC_CONFIGS` setting (`dynamic_configs.E001` to `E005`) and the admin
  (`dynamic_configs.W001` and `E006`).
- The admin, built on stock admin pages so admin skins apply: a two-step add page, each type's own form field, a JSON
  editor (formatting, a validity note, colours and a whitespace view), a list editor (an item editor, a raw mode for
  pasting, and sorting), whole-number inputs that trim a typed decimal to its whole part, and number inputs whose
  arrows count from multiples of their step.
- Test helpers that need neither the database nor the cache: `dynamic_configs.test.override_configs`, and a pytest
  plugin with the `config_overrides` fixture.
- Example custom types, not registered by default: `money` (an amount with at most 2 decimal places) and
  `money_currency` (an amount and a currency code). An amount with more than 2 places is refused,
  unless the type's `options` set a `rounding`.
- Currency suggestions for `money_currency`: its currency input offers the ISO 4217 codes (from SIX Group, with their
  names) as you type, or the codes and labels of a `currencies` option; the suggestions never restrict what is entered.
  A monthly workflow checks the list and opens a pull request when it changes.
- An optional django-simple-history integration (`dynamic_configs.contrib.simple_history`, installed with the
  `simple-history` extra) that records every change and adds the History button to the admin, with the system checks
  `dynamic_configs.E101` and `E102`. Restoring a past version never changes a config's type.
