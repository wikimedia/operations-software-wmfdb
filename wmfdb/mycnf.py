"""mycnf module."""

import configparser
import os
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from wmfdb.exceptions import WmfdbIOError, WmfdbValueError

DEF_CFG_LIST = (
    "/etc/my.cnf",
    "/etc/mysql/my.cnf",
    "~/.my.cnf",
)
DEF_SECTION_LIST = ("client",)


class Cnf:
    """Class to support reading from mysql .cnf files.

    my.cnf files are ini-like, with some non-standard differences:
    - Dashes and underscores in key-names are interchangable. I.e.
      'max-allowed-packet' is treated the same as 'max_allowed_packet',
      and 'max-allowed_packet'.
    - Single- or double-quotes around values are automatically stripped.
    - Values can have in-line comments that start with #, provided the
      value isn't quoted. E.g. `port = 3306 # default port` will be read
      as `3306`, but `port = "3306 # default port"` will be read as
      `3306 # default port`.

    Mysql will load .cnf files in a given order, with later values
    overriding earlier ones.

    Mysql can also be told to look at multiple sections for values.
    The first match wins. This class supports this using the
    `section_order` parameter to the constructor.
    """

    def __init__(
        self,
        section_order: Iterable[str] = DEF_SECTION_LIST,
        **kwargs: Any,
    ) -> None:
        """Initialize the instance.

        All undefined keyword args are passed directly to
        configparser.ConfigParser, with some options being hard-coded.

        Args:
            section_order (Iterable[str], optional): Order in which to
                search sections when looking for a key. First match wins.
                Defaults to DEF_SECTION_LIST.
        """
        self._section_order = section_order
        # Force these options.
        kwargs["interpolation"] = None
        kwargs["allow_no_value"] = True
        kwargs["default_section"] = None
        self._parser = configparser.ConfigParser(**kwargs)
        # Workaround for https://github.com/python/mypy/issues/2427
        setattr(self._parser, "optionxform", self._normalize_keys)

    @staticmethod
    def _normalize_keys(key: str) -> str:
        """Normalize my.cnf keys.

        Mysql/mariadb will allow options to appear as a-b-c or a_b_c,
        or even a_b-c :(

        Args:
            key (str): Key to normalize.

        Returns:
            str: Normalized key.
        """
        return key.replace("-", "_")

    def load_cfgs(self, paths: Iterable[str] = DEF_CFG_LIST) -> None:
        """Load my.cnf files in order.

        Any paths that don't exist or aren't readable are skipped.

        Args:
            paths (Iterable[str], optional): Paths to load. Defaults to
                DEF_CFG_LIST.
        """
        paths = self._find_cfgs(paths)
        for path in paths:
            self._load_cfg(path)

    def _load_cfg(self, path: str) -> None:
        """Load a my.cnf file.

        Args:
            path (str): File to load.

        Raises:
            WmfdbValueError: if parsing the file fails.
            WmfdbIOError: if unable to open the file.
        """
        try:
            with open(path, "r", encoding="utf8") as f:
                try:
                    self._parser.read_file(f, source=path)
                except configparser.Error as e:
                    raise WmfdbValueError(e) from None
        except (FileNotFoundError, PermissionError) as e:
            raise WmfdbIOError(e) from None

    def _find_cfgs(self, paths: Iterable[str]) -> List[str]:
        """Filter out missing and unreadable files.

        ~ and ~user are expanded as part of this.

        Args:
            paths (Iterable[str]): Files to look for.

        Returns:
            List[str]: Readable paths in expanded form.
        """
        ret: List[str] = []
        for path in paths:
            path = os.path.expanduser(path)
            if os.path.isfile(path) and os.access(path, os.R_OK):
                ret.append(path)
        return ret

    def _get(self, key: str) -> Tuple[str, str, bool]:
        """Search sections for the key, returning the value if found.

        Args:
            key (str): Key to load.

        Returns:
            Tuple[str, str, bool]: section name, key value, key found.
        """
        for sec in self._section_order:
            if self._parser.has_option(sec, key):
                # Remove in-line comments, and wrapping quotes
                return sec, self._cleanup_value(self._parser.get(sec, key)), True
        return "", "", False

    def _cleanup_value(self, val: Optional[str]) -> str:
        """Clean value to return a useful string version.

        Quotes and in-line comments are removed.

        Args:
            val (Optional[str]): value to clean.

        Returns:
            str: cleaned value.
        """
        if val is None:
            val = ""
        elif len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            # Check for "value" or 'value', and strip matching quotes.
            val = val[1:-1]
        elif "#" in val:
            # Handle in-line comments when value is not quoted.
            val = val[: val.index("#")].rstrip()
        return val

    def get_str(self, key: str) -> Tuple[str, bool]:
        """Get string value of key.

        Args:
            key (str): key to find.

        Returns:
            Tuple[str, bool]: value, key found.
        """
        _, val, ok = self._get(key)
        return val, ok

    def get_int(self, key: str) -> Tuple[int, bool]:
        """Get int value of key.

        Args:
            key (str): key to find.

        Raises:
            WmfdbValueError: if value is not integer.

        Returns:
            Tuple[int, bool]: vaule, key found.
        """
        sec, val, ok = self._get(key)
        if not ok:
            return 0, False
        try:
            return int(val), True
        except ValueError:
            raise WmfdbValueError(f'Mysql config value [{sec}]{key} has non-integer value: "{val}"')

    def get_float(self, key: str) -> Tuple[float, bool]:
        """Get float value of key.

        Args:
            key (str): key to find.

        Raises:
            WmfdbValueError: if value is not float.

        Returns:
            Tuple[float, bool]: value, key found.
        """
        sec, val, ok = self._get(key)
        if not ok:
            return 0.0, False
        try:
            return float(val), True
        except ValueError:
            raise WmfdbValueError(f'Mysql config value [{sec}]{key} has non-float value: "{val}"')

    def get_bool(self, key: str) -> Tuple[bool, bool]:
        """Get bool value of key.

        Args:
            key (str): key to find.

        Raises:
            WmfdbValueError: if value is not boolean.

        Returns:
            Tuple[bool, bool]: value, key found.
        """
        true_vals = ["true", "1", "on"]
        false_vals = ["false", "0", "off"]
        sec, val, ok = self._get(key)
        if not ok:
            return False, False
        if val.lower() in true_vals:
            return True, True
        if val.lower() in false_vals:
            return False, True
        raise WmfdbValueError(f'Mysql config value [{sec}]{key} has non-boolean value: "{val}"')

    def get_no_value(self, key: str) -> Tuple[bool, bool]:
        """Get 'no value' value.

        Some keys have no value. E.g. `ssl_verify_server_cert`.
        So just detect if the key exists or not. (The return signature
        is kept as a tuple for consistency with the other get_* methods.)

        Args:
            key (str): key to find.

        Returns:
            Tuple[bool, bool]: key found, key found.
        """
        _, _, ok = self._get(key)
        return ok, ok

    def pymysql_conn_args(self) -> Dict[str, Any]:
        """Generate pymysql Connection arguments from my.cnf settings.

        Returns:
            Dict[str, Any]: kwargs to be passed to pymysql.connection.Connection
        """
        args: Dict[str, Any] = {}

        def _set_arg(
            key: str,
            *,
            arg: Optional[str] = None,
            get: Optional[Callable[[str], Tuple[Any, bool]]] = None,
        ) -> None:
            get = get or self.get_str
            arg = arg or key
            val, ok = get(key)
            if not ok:
                return
            args[arg] = val

        # All the args for pymysql that are readable from a my.cnf file
        _set_arg("user")
        _set_arg("password")
        _set_arg("host")
        _set_arg("database")
        _set_arg("socket", arg="unix_socket")
        _set_arg("port", get=self.get_int)
        _set_arg("default_character_set", arg="charset")
        _set_arg("connect_timeout", get=self.get_float)
        _set_arg("max_allowed_packet")
        _set_arg("bind_address")
        _set_arg("ssl_ca")
        _set_arg("ssl_cert")
        _set_arg("ssl_key")
        _set_arg("ssl_verify_server_cert", arg="ssl_verify_cert", get=self.get_no_value)
        _set_arg("ssl_verify_server_cert", arg="ssl_verify_identity", get=self.get_no_value)
        return args
