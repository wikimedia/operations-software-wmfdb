from typing import Union

import pytest

import wmfdb.log as log
from wmfdb.exceptions import WmfdbValueError


@pytest.mark.parametrize(
    "level",
    [
        "INFO",
        "DEBUG",
        50,  # logging.CRITICAL
    ],
)
def test_check_level_ok(level: Union[str, int]) -> None:
    log._check_level(level)


@pytest.mark.parametrize(
    "level",
    [
        "info",
        99,
    ],
)
def test_check_level_fail(level: Union[str, int]) -> None:
    with pytest.raises(WmfdbValueError):
        log._check_level("info")
