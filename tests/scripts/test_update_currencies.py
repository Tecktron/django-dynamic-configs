import importlib.util
import itertools
import string
from pathlib import Path

import pytest

from dynamic_configs.types import iso4217

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "update_currencies.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("update_currencies", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(country, name, code=None, fund=False):
    """One CcyNtry element; no code means a country with no currency."""
    fund_attribute = ' IsFund="true"' if fund else ""
    code_element = f"<Ccy>{code}</Ccy>" if code else ""
    return f"<CcyNtry><CtryNm>{country}</CtryNm><CcyNm{fund_attribute}>{name}</CcyNm>{code_element}</CcyNtry>"


def list_one(entries, published="2026-09-17"):
    """A List One document as bytes."""
    attribute = f' Pblshd="{published}"' if published else ""
    return f"<ISO_4217{attribute}><CcyTbl>{''.join(entries)}</CcyTbl></ISO_4217>".encode()


def synthetic(count, name="Money"):
    """``count`` normal entries with distinct codes AAA, AAB, ..."""
    codes = ("".join(letters) for letters in itertools.product(string.ascii_uppercase, repeat=3))
    return {code: f"{name} {code}" for code in itertools.islice(codes, count)}


def synthetic_xml(currencies, published="2026-09-17"):
    return list_one([entry(f"COUNTRY {code}", name, code) for code, name in currencies.items()], published)


SMALL = list_one(
    [
        entry("CANADA", "Canadian Dollar", "CAD"),
        entry("FRANCE", " Euro ", "EUR"),
        entry("GERMANY", "Euro", "EUR"),
        entry("BOLIVIA", "Mvdol", "BOV", fund=True),
        entry("ZZ01_Gold", "Gold", "XAU"),
        entry("ANTARCTICA", "No universal currency"),
    ]
)


def test_parse_keeps_normal_and_duplicate_codes_only(script):
    published, currencies = script.parse(SMALL, minimum=1)
    assert published == "2026-09-17"
    assert currencies == {"CAD": "Canadian Dollar", "EUR": "Euro"}


def test_parse_sorts_by_code(script):
    xml = list_one([entry("B", "Bee", "BBB"), entry("A", "Aye", "AAA")])
    assert list(script.parse(xml, minimum=1)[1]) == ["AAA", "BBB"]


@pytest.mark.parametrize(
    "xml",
    [
        pytest.param(b"<!DOCTYPE html><html><body><p>Sorry</p></body></html>", id="html"),
        pytest.param(b"<html><body><p>Sorry</p></body></html>", id="well-formed html"),
        pytest.param(SMALL[:60], id="truncated"),
        pytest.param(list_one([entry("CANADA", "Canadian Dollar", "CAD")], published=""), id="no date"),
        pytest.param(list_one([entry("CANADA", "Canadian Dollar", "ca1")]), id="bad code"),
        pytest.param(list_one([entry("CANADA", "", "CAD")]), id="no name"),
        pytest.param(
            list_one([entry("CANADA", "Canadian Dollar", "CAD"), entry("OTHER", "Other Dollar", "CAD")]),
            id="two names",
        ),
    ],
)
def test_parse_refuses_bad_input(script, xml):
    with pytest.raises(ValueError):
        script.parse(xml, minimum=1)


def test_parse_enforces_the_floor_of_100_by_default(script):
    with pytest.raises(ValueError, match="99"):
        script.parse(synthetic_xml(synthetic(99)))
    assert len(script.parse(synthetic_xml(synthetic(100)))[1]) == 100


def test_render_is_what_is_shipped(script):
    assert script.render(iso4217.PUBLISHED, iso4217.CURRENCIES) == Path(iso4217.__file__).read_text()


def test_main_writes_then_reports_unchanged(script, tmp_path, capsys):
    source = tmp_path / "list-one.xml"
    source.write_bytes(synthetic_xml(synthetic(120)))
    out = tmp_path / "iso4217.py"

    assert script.main(["--from", str(source), "--out", str(out)]) == 0
    assert "added: " in capsys.readouterr().out
    assert out.read_text() == script.render("2026-09-17", synthetic(120))

    text, mtime = out.read_text(), out.stat().st_mtime_ns
    assert script.main(["--from", str(source), "--out", str(out)]) == 0
    assert capsys.readouterr().out.strip() == "unchanged"
    assert (out.read_text(), out.stat().st_mtime_ns) == (text, mtime)


def test_main_ignores_a_new_publication_date_alone(script, tmp_path, capsys):
    out = tmp_path / "iso4217.py"
    source = tmp_path / "list-one.xml"
    source.write_bytes(synthetic_xml(synthetic(120)))
    script.main(["--from", str(source), "--out", str(out)])
    capsys.readouterr()
    text = out.read_text()

    source.write_bytes(synthetic_xml(synthetic(120), published="2026-10-01"))
    script.main(["--from", str(source), "--out", str(out)])

    assert capsys.readouterr().out.strip() == "unchanged"
    assert out.read_text() == text


def test_main_reports_added_removed_and_renamed(script, tmp_path, capsys):
    out = tmp_path / "iso4217.py"
    out.write_text(script.render("2026-09-17", synthetic(120)))
    changed = synthetic(121)
    del changed["AAB"]
    changed["AAC"] = "Renamed Money"
    source = tmp_path / "list-one.xml"
    source.write_bytes(synthetic_xml(changed, published="2026-10-01"))
    summary = tmp_path / "summary.md"

    assert script.main(["--from", str(source), "--out", str(out), "--summary", str(summary)]) == 0

    printed = capsys.readouterr().out
    assert printed == summary.read_text()
    assert "added: " in printed
    assert "removed: " in printed
    assert "renamed: AAC (Money AAC -> Renamed Money)" in printed
    assert 'PUBLISHED = "2026-10-01"' in out.read_text()
    assert out.read_text() == script.render("2026-10-01", changed)


def test_main_with_from_never_fetches(script, tmp_path, mocker):
    urlopen = mocker.patch.object(script, "urlopen", side_effect=AssertionError("fetched"))
    source = tmp_path / "list-one.xml"
    source.write_bytes(synthetic_xml(synthetic(120)))

    script.main(["--from", str(source), "--out", str(tmp_path / "iso4217.py")])

    urlopen.assert_not_called()


def test_main_fetches_the_source_when_not_given_a_file(script, tmp_path, mocker):
    response = mocker.MagicMock()
    response.__enter__.return_value.read.return_value = synthetic_xml(synthetic(120))
    urlopen = mocker.patch.object(script, "urlopen", return_value=response)
    out = tmp_path / "iso4217.py"

    script.main(["--out", str(out)])

    urlopen.assert_called_once_with(script.SOURCE, timeout=60)
    assert out.exists()
