import re
from pathlib import Path
from typing import Any, List
from unittest.mock import call

import pytest
from pytest_mock import MockerFixture, MockType

from wmfdb import mycnf
from wmfdb.exceptions import WmfdbIOError, WmfdbValueError
from wmfdb.tests import get_fixture_path

FIXTURES_BASE = get_fixture_path("mycnf")


class TestCnf:
    def _mock_get(self, c: mycnf.Cnf, mocker: MockerFixture) -> MockType:
        return mocker.patch.object(c, "_get", autospec=True, spec_set=True)

    def test_init_defaults(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.configparser.ConfigParser", autospec=True, spec_set=True)
        c = mycnf.Cnf()
        assert c._section_order == mycnf.DEF_SECTION_LIST
        assert c._parser == m.return_value
        m.assert_called_once_with(interpolation=None, allow_no_value=True, default_section=None)
        assert c._parser.optionxform == c._normalize_keys

    def test_init_custom(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.configparser.ConfigParser", autospec=True, spec_set=True)
        c = mycnf.Cnf(
            ["clientlabsdb", "client"],
            empty_lines_in_values=False,
            inline_comment_prefixes="#.#",
            allow_no_value=False,
        )
        assert c._section_order == ["clientlabsdb", "client"]
        assert c._parser == m.return_value
        m.assert_called_once_with(
            empty_lines_in_values=False,
            inline_comment_prefixes="#.#",
            interpolation=None,
            allow_no_value=True,
            default_section=None,
        )
        assert c._parser.optionxform == c._normalize_keys

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("asdf", "asdf"),
            ("foo-bar", "foo_bar"),
            ("foo_bar", "foo_bar"),
        ],
    )
    def test__normalize_keys(self, key: str, expected: str) -> None:
        assert mycnf.Cnf._normalize_keys(key) == expected

    def test_load_cfgs(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m_find_cfgs = mocker.patch.object(
            c, "_find_cfgs", return_value=["find1", "find2"], autospec=True, spec_set=True
        )
        m_load_cfg = mocker.patch.object(c, "_load_cfg", autospec=True, spec_set=True)
        paths = (Path("load1"), Path("load2"), Path("load3"))
        c.load_cfgs(paths)
        m_find_cfgs.assert_called_once_with(paths)
        assert m_load_cfg.call_args_list == [
            call("find1"),
            call("find2"),
        ]

    def test__load_cfg(self) -> None:
        cnf_path = FIXTURES_BASE / "base.cnf"
        c = mycnf.Cnf()
        assert not c._parser.sections()
        c._load_cfg(cnf_path)
        assert c._parser.sections() == ["client", "clientextra"]
        assert c._parser.get("client", "user") == '"user1"'
        assert c._parser.get("client", "ssl-ca") == '"/path/to/#/CA.pem"  # inline comment'
        assert c._parser.get("client", "port") == "3999#inline comment"
        assert c._parser.get("clientextra", "user") == '"user1_extra"'
        # Normalization tests
        assert c._parser.get("client", "max-allowed-packet") == "16M"
        assert c._parser.get("client", "max_allowed_packet") == "16M"
        assert c._parser.get("client", "max_allowed-packet") == "16M"
        assert c._parser.get("client", "max-allowed_packet") == "16M"

    def test__load_cfg_parse_error(self) -> None:
        cnf_path = FIXTURES_BASE / "parse_error.cnf"
        c = mycnf.Cnf()
        with pytest.raises(WmfdbValueError, match="no section headers"):
            c._load_cfg(cnf_path)

    def test__load_cfg_not_found(self, tmp_path: Path) -> None:
        cnf_path = tmp_path / "my.cnf"
        c = mycnf.Cnf()
        with pytest.raises(WmfdbIOError, match="No such file"):
            c._load_cfg(cnf_path)

    def test__load_cfg_read_error(self, tmp_path: Path) -> None:
        cnf_path = tmp_path / "my.cnf"
        cnf_path.touch(mode=0o000)
        c = mycnf.Cnf()
        with pytest.raises(WmfdbIOError, match="Permission denied"):
            c._load_cfg(cnf_path)

    def test__find_cfgs(self, tmp_path: Path) -> None:
        paths = [
            tmp_path / "0_readable.cnf",
            tmp_path / "1_missing.cnf",
            tmp_path / "2_readable.cnf",
            tmp_path / "3_unreadable.cnf",
            tmp_path / "~",
        ]
        exp_paths = [
            tmp_path / "0_readable.cnf",
            tmp_path / "2_readable.cnf",
        ]
        paths[0].touch()
        paths[2].touch()
        paths[3].touch(mode=0o000)
        c = mycnf.Cnf()
        assert c._find_cfgs(paths) == exp_paths

    def test__get(self, mocker: MockerFixture) -> None:
        m_cp = mocker.patch("wmfdb.mycnf.configparser.ConfigParser", autospec=True, spec_set=True)
        m_cp.return_value.has_option.side_effect = [False, True]
        c = mycnf.Cnf(section_order=["clientextra"] + list(mycnf.DEF_SECTION_LIST))
        m_cleanup = mocker.patch.object(c, "_cleanup_value", autospec=True, spec_set=True)
        assert c._get("port") == ("client", m_cleanup.return_value, True)
        assert m_cp.return_value.has_option.call_args_list == [
            call("clientextra", "port"),
            call("client", "port"),
        ]

        m_cp.return_value.get.assert_called_once_with("client", "port")
        m_cleanup.assert_called_once_with(m_cp.return_value.get.return_value)

    def test__get_missing(self) -> None:
        c = mycnf.Cnf()
        assert c._get("missing_key") == ("", "", False)

    def test__cleanup_value_none(self) -> None:
        c = mycnf.Cnf()
        assert c._cleanup_value(None) == ""

    def test__cleanup_value_comment(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = mocker.patch.object(c, "_cleanup_comment", autospec=True, spec_set=True)
        assert c._cleanup_value("foo#bar") == m.return_value
        m.assert_called_once_with("foo#bar")

    @pytest.mark.parametrize(
        ("val", "expected"),
        [
            # For readability,
            # Input values are wrapped in +'s
            # Output values are wrapped in *'s
            ("++", "**"),  # Empty string
            ("+ +", "* *"),
            ("+  +", "*  *"),
            ("+a+", "*a*"),
            ("+aa+", "*aa*"),
            ("+'+", "*'*"),  # 1 single quote
            ("+''+", "**"),  # 2 single quotes
            ("+'a'+", "*a*"),
            ('+"+', '*"*'),  # 1 double quote
            ('+""+', "**"),  # 2 double quotes
            ('+"a"+', "*a*"),
            ("+' a'+", "* a*"),
            ("+'a '+", "*a *"),
            ("""+'"+""", """*'"*"""),
            ("""+'asdf"+""", """*'asdf"*"""),
            ("""+"'+""", """*"'*"""),
            ("""+"asdf'+""", """*"asdf'*"""),
        ],
    )
    def test__cleaup_value_quotes(self, val: str, expected: str) -> None:
        assert len(val) > 1, "val is too short"
        assert len(expected) > 1, "expected is too short"
        assert val[0] == "+" and val[-1] == "+", "val is wrapped incorrectly"  # noqa: PT018
        assert (  # noqa: PT018
            expected[0] == "*" and expected[-1] == "*"
        ), "expected is wrapped incorrectly"
        val = val.strip("+")
        expected = expected.strip("*")
        c = mycnf.Cnf()
        assert c._cleanup_value(val) == expected

    @pytest.mark.parametrize(
        ("val", "expected"),
        [
            ("", ""),
            ("'", "'"),
            ('"', '"'),
            ("foo", "foo"),
            ("foo#cmt", "foo"),
            ("foo #cmt", "foo"),
            ("foo# cmt", "foo"),
            ("foo#cmt1#cmt2", "foo"),
            ("'foo # cmt", "'foo"),
            ("\"foo # cmt'", '"foo'),
            ("'foo # bar#'baz", "'foo # bar#'baz"),
            ("'foo # bar#' # cmt", "'foo # bar#'"),
            ("''foo # bar # cmt", "''foo"),
        ],
    )
    def test__cleanup_comment(self, val: str, expected: str) -> None:
        c = mycnf.Cnf()
        assert c._cleanup_comment(val) == expected

    def test_get_str(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["section", "foo", True]
        assert c.get_str("key") == "foo"
        m.assert_called_once_with("key")

    def test_get_str_missing(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["", "", False]
        assert c.get_str("key") is None

    def test_get_int(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["section", "1001", True]
        assert c.get_int("key") == 1001
        m.assert_called_once_with("key")

    def test_get_int_missing(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["", "", False]
        assert c.get_int("key") is None

    def test_get_int_err(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["test_section", "1001a", True]
        with pytest.raises(
            WmfdbValueError, match=r'\[test_section\]test_key has non-integer value: "1001a"'
        ):
            c.get_int("test_key")

    def test_get_float(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["section", "1001.03", True]
        assert c.get_float("key") == 1001.03
        m.assert_called_once_with("key")

    def test_get_float_missing(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["", "", False]
        assert c.get_float("key") is None

    def test_get_float_err(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["test_section", "1001.03a", True]
        with pytest.raises(
            WmfdbValueError, match=r'\[test_section\]test_key has non-float value: "1001.03a"'
        ):
            c.get_float("test_key")

    @pytest.mark.parametrize(
        ("val", "expected"),
        [
            ("TRUE", True),
            ("True", True),
            ("true", True),
            ("1", True),
            ("FALSE", False),
            ("False", False),
            ("false", False),
            ("0", False),
        ],
    )
    def test_get_bool(self, val: str, expected: bool, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["section", val, True]
        assert c.get_bool("key") == expected
        m.assert_called_once_with("key")

    def test_get_bool_missing(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["", "", False]
        assert c.get_bool("key") is None

    def test_get_bool_err(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["test_section", "maybe", True]
        with pytest.raises(
            WmfdbValueError, match=r'\[test_section\]test_key has non-boolean value: "maybe"'
        ):
            c.get_bool("test_key")

    def test_get_no_value(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["test_section", None, True]
        assert c.get_no_value("key")

    def test_get_no_value_missing(self, mocker: MockerFixture) -> None:
        c = mycnf.Cnf()
        m = self._mock_get(c, mocker)
        m.return_value = ["test_section", None, False]
        assert not c.get_no_value("key")

    def test_pymysql_conn_args_one_cnf(self) -> None:
        c = mycnf.Cnf()
        c.load_cfgs([FIXTURES_BASE / "base.cnf"])
        assert c.pymysql_conn_args(user="override_user") == {
            "user": "override_user",
            "unix_socket": "/run/mysqld/client.sock",
            "connect_timeout": 0.3,
            "max_allowed_packet": "16M",
            "ssl_ca": "/path/to/#/CA.pem",
        }

    def test_pymysql_conn_args_multi_cnf(self) -> None:
        c = mycnf.Cnf()
        c.load_cfgs(
            [
                FIXTURES_BASE / "base.cnf",
                FIXTURES_BASE / "add.cnf",
            ]
        )
        assert c.pymysql_conn_args() == {
            "user": "user2",
            "unix_socket": "/run/mysqld/client.sock",
            "connect_timeout": 0.3,
            "max_allowed_packet": "32M",
            "ssl_ca": "/path/to/#/CA.pem",
            "ssl_verify_cert": True,
            "ssl_verify_identity": True,
        }

    def test_pymysql_conn_args_multi_section(self) -> None:
        c = mycnf.Cnf(section_order=["clientextra", "client"])
        c.load_cfgs([FIXTURES_BASE / "base.cnf"])
        assert c.pymysql_conn_args() == {
            "user": "user1_extra",
            "unix_socket": "/run/mysqld/client.sock",
            "connect_timeout": 0.3,
            "max_allowed_packet": "16M",
            "ssl_ca": "/path/to/#/CA.pem",
        }

    def test_pymsql_conn_args_no_host(self) -> None:
        c = mycnf.Cnf()
        c.load_cfgs([FIXTURES_BASE / "base.cnf"])
        kwargs = c.pymysql_conn_args()
        assert "unix_socket" in kwargs
        assert "port" not in kwargs

    def test_pymsql_conn_args_localhost(self) -> None:
        c = mycnf.Cnf()
        c.load_cfgs([FIXTURES_BASE / "base.cnf"])
        kwargs = c.pymysql_conn_args(host="localhost")
        assert "unix_socket" in kwargs
        assert "port" not in kwargs

    def test_pymsql_conn_args_hostname(self) -> None:
        c = mycnf.Cnf()
        c.load_cfgs([FIXTURES_BASE / "base.cnf"])
        kwargs = c.pymysql_conn_args(host="db9999")
        assert "unix_socket" not in kwargs
        assert kwargs["port"] == 3999


class TestCnfSelector:
    @pytest.fixture(autouse=True)
    def _mock_cnf(self, mocker: MockerFixture) -> None:
        # Keep a reference to the original class so we can use it in the factory.
        self._m_cnf_orig = mycnf.Cnf
        self.mock_cnfs: List[Any] = []

        def _factory(*args: Any, **kwargs: Any) -> Any:
            m = mocker.create_autospec(self._m_cnf_orig, spec_set=True)(*args, **kwargs)
            self.mock_cnfs.append(m)
            return m

        self.m_cnf = mocker.patch(
            "wmfdb.mycnf.Cnf",
            side_effect=_factory,
            autospec=True,
            spec_set=True,
        )

    def test_init_defaults(self) -> None:
        cs = mycnf.CnfSelector()
        assert self.m_cnf.call_args_list == [
            call(mycnf.DEF_SECTION_LIST),
            call(("clientlabsdb", "client")),
        ]
        assert cs._def_cnf == self.mock_cnfs[0]
        assert cs._cnfs[0].pat == re.compile("(clouddb.*|an-redacteddb.*)")
        assert cs._cnfs[0].cnf == self.mock_cnfs[1]

    def test_init_custom(self) -> None:
        cs = mycnf.CnfSelector(
            def_section_order=("def1", "def2"),
            section_order_map=[
                ("aaaa", ("a1", "a2", "a3")),
                ("bbbb.*", ("b1")),
            ],
            user="user1",
            port=9999,
        )
        assert self.m_cnf.call_args_list == [
            call(("def1", "def2"), user="user1", port=9999),
            call(("a1", "a2", "a3"), user="user1", port=9999),
            call(("b1"), user="user1", port=9999),
        ]
        assert cs._def_cnf == self.mock_cnfs[0]
        assert cs._cnfs[0].pat.pattern == "aaaa"
        assert cs._cnfs[0].cnf == self.mock_cnfs[1]
        assert cs._cnfs[1].pat.pattern == "bbbb.*"
        assert cs._cnfs[1].cnf == self.mock_cnfs[2]

    def test_load_cfgs(self, mocker: MockerFixture) -> None:
        cs = mycnf.CnfSelector()
        assert cs.load_cfgs() == cs._def_cnf.load_cfgs.return_value  # type: ignore
        assert cs._def_cnf.load_cfgs.call_args_list == [  # type: ignore
            call(mycnf.DEF_CFG_LIST),
        ]

    def test_get_cnf_def(self) -> None:
        cs = mycnf.CnfSelector()
        assert cs.get_cnf("db9999") == cs._def_cnf

    def test_get_cnf_clouddb(self) -> None:
        cs = mycnf.CnfSelector()
        assert cs.get_cnf("clouddb9999") == cs._cnfs[0].cnf

    def test_get_cnf_an_redacteddb(self) -> None:
        cs = mycnf.CnfSelector()
        assert cs.get_cnf("an-redacteddb9999") == cs._cnfs[0].cnf

    def test_pymsql_conn_args(self, mocker: MockerFixture) -> None:
        cs = mycnf.CnfSelector()
        cnf = self.mock_cnfs[0]
        mocker.patch.object(cs, "get_cnf", return_value=cnf, autospec=True, spec_set=True)
        cs.pymysql_conn_args(host="db9999", arg1="arg1a")
        cs.get_cnf.assert_called_once_with("db9999")  # type: ignore
        cnf.pymysql_conn_args.assert_called_once_with(host="db9999", arg1="arg1a")
