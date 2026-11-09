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

JSON settings get a small editor in the admin: a Format link, Enter that keeps the indent, a closing bracket on its own
line that steps back a level, a note saying whether the JSON is valid (and where it isn't), and colours. It works on the text as typed and never re-encodes values, so integers
too large for JavaScript are kept exactly. (Saving stores numbers as Python's `json` reads them: integers exactly,
other numbers as floats, so `1.10` is saved as `1.1`.)

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

## The admin's list editor

List and set settings are edited one item at a time. Each item gets its type's own input (a number box, the date picker,
a datetime's date, time and zone), and the server checks it when you click Add or Update. Select an item to load it back
into the input. Remove, Up and Down act on the selected item, and Sort orders the list by value, flipping direction on
each click; sets have no Up, Down or Sort. Raw mode edits the whole list as text, one item per line, for pasting. Every
line is an item, blank ones included (for a type that rejects an empty value, such as a number, a blank line is an
error), and Apply says which lines were blank. Without JavaScript, the field is that text. Each way of entering items
has its own help: the item editor describes its input (a boolean's checkbox: "Checked means true."), and raw mode what
to type on each line.

Saving from the list keeps each item exactly: spaces at the ends, empty items and line breaks within an item all
survive. Raw mode and the field without JavaScript strip each line as the item's own input would (the table below says
how for strings). A list with an item containing a line break, or a list of one empty item, can't be shown one item per
line, so raw mode won't open for it, and without JavaScript the field is read-only and saving keeps the list as it is.

A custom type's `form` checks each item added or updated in the list. Raw mode, the field without JavaScript and saving
check items with the type's serializer only. So put any rule a value must always follow in the serializer's
`deserialize`, and use `form` for how the value is entered.

A custom type can say how its lists sort with `sort_key` (the dotted path of a function from an item to what to sort
by) or `sort_compare` (the dotted path of a function comparing two items) in its `TYPES` entry. Without either, a list
sorts by its values when their class defines an order, and otherwise has no Sort.

### Spaces in typed strings

`DYNAMIC_CONFIGS["STRIP_STRINGS"]` decides whether the admin strips spaces from the ends of strings typed in a
single-line input (`str` values and items, and custom types without a `form`):

| `STRIP_STRINGS`  | A single value | List and set items |
|------------------|----------------|--------------------|
| `None` (default) | stripped       | kept exactly       |
| `True`           | stripped       | stripped           |
| `False`          | kept exactly   | kept exactly       |

Values set from code are always stored exactly, and multi-line `text` is never stripped.

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
skips the browser tests; the `browser-django52` and `browser-django61` environments run them on the oldest and newest
Django, each installing its own Chromium:

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
