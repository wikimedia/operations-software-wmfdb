from pkg_resources import DistributionNotFound, get_distribution

try:
    # Must be the same used as 'name' in setup.py
    __version__ = get_distribution("wmfdb").version
    """:py:class:`str`: the version of the current wmfdb module."""
except DistributionNotFound:  # pragma: no cover - this should never happen during tests
    pass  # package is not installed
