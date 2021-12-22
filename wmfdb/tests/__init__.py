"""Tests package for wmfdb."""

# Shameless stolen from https://doc.wikimedia.org/spicerack/master/

import os
import pathlib

TESTS_BASE_PATH = os.path.realpath(os.path.dirname(__file__))


def get_fixture_path(*paths: str) -> pathlib.Path:
    """Return the absolute path of the given fixture.

    Arguments:
        *paths: arbitrary positional arguments used to compose the absolute path to the fixture.

    Returns:
        str: the absolute path of the selected fixture.

    """
    return pathlib.Path(os.path.join(TESTS_BASE_PATH, "fixtures", *paths))
