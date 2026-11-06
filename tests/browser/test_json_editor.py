"""The admin's JSON editor (json_editor.js), in a real browser."""

import pytest
from playwright.sync_api import expect

from dynamic_configs.models import Config

LIGHT_KEY = "rgb(4, 81, 165)"
DARK_KEY = "rgb(156, 220, 254)"


@pytest.fixture
def editor(admin_page):
    """Open the change page of a JSON config, and return the page."""
    Config.objects.create(name="FLAGS", type="json", value='{"beta": true}')
    admin_page.goto("/admin/dynamic_configs/config/FLAGS/change/")
    return admin_page


def textarea(page):
    return page.locator("textarea[name=value]")


def status(page):
    return page.locator(".dynamic-configs-json-status")


def colours(page):
    return page.locator(".dynamic-configs-json-highlight")


def click_format(page):
    page.get_by_role("button", name="Format").click()


def test_format_indents_without_changing_any_value(editor):
    # The reason for the editor: re-encoding through JavaScript numbers would round the first and drop the zero.
    typed = r'{"id":12345678901234567890,"price":1.10,"e":1E+2,"s":"a\"b é","list":[1,[],{}],"t":true,"n":null}'
    textarea(editor).fill(typed)
    click_format(editor)
    expect(textarea(editor)).to_have_value(
        "{\n"
        '  "id": 12345678901234567890,\n'
        '  "price": 1.10,\n'
        '  "e": 1E+2,\n'
        r'  "s": "a\"b é",' + "\n"
        '  "list": [\n'
        "    1,\n"
        "    [],\n"
        "    {}\n"
        "  ],\n"
        '  "t": true,\n'
        '  "n": null\n'
        "}"
    )
    # Undo brings back what was typed.
    textarea(editor).press("ControlOrMeta+z")
    expect(textarea(editor)).to_have_value(typed)


def test_format_leaves_invalid_json_alone_and_points_to_the_error(editor):
    typed = '{"a": 1,\n  "b" 2}'
    textarea(editor).fill(typed)
    click_format(editor)
    expect(textarea(editor)).to_have_value(typed)
    expect(status(editor)).to_have_text('Invalid JSON at line 2, column 7: expected ":".')
    expect(textarea(editor)).to_be_focused()
    assert textarea(editor).evaluate("t => t.selectionStart") == typed.index("2}")


@pytest.mark.parametrize(
    ("typed", "note"),
    [
        ('{"a": [1, 2]}', "Valid JSON."),
        ("[1, 2", "Invalid JSON at line 1, column 6: the JSON ends too soon."),
        ("[1, 2,]", "Invalid JSON at line 1, column 7: expected a value."),
        ('{"a": 1 "b": 2}', 'Invalid JSON at line 1, column 9: expected "," or "}".'),
        ("{'a': 1}", "Invalid JSON at line 1, column 2: unexpected text."),
        (
            '{"a": "tab\there"}',
            "Invalid JSON at line 1, column 7: a string can't contain a tab or other control character.",
        ),
        ('{"a": "\\x"}', "Invalid JSON at line 1, column 7: invalid escape in a string."),
        ('{"a": "open', "Invalid JSON at line 1, column 7: unterminated string."),
        ("[1] 2", "Invalid JSON at line 1, column 5: unexpected text after the end of the JSON."),
        # The server's own message: a setting holds an object or an array.
        ("5", "Enter a JSON object or array."),
        ("", ""),
    ],
)
def test_the_note_says_whether_the_json_is_valid_as_you_type(editor, typed, note):
    textarea(editor).fill(typed)
    expect(status(editor)).to_have_text(note)


def test_enter_keeps_the_indent_and_adds_a_level_after_an_opening_bracket(editor):
    field = textarea(editor)
    field.fill('{\n  "a": [')
    field.press("End")
    field.press("Enter")
    expect(field).to_have_value('{\n  "a": [\n    ')
    field.press_sequentially("1")
    field.press("Enter")
    expect(field).to_have_value('{\n  "a": [\n    1\n    ')


def test_enter_between_brackets_puts_the_closing_one_on_its_own_line(editor):
    field = textarea(editor)
    field.fill("{}")
    field.evaluate("t => t.setSelectionRange(1, 1)")
    field.press("Enter")
    expect(field).to_have_value("{\n  \n}")
    assert field.evaluate("t => t.selectionStart") == 4


def test_a_closing_bracket_alone_on_its_line_steps_back_a_level(editor):
    field = textarea(editor)
    field.fill('{\n  "a": [\n    1\n    ')
    field.press("End")
    field.press_sequentially("]")
    expect(field).to_have_value('{\n  "a": [\n    1\n  ]')
    field.press("Enter")
    field.press_sequentially("}")
    expect(field).to_have_value('{\n  "a": [\n    1\n  ]\n}')
    # One undo takes back the bracket and the outdent together.
    field.press("ControlOrMeta+z")
    expect(field).to_have_value('{\n  "a": [\n    1\n  ]\n  ')


def test_a_tab_indent_steps_back_one_tab(editor):
    field = textarea(editor)
    field.fill("[\n\t[\n\t\t")
    field.press("End")
    field.press_sequentially("]")
    expect(field).to_have_value("[\n\t[\n\t]")


def test_the_closing_bracket_steps_back_whichever_key_types_it(editor):
    # Text arriving without key presses, as from a keyboard layout that types "}" with AltGr.
    field = textarea(editor)
    field.fill("{\n  ")
    field.press("End")
    editor.keyboard.insert_text("}")
    expect(field).to_have_value("{\n}")


@pytest.mark.parametrize(
    ("before", "selected", "after"),
    [
        # Text before it on the line.
        ("[\n  1", None, "[\n  1]"),
        # No indent to take away.
        ("[\n", None, "[\n]"),
        # It replaces a selection.
        ("[\n  x", "x", "[\n  ]"),
    ],
)
def test_a_closing_bracket_otherwise_goes_in_as_typed(editor, before, selected, after):
    field = textarea(editor)
    field.fill(before)
    if selected:
        field.evaluate("(t, s) => t.setSelectionRange(t.value.indexOf(s), t.value.indexOf(s) + s.length)", selected)
    else:
        field.press("ControlOrMeta+End")
    field.press_sequentially("]")
    expect(field).to_have_value(after)


def test_values_are_coloured_by_kind(editor):
    textarea(editor).fill('{"key": "text", "n": -1.5e3, "ok": true, "none": null}')
    copy = colours(editor)
    expect(copy.locator(".dynamic-configs-json-key").first).to_have_text('"key"')
    expect(copy.locator(".dynamic-configs-json-string")).to_have_text('"text"')
    expect(copy.locator(".dynamic-configs-json-number")).to_have_text("-1.5e3")
    expect(copy.locator(".dynamic-configs-json-literal")).to_have_text(["true", "null"])
    expect(copy.locator(".dynamic-configs-json-punctuation").first).to_have_text("{")
    expect(copy.locator(".dynamic-configs-json-key").first).to_have_css("color", LIGHT_KEY)
    # The textarea's own text is hidden, so only the coloured copy shows.
    expect(textarea(editor)).to_have_css("color", "rgba(0, 0, 0, 0)")


def test_the_invalid_token_is_underlined(editor):
    textarea(editor).fill('{"a" 1}')
    expect(colours(editor).locator(".dynamic-configs-json-invalid")).to_have_text("1")


def test_markup_in_a_value_stays_text(admin_page):
    value = '{"html": "<img src=x onerror=document.title=1>"}'
    Config.objects.create(name="SNIPPET", type="json", value=value)
    admin_page.goto("/admin/dynamic_configs/config/SNIPPET/change/")
    copy = colours(admin_page)
    expect(copy.locator(".dynamic-configs-json-string")).to_have_text('"<img src=x onerror=document.title=1>"')
    expect(copy.locator("img")).to_have_count(0)


