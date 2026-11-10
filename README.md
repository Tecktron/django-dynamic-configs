# django-dynamic-configs

[![CI](https://github.com/Tecktron/django-dynamic-configs/actions/workflows/ci.yml/badge.svg)](https://github.com/Tecktron/django-dynamic-configs/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/Tecktron/django-dynamic-configs/actions/workflows/ci.yml)
[![Documentation](https://readthedocs.org/projects/django-dynamic-configs/badge/?version=latest)](https://django-dynamic-configs.readthedocs.io/)
[![PyPI version](https://img.shields.io/pypi/v/django-dynamic-configs)](https://pypi.org/project/django-dynamic-configs/)
[![Python versions](https://img.shields.io/pypi/pyversions/django-dynamic-configs)](https://pypi.org/project/django-dynamic-configs/)
[![Django versions](https://img.shields.io/pypi/djversions/django-dynamic-configs)](https://pypi.org/project/django-dynamic-configs/)
[![License](https://img.shields.io/pypi/l/django-dynamic-configs)](https://github.com/Tecktron/django-dynamic-configs/blob/main/LICENSE)

Typed runtime settings for Django that admins can add and edit in the Django admin, read from code through a small,
cached API.

**Status:** alpha, under active development.

## Installation

```
pip install django-dynamic-configs
```

Add it to `INSTALLED_APPS`, then create its table:

```python
INSTALLED_APPS = [
    # ...
    "django.contrib.admin",
    "dynamic_configs",
]
```

```
python manage.py migrate
```

To record every change with django-simple-history, install the extra:

```
pip install "django-dynamic-configs[simple-history]"
```

## Quick start

```python
import dynamic_configs

# Create the setting the first time; later calls return what is stored.
page_size, created = dynamic_configs.get_or_create("PAGE_SIZE", "int", 20, description="Items per list page.")

page_size = dynamic_configs.get("PAGE_SIZE", 20)  # a cached read, with a default
dynamic_configs.update("PAGE_SIZE", 50)  # change it from code
```

Admins can then change `PAGE_SIZE` under **Configs** in the Django admin, and the code above reads their value.

## Documentation

The full documentation is at https://django-dynamic-configs.readthedocs.io/.

## License

MIT. See [LICENSE](https://github.com/Tecktron/django-dynamic-configs/blob/main/LICENSE).
