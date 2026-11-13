"""Sphinx configuration for the django-dynamic-configs documentation."""

import importlib.metadata

import django
from django.conf import settings

# autodoc imports the package's modules, and the models and the admin need Django set up first. Django is configured
# here, not from the test suite's settings, so the docs build wherever only the package is installed (Read the Docs).
# Importing touches no database, so none is configured.
settings.configure(
    INSTALLED_APPS=[
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "dynamic_configs",
    ],
    USE_TZ=True,
)
django.setup()

project = "django-dynamic-configs"
author = "Tecktron"
copyright = "2026, Tecktron"
release = importlib.metadata.version("django-dynamic-configs")

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx_autodoc_typehints",
]

# design/plans holds implementation plans, kept locally and ignored by git; they're never published.
exclude_patterns = ["_build", "design/plans"]

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_css_files = ["custom.css"]

myst_heading_anchors = 3

autodoc_member_order = "bysource"
# Show defaults as written in the source: get()'s default is a sentinel, which would otherwise render as
# <object object>.
autodoc_preserve_defaults = True