def lines_up(page):
    """Return whether the coloured copy wraps and scrolls exactly as the textarea does."""
    return page.evaluate(
        """() => {
            const field = document.querySelector("textarea[name=value]");
            const copy = document.querySelector(".dynamic-configs-json-highlight");
            return copy.scrollHeight === field.scrollHeight && copy.scrollTop === field.scrollTop;
        }"""
    )


def test_the_colours_line_up_with_the_text_and_scroll_with_it(editor):
    # Long enough to scroll, with a line long enough to wrap.
    lines = [f'  "key{n}": "{"word " * (40 if n == 3 else 1)}",' for n in range(60)]
    textarea(editor).fill("{\n" + "\n".join(lines) + '\n  "end": 1\n}\n')
    assert lines_up(editor)
    textarea(editor).evaluate("t => { t.scrollTop = t.scrollHeight; }")
    editor.wait_for_function("() => document.querySelector('.dynamic-configs-json-highlight').scrollTop > 0")
    assert lines_up(editor)
    # Resizing the textarea resizes the copy.
    textarea(editor).evaluate("t => { t.style.width = '300px'; }")
    editor.wait_for_function(
        """() => document.querySelector('.dynamic-configs-json-highlight').clientWidth
            === document.querySelector('textarea[name=value]').clientWidth"""
    )
    assert lines_up(editor)


def test_the_colours_turn_off_when_the_copy_cant_line_up(editor):
    # A skin's rule the script can't follow: the copy's text no longer wraps where the textarea's does.
    editor.add_style_tag(content=".dynamic-configs-json-highlight { letter-spacing: 6px !important; }")
    textarea(editor).fill('{"long": "' + "word " * 60 + '"}')
    expect(textarea(editor)).not_to_have_css("color", "rgba(0, 0, 0, 0)")
    expect(colours(editor)).to_be_hidden()
    # The rest of the editor still works.
    expect(status(editor)).to_have_text("Valid JSON.")


def test_without_the_stylesheet_the_field_stays_plain_but_still_checks(admin_page):
    admin_page.route("**/dynamic_configs/admin.css", lambda route: route.fulfill(content_type="text/css", body=""))
    Config.objects.create(name="FLAGS", type="json", value='{"beta": true}')
    admin_page.goto("/admin/dynamic_configs/config/FLAGS/change/")
    expect(colours(admin_page)).to_have_count(0)
    expect(textarea(admin_page)).not_to_have_css("color", "rgba(0, 0, 0, 0)")
    textarea(admin_page).fill('{"a":1}')
    click_format(admin_page)
    expect(textarea(admin_page)).to_have_value('{\n  "a": 1\n}')
    expect(status(admin_page)).to_have_text("Valid JSON.")


def test_dark_colours_follow_the_browser_and_the_admins_theme_toggle(editor):
    key = colours(editor).locator(".dynamic-configs-json-key").first
    editor.emulate_media(color_scheme="dark")
    expect(key).to_have_css("color", DARK_KEY)
    # Django's theme toggle sets data-theme on the page; light wins over the browser's preference.
    editor.evaluate("() => { document.documentElement.dataset.theme = 'light'; }")
    expect(key).to_have_css("color", LIGHT_KEY)
    editor.evaluate("() => { document.documentElement.dataset.theme = 'dark'; }")
    editor.emulate_media(color_scheme="light")
    expect(key).to_have_css("color", DARK_KEY)


def test_a_projects_own_colours_win(editor):
    editor.add_style_tag(content=":root { --dynamic-configs-json-key: rgb(1, 2, 3); }")
    expect(colours(editor).locator(".dynamic-configs-json-key").first).to_have_css("color", "rgb(1, 2, 3)")


def test_the_add_page_has_the_editor(admin_page):
    admin_page.goto("/admin/dynamic_configs/config/add/?type=json")
    textarea(admin_page).fill('{"a":1}')
    click_format(admin_page)
    expect(textarea(admin_page)).to_have_value('{\n  "a": 1\n}')


def test_deep_nesting_is_checked_without_crashing(editor):
    textarea(editor).fill("[" * 5000 + "]" * 5000)
    expect(status(editor)).to_have_text("Valid JSON.")
