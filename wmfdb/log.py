"""Log module."""
import logging
from typing import Union

from wmfdb.exceptions import WmfdbValueError

root_logger = logging.getLogger()


def setup(level: Union[str, int] = logging.INFO) -> None:
    """Set up logging.

    Arguments:
        level (str, int): Logging level to set.

    Raises:
        wmfdb.exceptions.WmfdbValueError: if level is not valid.
    """
    _check_level(level)
    formatter = logging.Formatter(fmt="%(asctime)s %(process)d [%(levelname)s] %(message)s")
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)
    root_logger.addHandler(stderr_handler)
    root_logger.setLevel(level)


def _check_level(level: Union[str, int]) -> None:
    """Validate logging level.

    Arguments:
        level (str, int): Logging level to check.

    Raises:
        wmfdb.exceptions.WmfdbValueError: if level is not valid.
    """
    # getLevelName has weird semantics, but there doesn't seem to be any other supported
    # way to do this.
    # https://docs.python.org/3/library/logging.html#logging.getLevelName
    ret: Union[str, int] = logging.getLevelName(level)
    if isinstance(ret, int):
        # Any integer value means 'level' contained a string representation of a known
        # logging level.
        return
    assert isinstance(ret, str)
    if ret.startswith("Level "):
        # If getLevelName is given an unknown level, it returns a string of the form
        # "Level %s"
        raise WmfdbValueError(f"Invalid logging level '{level}'")
