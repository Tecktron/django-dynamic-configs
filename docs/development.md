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

The browser tests (`tests/browser`, the admin's scripts in Chromium, Firefox and WebKit) need a browser. They use
Chromium unless told otherwise; this installs it inside the virtual environment, about 280 MB:

```
PLAYWRIGHT_BROWSERS_PATH=0 venv/bin/playwright install --only-shell chromium
```

To run them in Firefox or WebKit as well, install those the same way (`install firefox`, `install webkit`) and pass
`--browser firefox` or `--browser webkit` to pytest. Either may need system libraries the machine lacks: Playwright
names them when it can't start the browser, and `playwright install-deps` installs them (with `sudo`). Without them,
that browser's tests fail, and so do its tox environments: [tox](#tox) shows how to skip WebKit's, or run them in
Docker.

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
- **`browser-chromium-django52` to `browser-webkit-django61`**: the browser tests in each headless browser (Chromium,
  Firefox, WebKit) on the oldest and newest Django (their admin markup differs), one engine per environment, each
  installing only its own browser. Without coverage, since the matrix holds the Python code to 100%.

  Firefox and WebKit need the system libraries described in [Setting up](#setting-up); without them, their
  environments fail. To leave WebKit out, skip its environments (tox matches the pattern from the start of each name):

  ```
  venv/bin/tox --skip-env browser-webkit
  ```

  Or run them in Playwright's Docker image, which has the libraries. This copies the working tree into the container
  (nothing is mounted, so the container's `.tox` stays apart from yours), installs tox there as the image's non-root
  user, and points the environments at the image's Python 3.12, since they ask for 3.14:

  ```
  git ls-files -co --exclude-standard | tar -cf - -T - | docker run --rm -i --ipc=host --user pwuser \
      mcr.microsoft.com/playwright/python:v1.64.1-noble bash -c '
          set -e
          umask 022
          mkdir ~/src
          tar -xf - -C ~/src
          cd ~/src
          pip install --user --quiet --no-warn-script-location tox
          python3 -m tox -e browser-webkit-django52,browser-webkit-django61 \
              -x testenv:browser-webkit-django52.base_python=python3 \
              -x testenv:browser-webkit-django61.base_python=python3'
  ```

  The image provides the libraries of its Playwright version; if tox installs a newer Playwright whose browsers need
  more, use the image tag of that version.
- **`extras`**: the suite with django-simple-history installed and its app enabled in the test settings
  (`DYNAMIC_CONFIGS_TEST_EXTRAS=1`).
- **`lint`**: ruff's check and format check.
- **`docs`**: builds this documentation site with warnings as errors.
- **`coverage`**: combines the coverage of every test environment and enforces 100%.

Five more run only when named, and always in CI:

- **`postgres`**: the suite on PostgreSQL (`DYNAMIC_CONFIGS_TEST_POSTGRES=1`). It needs a server: the connection comes
  from libpq's standard `PG*` variables, which tox passes through, and the user must be able to create the test
  database. For example:

  ```
  PGHOST=localhost PGUSER=postgres PGPASSWORD=postgres venv/bin/tox -e postgres
  ```

- **`redis`, `redis-json` and `memcached`**: the suite against a real cache server instead of LocMemCache
  (`DYNAMIC_CONFIGS_TEST_CACHE`): Django's Redis backend; django-redis with its JSON serializer, on Django 6.0 (the
  newest django-redis supports); and Django's pymemcache backend. The server's address comes from
  `DYNAMIC_CONFIGS_TEST_REDIS_URL` or `DYNAMIC_CONFIGS_TEST_MEMCACHED`, which tox passes through. There is no default
  address.

  **The tests empty the server.** The suite clears the cache around every test: `FLUSHDB` on the Redis database, and
  the whole Memcached server. Never point them at a server holding anything you want to keep. As a guard, a run stops
  before the first test, deleting nothing, if another run is using the same address (a lock file in the system's
  temporary directory), or the server already holds data or can't be reached. Give each environment its own server, or
  its own Redis database: two runs sharing one would empty each other's cache. On Windows there's no lock, so runs
  there aren't protected against each other. For example, with throwaway servers in Docker, on uncommon ports bound to
  `127.0.0.1`:

  ```
  docker run --rm -d --name dc-test-redis -p 127.0.0.1:16379:6379 redis:8
  docker run --rm -d --name dc-test-memcached -p 127.0.0.1:21211:11211 memcached:1.6
  DYNAMIC_CONFIGS_TEST_REDIS_URL=redis://127.0.0.1:16379/0 venv/bin/tox -e redis
  DYNAMIC_CONFIGS_TEST_REDIS_URL=redis://127.0.0.1:16379/1 venv/bin/tox -e redis-json
  DYNAMIC_CONFIGS_TEST_MEMCACHED=127.0.0.1:21211 venv/bin/tox -e memcached
  docker stop dc-test-redis dc-test-memcached
  ```

  These environments use a file-backed SQLite test database, in the system's temporary directory, instead of the
  in-memory one, so a second process can open it.

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

The site is built with Sphinx from Markdown pages (MyST) in `docs/`, with the Read the Docs theme (sphinx-rtd-theme);
the API reference comes from the docstrings. Build it with warnings as errors:

```
venv/bin/tox -e docs
```

The pages are written to `docs/_build/html/`. Read the Docs builds `latest` from `main`, and a version for each release
tag.

## CI

GitHub Actions runs `ci.yml` on pushes to `main` and on pull requests:

- the `lint` and `docs` jobs;
- the `package` job: it builds the sdist and the wheel, as a release does, and checks them with
  `twine check --strict`, so a packaging problem shows up before a tag is pushed;
- the browser tests, one job per browser environment;
- the test suite, one job per tox environment, including `postgres` (with a PostgreSQL service container), `redis`,
  `redis-json` and `memcached` (each job with a Redis or Memcached service container of its own) and `djangomain`
  (allowed to fail); each saves its coverage data;
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
version of the docs, once the automation rule below is in place.

### Dry run

To try the release pipeline without releasing, start `release.yml` by hand from `main`:

```
gh workflow run release.yml --ref main
```

A manual run skips the tag check, rewrites `version` in the runner's copy of `pyproject.toml` to
`X.Y.Z.devN` (`N` is the run number; nothing is committed), and builds and checks the distributions. Started from
`main`, it publishes them to TestPyPI only, through the `testpypi` environment; started from any other branch, it
publishes nothing. A tag never reaches TestPyPI, and a manual run never reaches PyPI. A `.devN` version is a pre-release, so a dry run can repeat without using up `X.Y.Z` on either index. GitHub
offers a manual run only for a workflow on the default branch, so the dry run works once the change is merged to `main`.

### One-time setup (maintainer)

Outside the repository, once:

- **PyPI:** before the first release, on pypi.org, *Your account → Publishing → Add a pending publisher*: project
  `django-dynamic-configs`, owner `Tecktron`, repository `django-dynamic-configs`, workflow `release.yml`, environment
  `pypi`. The PyPI badges show "not found" until the first release.
- **TestPyPI:** for the dry run, create an account on test.pypi.org (a separate site from PyPI) with 2FA, then *Your
  account → Publishing → Add a pending publisher*: project `django-dynamic-configs`, owner `Tecktron`, repository
  `django-dynamic-configs`, workflow `release.yml`, environment `testpypi`.
- **GitHub:** create the `pypi` environment in the repository settings. Under *Deployment branches and tags*, choose
  *Selected branches and tags* and add a rule of ref type *Tag* for `v*`: a release runs from a tag, and *Protected
  branches only* lets only protected branches deploy, so it would block the release. Optionally, add required
  reviewers, so each release waits for approval.
- **GitHub (dry run):** create the `testpypi` environment. Under *Deployment branches and tags*, choose *Selected
  branches and tags* and add a rule of ref type *Branch* for `main`: a dry run starts from `main`.
- **Read the Docs:** sign in at readthedocs.org with GitHub and import `Tecktron/django-dynamic-configs`. Its GitHub
  integration starts a build on every push, and the docs badge starts working; if a push to `main` doesn't start a
  build, check the integration in the project's *Admin → Integrations*. Then, in *Admin → Automation Rules*, add a
  rule that activates new versions for tags matching SemVer (or `v*`); without it, Read the Docs doesn't build
  release tags.

## Design

The design document records what the package does and why, for contributors.

```{toctree}
:maxdepth: 1

design/django-dynamic-configs
```
