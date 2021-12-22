"""Section module."""

import csv
import os
from typing import Dict, List

from wmfdb.exceptions import WmfdbIOError, WmfdbValueError

DEFAULT_CFG_PATH = "/etc/wmfmariadbpy/section_ports.csv"
TEST_DATA_ENV = "WMFDB_SECTION_MAP_TEST_DATA"
# Use a string literal with splitlines(keepends=True) to keep the same format as a
# file read from disk.
TEST_DATA = """\
f0, 10110
f1, 10111
f2, 10112
f3, 10113
alpha, 10320
""".splitlines(
    keepends=True
)
DEFAULT_SECTION = "default"
DEFAULT_PORT = 3306
DEFAULT_PROM_PORT = 9104


class SectionMap:
    """Class to map between section names and port numbers."""

    def __init__(self, cfg_path: str = "", _load_cfg: bool = True) -> None:
        """Initialize the instance.

        Args:
            cfg_path (str, optional): the config file to load. If not set, DEFAULT_CFG_PATH
                is used.. Defaults to "".
            _load_cfg (bool, optional): If True, loads config on instance initialisation.
                Used to by-pass cfg loading during unit testing. Defaults to True.
        """

        self._section: Dict[str, int] = {}
        self._port: Dict[int, str] = {}
        if _load_cfg:
            cfg = self._get_cfg_file(cfg_path)
            self._parse_cfg(cfg)

    def _get_cfg_file(self, path: str) -> List[str]:
        """Get the contents of the config file.

        If path is "", and $WMFDB_SECTION_MAP_TEST_DATA is set in
        the environment, test data is returned instead.

        Args:
            path (str): the config file to load.

        Raises:
            WmfdbIOError: if unable to open the file.

        Returns:
            List[str]: lines of the config.
        """
        if not path:
            if TEST_DATA_ENV in os.environ:
                return TEST_DATA
            path = DEFAULT_CFG_PATH
        try:
            with open(path, mode="r", newline="") as f:
                return f.readlines()
        except (FileNotFoundError, PermissionError) as e:
            raise WmfdbIOError(e) from None

    def _parse_cfg(self, cfg: List[str]) -> None:
        """Parse the config.

        Args:
            cfg (List[str]): lines of the config.

        Raises:
            WmfdbValueError: if section name is empty or blank.
            WmfdbValueError: if port is not an int.
        """
        reader = csv.reader(iter(cfg))
        for (section, port_str) in reader:
            line_num = reader.line_num - 1
            if not section.strip():
                raise WmfdbValueError(f"Line {line_num} of config has a blank section entry")
            try:
                port = int(port_str)
            except ValueError:
                raise WmfdbValueError(
                    f"Line {line_num} of config has a invalid port number: {port_str}"
                )
            self._section[section] = port
            self._port[port] = section

    def names(self) -> List[str]:
        """Get section names.

        Returns:
            List[str]: all known section names.
        """
        return sorted(self._section.keys())

    def ports(self) -> List[int]:
        """Get section ports.

        Returns:
            List[int]: all known section ports.
        """
        return sorted(self._port.keys())

    def by_name(self, name: str) -> "Section":
        """Retrieve a Section object for a given section name.

        Args:
            name (str): Either a section name, or DEFAULT_SECTION

        Raises:
            WmfdbValueError: if section name is unknown.

        Returns:
            Section: object for the section.
        """
        if name == DEFAULT_SECTION:
            return Section(name=DEFAULT_SECTION, port=DEFAULT_PORT)
        try:
            port = self._section[name]
        except KeyError:
            raise WmfdbValueError(f"Invalid section name {name}")
        return Section(name=name, port=port)

    def by_port(self, port: int) -> "Section":
        """Retrieve a Section object for given section port.

        Args:
            port (int): Either a section port, or DEFAULT_PORT (for the default section).

        Raises:
            WmfdbValueError: if no section has the given port.

        Returns:
            Section: object for the section.
        """
        if port == DEFAULT_PORT:
            return Section(name=DEFAULT_SECTION, port=DEFAULT_PORT)
        try:
            name = self._port[port]
        except KeyError:
            raise WmfdbValueError(f"Invalid port number {port}")
        return Section(name=name, port=port)


class Section:
    """Class to represent a section."""

    def __init__(self, *, name: str, port: int):
        """Initialize the instance.

        Args:
            name (str): Name of section, or 'default'.
            port (int): Port of section, or 3306.

        Raises:
            WmfdbValueError: if name is empty or blank.
            WmfdbValueError: if port is 0 or negative.
            WmfdbValueError: if name is 'default', and port is not 3306.
            WmfdbValueError: if port is 3306, and name is not 'default'.
        """
        if not name.strip():
            raise WmfdbValueError(f'Empty/blank section name "{name}"')
        if port <= 0:
            raise WmfdbValueError(f"Invalid port number, {port}")
        if name == DEFAULT_SECTION and port != DEFAULT_PORT:
            raise WmfdbValueError(
                f"Section {name} must have default port ({DEFAULT_PORT}), not {port}"
            )
        if port == DEFAULT_PORT and name != DEFAULT_SECTION:
            raise WmfdbValueError(
                f"Port {port} must have {DEFAULT_SECTION} section name, not {name}"
            )
        self.name = name
        self.port = port

    def socket_path(self) -> str:
        """Return the unix socket path.

        Returns:
            str: path to the unix socket for mysqld. E.g. /run/mysqld/mysqld.s8.sock
        """
        if self.name == DEFAULT_SECTION:
            return "/run/mysqld/mysqld.sock"
        return f"/run/mysqld/mysqld.{self.name}.sock"

    def datadir(self) -> str:
        """Return the mysql data directory.

        Returns:
            str: path to the data directory. E.g. /srv/sqldata.s8
        """
        if self.name == DEFAULT_SECTION:
            return "/srv/sqldata"
        return f"/srv/sqldata.{self.name}"

    def prom_port(self) -> int:
        """Return the prometheus exporter port.

        Returns:
            int: Prometheus exporter port.
        """
        if self.name == DEFAULT_SECTION:
            return DEFAULT_PROM_PORT
        return self.port + 10000
