"""A custom type module that fails while it's imported, with an error other than ImportError."""

raise ZeroDivisionError("this module is broken")
