from typing import Any, Dict, Optional, Tuple

import pymysql.err
import pytest
from pymysql.cursors import Cursor, DictCursor
from pytest_mock import MockerFixture, MockType

from wmfdb import db
from wmfdb.exceptions import WmfdbDBError, WmfdbValueError


class TestDB:
    @pytest.fixture(autouse=True)
    def _mock_conn(self, mocker: MockerFixture) -> None:
        self.m_conn = mocker.patch("wmfdb.db.Connection", autospec=True, spec_set=True)

    @pytest.fixture
    def mock_cw(self, mocker: MockerFixture) -> MockType:
        return mocker.patch("wmfdb.db.CursorWrapper", autospec=True, spec_set=True)

    def _mock_addr(self, d: db.DB, mocker: MockerFixture) -> MockType:
        return mocker.patch.object(d, "addr", autospec=True, spec_set=True)

    def test_init_defaults(self) -> None:
        d = db.DB()
        self.m_conn.assert_called_once_with()
        assert d._user is None
        assert d._host == "localhost"
        assert d._unix_socket is None
        assert d._port == 3306
        assert d._curr_db is None

    def test_init_socket(self) -> None:
        d = db.DB(
            user="user1",
            host="host1",
            unix_socket="/run/mysql.sock",
            port=3307,
            database="database1",
        )
        assert d._user is None
        assert d._host == "localhost"
        assert d._unix_socket == "/run/mysql.sock"
        assert d._port is None
        assert d._curr_db == "database1"

    def test_init_port(self) -> None:
        d = db.DB(
            user="user1",
            host="host1",
            port=3307,
        )
        assert d._user == "user1"
        assert d._host == "host1"
        assert d._unix_socket is None
        assert d._port == 3307

    def test_init_err(self) -> None:
        self.m_conn.side_effect = pymysql.err.OperationalError
        with pytest.raises(WmfdbDBError):
            db.DB()
        self.m_conn.assert_called_once_with()

    def test_dict_cursor(self, mock_cw: MockType, mocker: MockerFixture) -> None:
        conn_obj = self.m_conn.return_value
        d = db.DB()
        m_addr = self._mock_addr(d, mocker)
        c = d.dict_cursor()
        conn_obj.cursor.assert_called_once_with(cursor=DictCursor)
        mock_cw.assert_called_once_with(
            m_addr.return_value, conn_obj.cursor.return_value, timeout=None
        )
        assert c == mock_cw.return_value

    def test_dict_cursor_tout(self, mock_cw: MockType, mocker: MockerFixture) -> None:
        conn_obj = self.m_conn.return_value
        d = db.DB()
        m_addr = self._mock_addr(d, mocker)
        d.dict_cursor(timeout=99.1)
        mock_cw.assert_called_once_with(
            m_addr.return_value, conn_obj.cursor.return_value, timeout=99.1
        )

    def test_cursor(self, mock_cw: MockType, mocker: MockerFixture) -> None:
        conn_obj = self.m_conn.return_value
        d = db.DB()
        m_addr = self._mock_addr(d, mocker)
        c = d.cursor()
        conn_obj.cursor.assert_called_once_with(cursor=Cursor)
        mock_cw.assert_called_once_with(
            m_addr.return_value, conn_obj.cursor.return_value, timeout=None
        )
        assert c == mock_cw.return_value

    def test_cursor_tout(self, mock_cw: MockType, mocker: MockerFixture) -> None:
        conn_obj = self.m_conn.return_value
        d = db.DB()
        m_addr = self._mock_addr(d, mocker)
        d.cursor(timeout=99.1)
        mock_cw.assert_called_once_with(
            m_addr.return_value, conn_obj.cursor.return_value, timeout=99.1
        )

    def test_select_db(self) -> None:
        d = db.DB()
        d.select_db("test1")
        self.m_conn.return_value.select_db.assert_called_once_with("test1")
        assert d._curr_db == "test1"

    def test_select_db_bad_db(self) -> None:
        self.m_conn.return_value.select_db.side_effect = pymysql.err.OperationalError(
            pymysql.constants.ER.BAD_DB_ERROR, "bad db err"
        )
        d = db.DB()
        with pytest.raises(WmfdbValueError):
            d.select_db("test1")

    def test_select_db_err(self) -> None:
        self.m_conn.return_value.select_db.side_effect = pymysql.err.OperationalError(
            -1, "bad db err"
        )
        d = db.DB()
        with pytest.raises(WmfdbDBError):
            d.select_db("test1")

    def test_db(self) -> None:
        d = db.DB()
        d._curr_db = "test2"
        assert d.db() == "test2"

    @pytest.mark.parametrize(
        "host",
        [
            ("::1"),
            ("2001:db8::11"),
        ],
    )
    def test_host_ipv6(self, host: str) -> None:
        d = db.DB(host=host)
        assert d.host() == f"[{host}]"

    @pytest.mark.parametrize(
        "host",
        [
            ("127.0.0.1"),
            ("192.0.2.1"),
        ],
    )
    def test_host_ipv4(self, host: str) -> None:
        d = db.DB(host=host)
        assert d.host() == host

    @pytest.mark.parametrize(
        "host",
        [
            ("db9999"),
            ("db9999.site"),
            ("db9999.site.wmnet"),
        ],
    )
    def test_host_hostname(self, host: str) -> None:
        d = db.DB(host=host)
        assert d.host() == "db9999"

    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            ({"unix_socket": "/run/mysql.sock"}, "host1:/run/mysql.sock"),
            ({}, "host1"),
            ({"port": 3306}, "host1"),
            ({"port": 3307}, "host1:3307"),
        ],
    )
    def test_addr(self, args: Dict[str, Any], expected: str, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.db.DB.host", autospec=True, spec_set=True)
        m.return_value = "host1"
        d = db.DB(**args)
        assert d.addr() == expected

    @pytest.mark.parametrize(
        ("args", "expected"),
        [
            ({}, "addr1[(none)]"),
            ({"database": "test1"}, "addr1[test1]"),
            ({"user": "root"}, "addr1[(none)]"),
            ({"user": "notroot"}, "notroot@addr1[(none)]"),
            ({"user": "notroot", "database": "test1"}, "notroot@addr1[test1]"),
        ],
    )
    def test_desc(self, args: Dict[str, Any], expected: str, mocker: MockerFixture) -> None:
        d = db.DB(**args)
        m_addr = self._mock_addr(d, mocker)
        m_addr.return_value = "addr1"
        assert d.desc() == expected


class TestCursorWrapper:
    @pytest.fixture(autouse=True)
    def _mock_cur(self, mocker: MockerFixture) -> None:
        self.m_cur = mocker.create_autospec(CursorForTest, spec_set=True)

    def _mock_add_timeout(self, c: db.CursorWrapper[Any], mocker: MockerFixture) -> Any:
        return mocker.patch.object(c, "_add_timeout", autospec=True, spec_set=True)

    def _mock_mogrify(self, c: db.CursorWrapper[Any], mocker: MockerFixture) -> Any:
        return mocker.patch.object(c, "mogrify", autospec=True, spec_set=True)

    def test_init(self) -> None:
        c = db.CursorWrapper("host1", self.m_cur)
        assert c._addr == "host1"
        assert c._cur == self.m_cur
        assert c._def_tout is None

    def test_init_tout(self) -> None:
        c = db.CursorWrapper("host1", self.m_cur, timeout=99.1)
        assert c._addr == "host1"
        assert c._cur == self.m_cur
        assert c._def_tout == 99.1

    def test_execute(self, mocker: MockerFixture) -> None:
        c = db.CursorWrapper("host1", self.m_cur)
        m_mog = self._mock_mogrify(c, mocker)
        m_add_timeout = self._mock_add_timeout(c, mocker)
        ret = c.execute("query1")
        assert ret == self.m_cur.execute.return_value
        m_mog.assert_called_once_with("query1", None, timeout=None)
        m_add_timeout.assert_called_once_with("query1", None)
        self.m_cur.execute.assert_called_once_with(
            m_add_timeout.return_value,
            args=None,
        )

    def test_execute_full(self, mocker: MockerFixture) -> None:
        c = db.CursorWrapper("host1", self.m_cur)
        m_mog = mocker.patch.object(c, "mogrify", autospec=True, spec_set=True)
        m_add_timeout = mocker.patch.object(c, "_add_timeout", autospec=True, spec_set=True)
        ret = c.execute("query1", ("arg1", "arg2"), timeout=99.1)
        assert ret == self.m_cur.execute.return_value
        m_mog.assert_called_once_with("query1", ("arg1", "arg2"), timeout=99.1)
        m_add_timeout.assert_called_once_with("query1", 99.1)
        self.m_cur.execute.assert_called_once_with(
            m_add_timeout.return_value,
            args=("arg1", "arg2"),
        )

    @pytest.mark.parametrize(
        "excp",
        [
            (pymysql.err.ProgrammingError,),
            (pymysql.err.OperationalError,),
        ],
    )
    def test_execute_err(self, excp: Exception, mocker: MockerFixture) -> None:
        self.m_cur.execute.side_effect = excp
        c = db.CursorWrapper("host1", self.m_cur)
        mocker.patch.object(c, "mogrify", autospec=True, spec_set=True)
        mocker.patch.object(c, "_add_timeout", autospec=True, spec_set=True)
        with pytest.raises(WmfdbDBError):
            c.execute("query1")

    def test_mogrify(self, mocker: MockerFixture) -> None:
        c = db.CursorWrapper("host1", self.m_cur)
        m_add_timeout = mocker.patch.object(c, "_add_timeout", autospec=True, spec_set=True)
        ret = c.mogrify("query1")
        assert ret == self.m_cur.mogrify.return_value
        m_add_timeout.assert_called_once_with("query1", None)
        self.m_cur.mogrify.assert_called_once_with(
            m_add_timeout.return_value,
            args=None,
        )

    def test_mogrify_full(self, mocker: MockerFixture) -> None:
        c = db.CursorWrapper("host1", self.m_cur)
        m_add_timeout = mocker.patch.object(c, "_add_timeout", autospec=True, spec_set=True)
        ret = c.mogrify("query1", ("arg1", "arg2"), timeout=99.1)
        assert ret == self.m_cur.mogrify.return_value
        m_add_timeout.assert_called_once_with("query1", 99.1)
        self.m_cur.mogrify.assert_called_once_with(
            m_add_timeout.return_value,
            args=("arg1", "arg2"),
        )

    @pytest.mark.parametrize(
        ("def_tout", "tout", "exp_tout"),
        [
            (None, None, None),
            (5.5, None, 5.5),
            (None, 3.3, 3.3),
            (5.5, 3.3, 3.3),
            (5.5, 0.0, 0.0),
        ],
    )
    def test__add_timeout(
        self, def_tout: Optional[float], tout: Optional[float], exp_tout: Optional[float]
    ) -> None:
        if exp_tout is None:
            expected = "query1"
        else:
            expected = f"SET STATEMENT max_statement_time={exp_tout} FOR query1"
        c = db.CursorWrapper("host1", self.m_cur, timeout=def_tout)
        assert c._add_timeout("query1", tout) == expected

    def test_result_meta(self) -> None:
        self.m_cur.description = (
            ("foo", 1),
            ("bar", 2),
        )
        self.m_cur.rowcount = 99
        c = db.CursorWrapper("host1", self.m_cur)
        assert c.result_meta() == (["foo", "bar"], 99)

    def test_result_meta_none(self) -> None:
        self.m_cur.description = None
        self.m_cur.rowcount = -1
        c = db.CursorWrapper("host1", self.m_cur)
        assert c.result_meta() == ([], -1)

    def test_getattr(self) -> None:
        self.m_cur.max_stmt_length = 11099
        c = db.CursorWrapper("host1", self.m_cur)
        assert c.max_stmt_length == 11099

    def test_getattr_executemany(self) -> None:
        c = db.CursorWrapper("host1", self.m_cur)
        with pytest.raises(NotImplementedError):
            c.executemany()

    def test_enter(self) -> None:
        c = db.CursorWrapper("host1", self.m_cur)
        with c as c1:
            assert c == c1

    def test_exit(self) -> None:
        c = db.CursorWrapper("host1", self.m_cur)
        with c as _:
            pass
        self.m_cur.close.assert_called_once_with()


class CursorForTest(Cursor):
    description: Optional[Tuple[Tuple[str, ...]]] = None  # type: ignore
    rowcount: int = -1
