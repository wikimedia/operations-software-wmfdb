"""Exceptions module."""


class WmfdbError(Exception):
    """Parent exception class for all wmfdb exceptions."""


class WmfdbValueError(WmfdbError):
    """Generic wmfdb value error."""


class WmfdbIOError(WmfdbError):
    """Generic wmfdb IO error."""
