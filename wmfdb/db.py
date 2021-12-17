"""DB module."""

from typing import Any, Generic, Iterable, Optional, Text, TypeVar

from pymysql.connections import Connection
from pymysql.cursors import Cursor, DictCursor

_C = TypeVar("_C", bound=Cursor)


class DB:
    """Class to connect to a database instance."""

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the instance.

        Args:
            kwargs: passed directly through to pymysql.connections.Connection.
        """
        self._conn = Connection(**kwargs)

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

    def dict_cursor(self, *, timeout: Optional[float] = None) -> "CursorWrapper[DictCursor]":
        """Return a DictCursor wrapped in a CursorWrapper for this connection.

        Args:
            timeout (float, optional): Default timeout for queries using this
                cursor.

        Returns:
            CursorWrapper[DictCursor]: cursor.
        """
        return CursorWrapper(self._conn.cursor(cursor=DictCursor), timeout=timeout)

    def cursor(self, *, timeout: Optional[float] = None) -> "CursorWrapper[Cursor]":
        """Return a Cursor wrapped in a CursorWrapper for this connection.

        Args:
            timeout (float, optional): Default timeout for queries using this
                cursor.

        Returns:
            CursorWrapper[Cursor]: cursor.
        """
        return CursorWrapper(self._conn.cursor(cursor=Cursor), timeout=timeout)

    def select_db(self, db: str) -> None:
        """Select database.

        Args:
            db (str): Database to select.
        """
        self._conn.select_db(db)
        self._curr_db = db

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
    pass in 0.0 as the timeout value to execute()/executemany()/mogrify().

    Args:
        Generic ([Cursor]): pymysql.cursors.Cursor, or a subclass.
    """

    def __init__(self, cursor: _C, *, timeout: Optional[float] = None) -> None:
        """Initialize the instance.

        Args:
            cursor ([Cursor]): cursor to wrap.
            timeout (Optional[float], optional): Default query timeout, used
                if no timeout is provided for execute/executemany/mogrify.
                Defaults to None.
        """
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
        query = self._add_timeout(query, timeout)
        return self._cur.execute(query, args=args)

    def executemany(
        self,
        query: Text,
        args: Iterable[Any] = (),
        *,
        timeout: Optional[float] = None,
    ) -> Optional[int]:
        """Execute a query multiple times.

        See the class docstring for how query timeouts are configured.
        The timeout will be applied to each individual query run.

        Args:
            query (Text): Query to run.
            args (Iterable[Any], optional): Sets of arguments for each run
                of the query. If no args are provided, query is not run.
                Defaults to ().
            timeout (Optional[float], optional): Per-run query timeout.
                Defaults to None.

        Returns:
            Optional[int]: If args were provided, sum of rows matched by
                all runs of the query.
        """
        query = self._add_timeout(query, timeout)
        return self._cur.executemany(query, args=args)

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

    def __getattr__(self, attr: str) -> Any:
        return getattr(self._cur, attr)

    def __enter__(self) -> "CursorWrapper[_C]":
        # need to be manually added to this, getattr isn't enough
        return self

    def __exit__(self, *exc_info: Any) -> None:
        # need to be manually added to this, getattr isn't enough
        self.close()
