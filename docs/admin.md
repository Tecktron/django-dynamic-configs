# Admin and skins

Settings are edited in the Django admin, under **Configs**. The admin ships **no templates** of its own: it uses the
stock `ModelAdmin` pages, so admin skins apply. Its scripts are optional and every page works without them:
`dynamic_configs/admin.js` fills in defaults and saves clicks, `dynamic_configs/json_editor.js` is the JSON editor and
`dynamic_configs/list_editor.js` the list editor, with `dynamic_configs/admin.css`, which styles only the editors' own
elements. You can still override the standard templates (`admin/dynamic_configs/config/change_form.html`).

Permissions are Django's standard add, change, delete and view permissions on configs.

## The list page

The list shows each setting's name, type, value and description, and when it was last modified. The value is a
preview: list and set items are joined with `, `, and long values are cut short. You can search names and
descriptions, and filter by type.

## Adding a setting

Adding takes two steps, so the value can use its type's own input:

1. Choose the type (every registered type, list and set variants included) and click **Save**. With the admin
   script, choosing a type moves on without the click.
2. Enter the name, the value, whether it may be empty (**Allow null**) and an optional description, and save. The
   type is shown read-only. A boolean gets a yes/no/unknown choice here, since whether the setting allows None isn't
   known until it's saved.

The second step's address is `add/?type=<key>`, so you can link straight to it. An unknown `?type=` shows the first
step again.

## Changing a setting

The name and type are read-only. The value uses its type's input: a checkbox, a date picker, the JSON editor, the
list editor, and so on. Django's plain date, date-and-time and textarea widgets are swapped for the admin's versions;
a type's own widget is never replaced.

## Empty values

On both pages, an empty value is saved as `None` when **Allow null** is checked. When it isn't, an empty value is the
empty string for `str` and `text`, an empty list or set for list and set types, and a "required" error for every other
type. (So a `str` setting that allows null can't hold the empty string through the admin; code can still `update` it
to `""`.)

## Spaces in typed strings

The name is always stripped, and `text` values and descriptions are kept exactly as typed.
`DYNAMIC_CONFIGS["STRIP_STRINGS"]` decides whether the admin strips spaces from the ends of strings typed in a
single-line input (`str` values and items, and custom types without a `form`):

| `STRIP_STRINGS`  | A single value | List and set items |
|------------------|----------------|--------------------|
| `None` (default) | stripped       | kept exactly       |
| `True`           | stripped       | stripped           |
| `False`          | kept exactly   | kept exactly       |

Values set from code are always stored exactly, and multi-line `text` is never stripped.

## Datetimes

With `USE_TZ` on, a datetime is entered as a date, a time and a time zone: the admin's date and time pickers plus a
select of IANA zones. Its help reads "A date, a time and the time zone they're in."

- Each zone is labelled with its current UTC offset, such as `America/New_York (-5:00)`. The zones run from the most
  negative offset to the most positive, by name within an offset, with UTC first among those at `+0:00`. `localtime`
  and `Factory` aren't offered, since they aren't real zones. The labels follow daylight saving, refreshed hourly.
- The select starts on the current time zone (`TIME_ZONE`, unless your project activates another), and a stored value
  is shown in that zone. UTC stands in when the select doesn't offer the current zone (a fixed offset your project
  activates) or a value can't be moved into it (near year 1 or 9999), so the page opens and saving it untouched keeps
  the instant.
- With the admin script, an empty value starts on the browser's own zone instead, and each widget's Today and Now
  links and time zone note follow the zone chosen beside it. "My zone | Server zone" links beside the select pick the
  browser's zone or `TIME_ZONE`; a link is left out when the select doesn't offer its zone.
- A time that a daylight-saving change skips or repeats is a form error, rather than guessed: "2026-03-08 02:30:00
  couldn't be interpreted in time zone America/New_York; it may be ambiguous or it may not exist."

With `USE_TZ` off there are no zones to choose: the value uses Django's split date and time pickers, and its help
reads "A date and a time. Times are in the server's time zone (<TIME_ZONE>)."

