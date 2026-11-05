# django-dynamic-configs

Typed runtime settings for Django that admins can add and edit in the Django admin, read from code through a small,
cached API.

**Status:** alpha, under active development. The design is in
[docs/design/django-dynamic-configs.md](docs/design/django-dynamic-configs.md).

## Known limitations

- **Datetimes in the admin keep whole seconds.** Like Django's own admin, the time input shows hours, minutes and
  seconds. A datetime set from code with fractions of a second loses them when its config is saved in the admin, even
  if the datetime itself wasn't changed. Keep such values in code (`dynamic_configs.update`).

## Development

Set up a virtual environment in the repository and install the development requirements:

```
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

Run the tests with coverage (100% branch coverage is required):

```
venv/bin/coverage run -m pytest
venv/bin/coverage report
```

Run the full matrix of Python and Django versions with tox (versions not installed locally are skipped):

```
venv/bin/tox
```

tox refuses to build in a group-writable directory. If your umask is `0002` (common on Linux, where each user has
their own group), tox fails with "package staging path ... can be changed by another account". Set a stricter umask
for that terminal first, and remove any `.tox/` directory created under the old one:

```
umask 022
rm -rf .tox
venv/bin/tox
```

## License

MIT. See [LICENSE](LICENSE).
