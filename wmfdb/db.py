"""DB module."""
import logging
from typing import Any, Generic, List, Optional, Text, Tuple, TypeVar

import pymysql.constants
import pymysql.err
from pymysql.connections import Connection
from pymysql.cursors import Cursor, DictCursor

from wmfdb.exceptions import WmfdbDBError, WmfdbValueError

_C = TypeVar("_C", bound=Cursor)
logger = logging.getLogger(__name__)


class DB:
    """Class to connect to a database instance."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the instance.

        Args:
            kwargs: passed directly through to pymysql.connections.Connection.
        """

        self._user: Optional[str] = kwargs.get("user")
        self._host: str = kwargs.get("host", "localhost")
        self._unix_socket: Optional[str] = kwargs.get("unix_socket")
        self._port = kwargs.get("port", 3306)
        self._curr_db: Optional[str] = kwargs.get("database")

        if self._unix_socket:
            # The params have no effect if a unix_socket is being used.
            self._user = None
            self._host = "localhost"
            self._port = None

        logger.debug(f"{{{self.addr()}}} Connecting.")
        try:
            self._conn = Connection(**kwargs)
        except pymysql.err.OperationalError as e:
            raise WmfdbDBError(e) from None

    def dict_cursor(self, *, timeout: Optional[float] = None) -> "CursorWrapper[DictCursor]":
        """Return a DictCursor wrapped in a CursorWrapper for this connection.

        Args:
            timeout (float, optional): Default timeout for queries using this
                cursor.

        Returns:
            CursorWrapper[DictCursor]: cursor.
        """
        return CursorWrapper(self.addr(), self._conn.cursor(cursor=DictCursor), timeout=timeout)

    def cursor(self, *, timeout: Optional[float] = None) -> "CursorWrapper[Cursor]":
        """Return a Cursor wrapped in a CursorWrapper for this connection.

        Args:
            timeout (float, optional): Default timeout for queries using this
                cursor.

        Returns:
            CursorWrapper[Cursor]: cursor.
        """
        return CursorWrapper(self.addr(), self._conn.cursor(cursor=Cursor), timeout=timeout)

    def select_db(self, db: str) -> None:
        """Select database.

        Args:
            db (str): Database to select.
        """
        try:
            self._conn.select_db(db)
        except pymysql.err.OperationalError as e:
            if e.args[0] == pymysql.constants.ER.BAD_DB_ERROR:
                raise WmfdbValueError(e) from None
            raise WmfdbDBError(e) from None
        old_db = self._curr_db
        self._curr_db = db
        logger.debug(f"{{{self.addr()}}} Changed db {old_db or '[none]'}->{db}.")

    def db(self) -> Optional[str]:
        """Return the currently selected database (if any).

        Returns:
            Optional[str]: database, if selected, otherwise None.
        """
        return self._curr_db

    def host(self) -> str:
        """Format the db instance host.

        If the address is an ipv6 literal, it's returned between []'s.
        If it's ipv4, it's returned as-is.
        Otherwise the bare hostname is returned with the domain stripped.

        Returns:
            str: host description.
        """
        if ":" in self._host:
            # IPv6
            return f"[{self._host}]"
        if self._host[0].isdigit():
            # IPv4. WMF hostnames never start with a digit.
            return self._host
        # FQDN, return hostname.
        return self._host.split(".")[0]

    def addr(self) -> str:
        """Format the db instance address.

        If the connection is over unix domain socket, the form is:
            host:/path/to/socket
        If the connection is over tcp, to a non-3306 port, the form is:
            host:port
        Otherwise just the plain host is returned.

        Returns:
            str: db instance address.
        """
        h = self.host()
        if self._unix_socket:
            return f"{h}:{self._unix_socket}"
        elif self._port != 3306:
            return f"{h}:{self._port}"
        return h

    def desc(self) -> str:
        """Format the connection description.

        The form is user@addr[dbname]. E.g.:
            wikiadmin@db9999[plwiki]

        If the username is root, it's ommitted.
        If no database is selected, (none) is displayed.

        Returns:
            str: connection description.
        """
        db_name = self._curr_db or "(none)"
        d = f"{self.addr()}[{db_name}]"
        if not self._user or self._user == "root":
            return d
        return f"{self._user}@{d}"

    def __str__(self) -> str:
        return self.desc()

    # ### Directly proxied methods ###

    def begin(self) -> None:
        self._conn.begin()

    def close(self) -> None:
        self._conn.close()

    @property
    def open(self) -> bool:
        return self._conn.open

    def ping(self, reconnect: bool = True) -> None:
        self._conn.ping(reconnect=reconnect)

    def rollback(self) -> None:
        self._conn.rollback()


