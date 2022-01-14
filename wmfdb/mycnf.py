"""mycnf module."""

import configparser
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, NamedTuple, Optional, Tuple

from wmfdb.exceptions import WmfdbIOError, WmfdbValueError

DEF_CFG_LIST = (
    Path("/etc/my.cnf"),
    Path("/etc/mysql/my.cnf"),
    Path("~/.my.cnf"),
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

    def load_cfgs(self, paths: Iterable[Path] = DEF_CFG_LIST) -> int:
        """Load my.cnf files in order.

        Any paths that don't exist or aren't readable are skipped.

        Args:
            paths (Iterable[Path], optional): Paths to load. Defaults to
                DEF_CFG_LIST.

        Returns:
            int: Number of config files loaded.
        """
        paths = self._find_cfgs(paths)
        for path in paths:
            self._load_cfg(path)
        return len(paths)

    def _load_cfg(self, path: Path) -> None:
        """Load a my.cnf file.

        Args:
            path (Path): File to load.

        Raises:
            WmfdbValueError: if parsing the file fails.
            WmfdbIOError: if unable to open the file.
        """
        try:
            with path.open(encoding="utf8") as f:
                try:
                    self._parser.read_file(f)
                except configparser.Error as e:
                    raise WmfdbValueError(e) from None
        except (FileNotFoundError, PermissionError) as e:
            raise WmfdbIOError(e) from None

    def _find_cfgs(self, paths: Iterable[Path]) -> List[Path]:
        """Filter out missing and unreadable files.

        ~ and ~user are expanded as part of this.

        Args:
            paths (Iterable[Path]): Files to look for.

        Returns:
            List[str]: Readable paths in expanded form.
        """
        ret: List[Path] = []
        for path in paths:
            path = path.expanduser()
            if path.is_file() and os.access(path, os.R_OK):
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
            return ""
        if "#" in val:
            val = self._cleanup_comment(val)
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            # Check for "value" or 'value', and strip matching quotes.
            val = val[1:-1]
        return val

    def _cleanup_comment(self, val: str) -> str:
        """Strip in-line comments from val.

        Mysql/Mariadb have very complex rules for in-line comments, which aren't
        documented, but can be seen in the code. E.g.:
        https://github.com/MariaDB/server/blob/1b8f0d4b674dd7f9414778054ef714f0fed71ccc/mysys/my_default.c#L842-L865
        Implementing full support for this requires a lot of complexity, including
        supporting quotes that appear in the middle of values, and escaping comments.

        Instead, this method implements a subset of the rules that should cover all
        normal use-cases:
        - If a value doesn't start with a quote char, or doesn't have a matching
            closing quote char, strip everything after the first #. E.g.:
            - `foo #bar#baz` -> `foo`
            - `"foo#bar#baz` -> `"foo`
            - `'foo#bar#baz"` -> `'foo`
        - If a value starts with a quote char and has a matching closing quote char,
            strip any comment after the (first) closing quote char. E.g.:
            - `"foo#bar"` -> `"foo#bar"`
            - `"foo#bar"baz#womble"` -> `"foo#bar"baz`
        If a comment is removed, all whitespace is also removed from the end of
        the value.

        Args:
            val (str): Value.

        Returns:
            str: Value with any in-line comment stripped.
        """
        if not val or "#" not in val:
            return val
        if val[0] not in ('"', "'") or val.count(val[0]) == 1:
            # Value is not (properly) quoted, drop everything after the first #
            return val[: val.index("#")].rstrip()
        # Value is quoted, find the the next quote.
        quote_close_idx = val.index(val[0], 1)
        try:
            cmt_idx = val.index("#", quote_close_idx)
        except ValueError:
            # No '#' after closing quote.
            return val
        return val[:cmt_idx].rstrip()

    def get_str(self, key: str) -> Optional[str]:
        """Get string value of key.

        Args:
            key (str): key to find.

        Returns:
            Optional[str]: value if found, otherwise None.
        """
        _, val, ok = self._get(key)
        if not ok:
            return None
        return val

    def get_int(self, key: str) -> Optional[int]:
        """Get int value of key.

        Args:
            key (str): key to find.

        Raises:
            WmfdbValueError: if value is not integer.

        Returns:
            Optional[int]: value if found, otherwise None.
        """
        sec, val, ok = self._get(key)
        if not ok:
            return None
        try:
            return int(val)
        except ValueError:
            raise WmfdbValueError(f'Mysql config value [{sec}]{key} has non-integer value: "{val}"')

    def get_float(self, key: str) -> Optional[float]:
        """Get float value of key.

        Args:
            key (str): key to find.

        Raises:
            WmfdbValueError: if value is not float.

        Returns:
            Optional[float]: value if found, otherwise None.
        """
        sec, val, ok = self._get(key)
        if not ok:
            return None
        try:
            return float(val)
        except ValueError:
            raise WmfdbValueError(f'Mysql config value [{sec}]{key} has non-float value: "{val}"')

    def get_bool(self, key: str) -> Optional[bool]:
        """Get bool value of key.

        Args:
            key (str): key to find.

        Raises:
            WmfdbValueError: if value is not boolean.

        Returns:
            Optional[bool]: value if found, otherwise None.
        """
        true_vals = ["true", "1", "on"]
        false_vals = ["false", "0", "off"]
        sec, val, ok = self._get(key)
        if not ok:
            return None
        if val.lower() in true_vals:
            return True
        if val.lower() in false_vals:
            return False
        raise WmfdbValueError(f'Mysql config value [{sec}]{key} has non-boolean value: "{val}"')

    def get_no_value(self, key: str) -> Optional[bool]:
        """Get 'no value' value.

        Some keys have no value. E.g. `ssl_verify_server_cert`.
        So just detect if the key exists or not. (The return signature
        is for consistency with the other get_* methods.)

        Args:
            key (str): key to find.

        Returns:
            Optional[bool]: True if found, otherwise None.
        """
        _, _, ok = self._get(key)
        if not ok:
            return None
        return True

    def pymysql_conn_args(self, **kwargs: Any) -> Dict[str, Any]:
        """Generate pymysql Connection arguments from my.cnf settings.

        Any arguments passed in take priority over my.cnf settings.

        Returns:
            Dict[str, Any]: kwargs to be passed to pymysql.connection.Connection
        """

        def _set_arg(
            key: str,
            *,
            arg: Optional[str] = None,
            get: Optional[Callable[[str], Any]] = None,
        ) -> None:
            if key in kwargs:
                # Don't overwrite anything that's already in kwargs.
                return
            get = get or self.get_str
            arg = arg or key
            val = get(key)
            if val is None:
                return
            kwargs[arg] = val

        # All the args for pymysql that are readable from a my.cnf file
        _set_arg("user")
        _set_arg("password")
        _set_arg("host")
        _set_arg("database")
        if ("host" not in kwargs) or (kwargs["host"] == "localhost"):
            _set_arg("socket", arg="unix_socket")
        else:
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
        return kwargs


class _PatternCnf(NamedTuple):
    pat: "re.Pattern[str]"
    cnf: Cnf


class CnfSelector:
    """Class to handle mapping a host to a Cnf.

    This is a convenince class. It simplifies the most common use-case:
    given a set of my.cnf files, and a hostname, return the correct pymysql
    connection arguments.
    """

    def __init__(
        self,
        def_section_order: Iterable[str] = DEF_SECTION_LIST,
        section_order_map: Optional[Iterable[Tuple[str, Iterable[str]]]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the instance.

        The default values should be sufficient for most use-cases.

        Args:
            def_section_order (Iterable[str], optional): Section order to use if
                no pattern in section_order_map matches. Defaults to
                DEF_SECTION_LIST.
            section_order_map (Optional[Iterable[Tuple[str, Iterable[str]]]], optional):
                Map of regular expression to section order. If not specified,
                a default map is used that matches "clouddb.*".
        """
        if section_order_map is None:
            section_order_map = [
                ("clouddb.*", ("clientlabsdb",) + DEF_SECTION_LIST),
            ]
        self._def_cnf = Cnf(def_section_order, **kwargs)
        self._cnfs: List[_PatternCnf] = []
        for pat, sec_list in section_order_map:
            rx = re.compile(pat)
            self._cnfs.append(_PatternCnf(rx, Cnf(sec_list, **kwargs)))

    def load_cfgs(self, paths: Iterable[Path] = DEF_CFG_LIST) -> int:
        """Load my.cnf files in order, for each Cnf.

        Args:
            paths (Iterable[Path], optional): Paths to load.
                Defaults to DEF_CFG_LIST.

        Returns:
            int: Number of config files loaded.
        """
        c = self._def_cnf.load_cfgs(paths)
        for _, cnf in self._cnfs:
            cnf.load_cfgs(paths)
        # Number of files loaded should be identical, so just
        # return the first result.
        return c

    def get_cnf(self, host: str) -> Cnf:
        """For a given hostname, return the relevant Cnf

        Args:
            host (str): hostname to match.

        Returns:
            Cnf: instance for the hostname.
        """
        for pat, cnf in self._cnfs:
            if pat.fullmatch(host):
                return cnf
        return self._def_cnf

    def pymysql_conn_args(self, *, host: str, **kwargs: Any) -> Dict[str, Any]:
        """For a given hostname, return the pymsql connection args.

        Any arguments passed in take priority over my.cnf settings.

        Args:
            host (str): hostname to match.

        Returns:
            Dict[str, Any]: kwargs to be passed to
                pymysql.connection.Connection
        """
        return self.get_cnf(host).pymysql_conn_args(host=host, **kwargs)
