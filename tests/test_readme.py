"""The README is PyPI's project page, so its links and badges are checked."""

import re
from pathlib import Path

README = (Path(__file__).parent.parent / "README.md").read_text()
LINKS = re.findall(r"\]\(([^)]+)\)", README)


def test_every_link_is_absolute():
    # The README is also PyPI's project page, where relative links break.
    assert LINKS
    assert [link for link in LINKS if not link.startswith("https://")] == []


def test_the_seven_badges_in_order():
    badges = re.findall(r"!\[[^\]]*\]\((https://[^)]+)\)", README)
    assert badges == [
        "https://github.com/Tecktron/django-dynamic-configs/actions/workflows/ci.yml/badge.svg",
        "https://img.shields.io/badge/coverage-100%25-brightgreen",
        "https://readthedocs.org/projects/django-dynamic-configs/badge/?version=latest",
        "https://img.shields.io/pypi/v/django-dynamic-configs",
        "https://img.shields.io/pypi/pyversions/django-dynamic-configs",
        "https://img.shields.io/pypi/djversions/django-dynamic-configs",
        "https://img.shields.io/pypi/l/django-dynamic-configs",
    ]


def test_it_points_to_the_documentation():
    assert "https://django-dynamic-configs.readthedocs.io/" in README