class CursorWrapper(Generic[_C]):
    """Class to wrap a database cursor.

    This allows automatically handling query timeouts, and other potential
    customizations in the future.

    If a default timeout is set, but a given query should have no timeout,
    pass in 0.0 as the timeout value to execute()/mogrify().

    executemany() is not supported.

    Args:
        Generic ([Cursor]): pymysql.cursors.Cursor, or a subclass.
    """

    def __init__(self, addr: str, cursor: _C, *, timeout: Optional[float] = None) -> None:
        """Initialize the instance.

        Args:
            cursor ([Cursor]): cursor to wrap.
            timeout (Optional[float], optional): Default query timeout, used
                if no timeout is provided for execute/executemany/mogrify.
                Defaults to None.
        """
        self._addr = addr
        self._cur: _C = cursor
        self._def_tout = timeout

    def execute(
        self,
        query: Text,
        args: Any = None,
        *,
        timeout: Optional[float] = None,
    ) -> int:
        """Execute a query.

        See the class docstring for how query timeouts are configured.

        Args:
            query (Text): Query to run.
            args (Any, optional): Arguments to the query. Defaults to None.
            timeout (Optional[float], optional): Query timeout. Defaults to None.

        Returns:
            int: Number of rows matched by query.
        """
        q_str = self.mogrify(query, args, timeout=timeout)
        logger.debug(f"{{{self._addr}}} Executing: {q_str}")
        query = self._add_timeout(query, timeout)
        try:
            return self._cur.execute(query, args=args)
        except (pymysql.err.ProgrammingError, pymysql.err.OperationalError) as e:
            raise WmfdbDBError(f"{{{self._addr}}} Error executing query ({q_str}): {e}")

    def mogrify(
        self,
        query: Text,
        args: Any = None,
        *,
        timeout: Optional[float] = None,
    ) -> str:
        """Format a query for execution.

        This can be used to see exactly what query will be sent. Nothing
        is sent to the database instance.

        Args:
            query (Text): Query to format.
            args (Any, optional): Arguments for the query.
                Defaults to None.
            timeout (Optional[float], optional): Query timeout.
                Defaults to None.

        Returns:
            str: Formatted query, with arguments inserted, and
            query timeout configured.
        """
        query = self._add_timeout(query, timeout)
        return self._cur.mogrify(query, args=args)

    def _add_timeout(self, query: str, timeout: Optional[float]) -> str:
        """Add timeout to query.

        If timeout is not None, then that is used.
        Else if a default timeout was provided to the constructor, that is used.
        Otherwise no timeout is used and the query is returned unchanged.

        See the class docstring for how query timeouts are configured.

        Args:
            query (str): Query.
            timeout (Optional[float]): Query timeout.

        Returns:
            str: Query with query timeout added (if any).
        """
        # Bypass default timeout by setting timeout to 0.0
        if timeout is None:
            timeout = self._def_tout
        if timeout is not None:
            return f"SET STATEMENT max_statement_time={timeout} FOR {query}"
        return query

    def result_meta(self) -> Tuple[List[str], int]:
        """Return metadata for query result.

        Returns:
            Tuple[List[str], int]: list of column names, rows matched.
        """
        names = []
        if self.description:
            for col in self.description:
                names.append(col[0])
        return names, self.rowcount

    def __getattr__(self, attr: str) -> Any:
        if attr == "executemany":
            # Not supported - there's no good way to provide useful errors
            raise NotImplementedError
        return getattr(self._cur, attr)

    def __enter__(self) -> "CursorWrapper[_C]":
        # need to be manually added to this, getattr isn't enough
        return self

    def __exit__(self, *exc_info: Any) -> None:
        # need to be manually added to this, getattr isn't enough
        self.close()