In the list editor, an item of a `list:datetime` or `set:datetime` is entered in the datetime's own fields (date, time
and zone). In raw mode, and without JavaScript, items are typed as text, one per line; an item can carry its zone as a
UTC offset (`2026-11-02 17:00+09:00`), and one without is in `TIME_ZONE`.

## The JSON editor

JSON settings get a small editor: a **Format** link, Enter that keeps the indent, a closing bracket on its own line
that steps back a level, a note saying whether the JSON is valid (and where it isn't), and colours. It works on the
text as typed and never re-encodes values, so integers too large for JavaScript (`12345678901234567890`) are kept
exactly. (Saving stores numbers as Python's `json` reads them: integers exactly, other numbers as floats, so `1.10` is
saved as `1.1`.)

- **Format** re-indents the value, two spaces per level. On invalid JSON, or JSON nested too deeply, it changes nothing
  and moves the cursor to the problem.
- **Enter** keeps the line's indent, adds a level after `{` or `[`, and between a pair of brackets puts the closing one
  on its own line. Tab is left alone, so it still moves to the next field.
- A **closing bracket** typed on a line of nothing but indent steps back a level, in the same undo step.
- A **note** under the field says "Valid JSON." or where and why it isn't ("Invalid JSON at line 2, column 7: expected
  ":"."). A lone number or string gets the server's own "Enter a JSON object or array.". JSON nested deeper than the
  [limit of 128 levels](types.md) gets "The JSON is nested too deeply at line 1, column 129: the limit is 128
  levels.", pointing at the bracket that goes over. An empty field gets no note.
- Edits go through the browser's undo.

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
The token where the JSON breaks is underlined. If your stylesheet changes the editor's font, padding or size so the
colours would no longer line up with the text, the colours turn off and the plain textarea shows; without `admin.css`
they never start, and Format and the note still work.

## The list editor

List and set settings are edited one item at a time. Each item gets its type's own input (a number box, the date
picker, a datetime's date, time and zone, a custom type's own widget), and the server checks it when you click **Add**
or **Update**. Select an item to load it back into the input; **Clear** empties the input and deselects the list.
**Remove**, **Up** and **Down** act on the selected item, and **Sort** orders the list by value, flipping direction on
each click; sets have no Up, Down or Sort, and Sort is shown only when the item type can be sorted (see
[Sorting](types.md#sorting)). A set rejects a repeat ("That's already in the set."), compared after parsing.

**Raw mode** edits the whole list as text, one item per line, for pasting and bulk edits. **Apply** has the server
check every line; if all pass they become the list, otherwise raw mode stays open with each failing line's error.
**Cancel** returns to the list unchanged. Every line is an item, blank ones included (for a type that rejects an empty
value, such as a number, a blank line is an error), and Apply says which lines were blank ("Lines 2 and 3 were blank,
so they were added as blank items."). An empty textarea is an empty list. Without JavaScript, the field is that text.

Each way of entering items has its own help: the item editor describes its input (a boolean's checkbox: "Checked
means true."), and raw mode what to type on each line ("One item per line. Each item: …").

Saving from the list keeps each item exactly: spaces at the ends, empty items and line breaks within an item all
survive. Raw mode and the field without JavaScript strip each line as the item's own input would (see
[Spaces in typed strings](#spaces-in-typed-strings) for strings). A list with an item containing a line break, or a
list of one empty item, can't be shown one item per line, so raw mode won't open for it, and without JavaScript the
field is read-only and saving keeps the list as it is.

Save is stopped, with a warning, while the item editor holds an unfinished change (a selected item edited but not
updated, or a new value typed but not added): "You have an unsaved change to an item: click Update or Clear." Every
item is checked again on save, so the page's checks are a convenience, not the rule.

The editor sends its requests (checking an item, loading one into the editor, checking raw lines, sorting) to
`<admin>/dynamic_configs/config/list-item/<type key>/`. It's behind the admin's login and
CSRF check, needs add or change permission on configs, takes only POSTs, answers JSON and never saves anything. If it
can't be reached, the page says "Couldn't check the item; try again." and changes nothing.

Only the config admin has the editor. `TypedLineListField` in your own forms keeps the textarea, one item per line.

### Custom types in the list editor

A custom type works in the list editor with no code of its own: the item editor is the type's own input. A custom
widget run entirely by its own script isn't supported there, since the editor fills in the widget's inputs rather than
replacing its HTML; widgets built from ordinary inputs, selects and checkboxes all work.

A custom type's `form` checks each item added or updated in the list. Raw mode, the field without JavaScript and saving
check items with the type's serializer only. So put any rule a value must always follow in the serializer's
`deserialize`, and use `form` for how the value is entered.

A custom type can say how its lists sort with `sort_key` (the dotted path of a function from an item to what to sort
by) or `sort_compare` (the dotted path of a function comparing two items) in its `TYPES` entry. Without either, a list
sorts by its values when their class defines an order, and otherwise has no Sort.

A custom type's `help_text` describes its own input, beside the value and the item editor. Raw mode shows it too,
unless the type's `TYPES` entry has a `raw_help_text`: set one when the input isn't typed as one line (a widget of
several parts, say), to say how an item is typed on a raw-mode line.

## Unregistered types

A setting whose type is no longer registered (removed from `TYPES`, or its entry broken) is listed with its type key
marked "(not registered)". Its page shows the stored text read-only, with the message "This config's type 'color'
isn't registered, so its value can't be edited. Add the type to DYNAMIC_CONFIGS['TYPES']."

## Customizing the admin

`ConfigAdminMixin` (in `dynamic_configs.admin`) holds all the behaviour. `ConfigAdmin` is `ConfigAdminMixin` +
`admin.ModelAdmin`, and is registered automatically unless `DYNAMIC_CONFIGS["REGISTER_ADMIN"]` is `False`.

The mixin sets the fields, their layout and which are read-only itself, since the add page's two steps and the locked
name and type depend on them. So the `fields`, `fieldsets` and `readonly_fields` options are ignored, and the system
check `dynamic_configs.W001` warns when one is set. To change them, override `get_fieldsets()` or
`get_readonly_fields()` and call `super()`.

To use your own subclass, turn the automatic registration off and register it yourself:

```python
# settings.py
DYNAMIC_CONFIGS = {"REGISTER_ADMIN": False}
```

```python
# myapp/admin.py
from django.contrib import admin

from dynamic_configs.admin import ConfigAdmin
from dynamic_configs.models import Config


@admin.register(Config)
class MyConfigAdmin(ConfigAdmin):
    list_per_page = 50
```

## Admin skins

Skins that restyle the stock admin pages, such as jazzmin and grappelli, need nothing: the config admin is stock
pages.

Skins with their own `ModelAdmin` base class, such as unfold, need the config admin built on that base. Combine
`ConfigAdminMixin` with it, and register that instead of `ConfigAdmin`:

```python
# settings.py
DYNAMIC_CONFIGS = {"REGISTER_ADMIN": False}
```

```python
# myapp/admin.py
from django.contrib import admin
from unfold.admin import ModelAdmin

from dynamic_configs.admin import ConfigAdminMixin
from dynamic_configs.models import Config


@admin.register(Config)
class ConfigAdmin(ConfigAdminMixin, ModelAdmin):
    pass
```

With the [simple-history](simple-history.md) integration, include its base class too: the mixin first, simple_history's
`SimpleHistoryAdmin` next, and the skin's base class last:

```python
# myapp/admin.py
from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin
from unfold.admin import ModelAdmin

from dynamic_configs.admin import ConfigAdminMixin
from dynamic_configs.models import Config


@admin.register(Config)
class ConfigAdmin(ConfigAdminMixin, SimpleHistoryAdmin, ModelAdmin):
    pass
```

This also needs `"REGISTER_ADMIN": False`, as above.

## Known limitations

- **Datetimes in the admin keep whole seconds.** Like Django's own admin, the time input shows hours, minutes and
  seconds. A datetime set from code with fractions of a second loses them when its config is saved in the admin, even
  if the datetime itself wasn't changed. Keep such values in code (`dynamic_configs.update`).
