from importlib import metadata

try:
    # Must be the same used as 'name' in setup.py
    __version__ = metadata.version("wmfdb")
    """:py:class:`str`: the version of the current wmfdb module."""
except metadata.PackageNotFoundError:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed
