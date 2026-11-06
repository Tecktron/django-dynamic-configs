# django-dynamic-configs

Typed runtime settings for Django that admins can add and edit in the Django admin, read from code through a small,
cached API.

**Status:** alpha, under active development. The design is in
[docs/design/django-dynamic-configs.md](docs/design/django-dynamic-configs.md).

## Known limitations

- **Datetimes in the admin keep whole seconds.** Like Django's own admin, the time input shows hours, minutes and
  seconds. A datetime set from code with fractions of a second loses them when its config is saved in the admin, even
  if the datetime itself wasn't changed. Keep such values in code (`dynamic_configs.update`).

## The admin's JSON editor

JSON settings get a small editor in the admin: a Format link, Enter that keeps the indent, a note saying whether the
JSON is valid (and where it isn't), and colours. It works on the text as typed and never re-encodes values, so numbers
too large or too precise for JavaScript are kept exactly.

The colours are CSS custom properties. Set any of them in your admin stylesheet to change them:

```css
:root {
    --dynamic-configs-json-key: #7a3e9d;
    --dynamic-configs-json-string: #a31515;
    --dynamic-configs-json-number: #098658;
    --dynamic-configs-json-literal: #0000ff;
    --dynamic-configs-json-punctuation: #6b6b6b;
    --dynamic-configs-json-error: #ba2121;
}
```

There's a dark set too. It follows the browser's light or dark preference, and the admin's theme toggle overrides it.

## Development

Set up a virtual environment in the repository and install the development requirements:

```
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

The browser tests (`tests/browser`, the admin's scripts in Chromium) need a browser. This installs one inside the
virtual environment, about 280 MB:

```
PLAYWRIGHT_BROWSERS_PATH=0 venv/bin/playwright install --only-shell chromium
```

Run the tests with coverage (100% branch coverage is required). The browser tests run last:

```
venv/bin/coverage run -m pytest
venv/bin/coverage report
```

Run the full matrix of Python and Django versions with tox (versions not installed locally are skipped). The matrix
skips the browser tests; the `browser` environment runs them once, installing its own Chromium:

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
