# Development

The source is at [github.com/Tecktron/django-dynamic-configs](https://github.com/Tecktron/django-dynamic-configs).
Issues and pull requests are welcome there.

## Setting up

Set up a virtual environment in the repository and install the development requirements (an editable install of the
package, plus the tools to test, lint and document it):

```
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

The browser tests (`tests/browser`, the admin's scripts in Chromium) need a browser. This installs one inside the
virtual environment, about 280 MB:

```
PLAYWRIGHT_BROWSERS_PATH=0 venv/bin/playwright install --only-shell chromium
```

## Running the tests

Run the tests with coverage. The browser tests run last:

```
venv/bin/coverage run -m pytest
venv/bin/coverage report
```

This is a quick check: the report can be under 100%, because some lines only run with the simple-history extra
installed, and some only without it. 100% branch coverage is required of the combined runs, which tox checks (see
[Coverage](#coverage)).

Check style and formatting with ruff:

```
venv/bin/ruff check .
venv/bin/ruff format --check .
```

## tox

tox runs the suite on every supported pair of Python and Django, plus the other checks:

```
venv/bin/tox
```

Add `-p auto` to run the environments in parallel. Versions not installed locally are skipped.

| Django | Python                         |
|--------|--------------------------------|
| 5.2    | 3.10, 3.11, 3.12, 3.13, 3.14   |
| 6.0    | 3.12, 3.13, 3.14               |
| 6.1    | 3.12, 3.13, 3.14, 3.15         |

Plain `tox` runs these environments:

- **The matrix** (`py310-django52` to `py315-django61`): the suite under coverage, without the browser tests, since
  the scripts don't change with Python or Django.
- **`browser-django52` and `browser-django61`**: the browser tests in headless Chromium, on the oldest and newest
  Django (their admin markup differs), each installing its own Chromium. Without coverage, since the matrix holds the
  Python code to 100%.
- **`extras`**: the suite with django-simple-history installed and its app enabled in the test settings
  (`DYNAMIC_CONFIGS_TEST_EXTRAS=1`).
- **`lint`**: ruff's check and format check.
- **`docs`**: builds this documentation site with warnings as errors.
- **`coverage`**: combines the coverage of every test environment and enforces 100%.

Two more run only when named, and always in CI:

- **`postgres`**: the suite on PostgreSQL (`DYNAMIC_CONFIGS_TEST_POSTGRES=1`). It needs a server: the connection comes
  from libpq's standard `PG*` variables, which tox passes through, and the user must be able to create the test
  database. For example:

  ```
  PGHOST=localhost PGUSER=postgres PGPASSWORD=postgres venv/bin/tox -e postgres
  ```

- **`djangomain`**: the suite on Django's development version, installed from GitHub each time. It may fail while
  Django's main branch changes.

tox refuses to build in a group-writable directory. If your umask is `0002` (common on Linux, where each user has
their own group), tox fails with "package staging path ... can be changed by another account". Set a stricter umask
for that terminal first, and remove any `.tox/` directory created under the old one:

```
umask 022
rm -rf .tox
venv/bin/tox
```

## Coverage

**100% branch coverage is required, of the combined data** of every test environment, not of each one, because some
lines only run with or without the extras. Each environment writes its own data file, and the `coverage` environment
combines them, prints the report with any missing lines, fails under 100%, and writes an HTML report to `htmlcov/`.
Run it after the environments whose data you want combined; plain `tox` does that for you.

Tests run under `coverage run -m pytest`, not pytest-cov: pytest loads this package's pytest plugin before pytest-cov
would start measuring, so the plugin's module-level code would show as uncovered. `# pragma: no cover` isn't used.

## Conventions

- Ruff, with 120 columns: `ruff check .` and `ruff format --check .` must pass.
- Every public module, class, function and method has a docstring, in reST field-list style (`:param:`,
  `:returns:`, `:raises:`); the [API reference](reference.md) is generated from them.
- Tests patch with pytest-mock's `mocker` fixture, not `unittest.mock`.
- Setting values are never logged.

## The documentation

The site is built with Sphinx from Markdown pages (MyST) in `docs/`, with the furo theme; the API reference comes from
the docstrings. Build it with warnings as errors:

```
venv/bin/tox -e docs
```

The pages are written to `docs/_build/html/`. Read the Docs builds `latest` from `main`, and a version for each release
tag.

## CI

GitHub Actions runs `ci.yml` on every push and pull request:

- the `lint` and `docs` jobs;
- the browser tests, one job per browser environment;
- the test suite, one job per tox environment, including `postgres` (with a PostgreSQL service container) and
  `djangomain` (allowed to fail); each saves its coverage data;
- the `coverage` job, after the tests: it combines their data, prints the report with any missing lines, fails under
  100%, and saves the HTML report to download.

There's no coverage service: the 100% rule already blocks any drop, and the job's log names the missing lines.

## Releasing

1. Bump `version` in `pyproject.toml` to the new version, `X.Y.Z`.
2. In `CHANGELOG.md`, rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` (today's date), and start a new, empty
   `## [Unreleased]` above it.
3. Commit both on `main`, then tag the commit and push the tag:

   ```
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

Pushing the tag runs `release.yml`: it checks that the tag matches the package version, builds the sdist and the
wheel, and publishes them to PyPI through trusted publishing, so no token is stored. Read the Docs builds the tag's
version of the docs.

### One-time setup (maintainer)

Outside the repository, once:

- **PyPI:** before the first release, on pypi.org, *Your account → Publishing → Add a pending publisher*: project
  `django-dynamic-configs`, owner `Tecktron`, repository `django-dynamic-configs`, workflow `release.yml`, environment
  `pypi`. The PyPI badges show "not found" until the first release.
- **GitHub:** create the `pypi` environment in the repository settings (optionally requiring approval before a
  release runs).
- **Read the Docs:** sign in at readthedocs.org with GitHub and import `Tecktron/django-dynamic-configs`. Builds then
  run on every push, and the docs badge starts working.

## Design

The design document records what the package does and why, for contributors.

```{toctree}
:maxdepth: 1

design/django-dynamic-configs
```
