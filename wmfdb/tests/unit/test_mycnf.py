from pathlib import Path
from typing import Optional
from unittest.mock import call

import pytest
from pytest_mock import MockerFixture

from wmfdb import mycnf
from wmfdb.exceptions import WmfdbIOError, WmfdbValueError
from wmfdb.tests import get_fixture_path

FIXTURES_BASE = get_fixture_path("mycnf")


class TestCnf:
    def test_init_defaults(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.configparser.ConfigParser")
        c = mycnf.Cnf()
        assert c._section_order == mycnf.DEF_SECTION_LIST
        assert c._parser == m.return_value
        m.assert_called_once_with(interpolation=None, allow_no_value=True, default_section=None)
        assert c._parser.optionxform == c._normalize_keys

    def test_init_custom(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.configparser.ConfigParser")
        c = mycnf.Cnf(["clientlabsdb", "client"], arg1="1", arg2="22", allow_no_value=False)
        assert c._section_order == ["clientlabsdb", "client"]
        assert c._parser == m.return_value
        m.assert_called_once_with(
            arg1="1", arg2="22", interpolation=None, allow_no_value=True, default_section=None
        )
        assert c._parser.optionxform == c._normalize_keys

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("asdf", "asdf"),
            ("foo-bar", "foo_bar"),
            ("foo_bar", "foo_bar"),
        ],
    )
    def test__normalize_keys(self, key: str, expected: str) -> None:
        assert mycnf.Cnf._normalize_keys(key) == expected

    def test_load_cfgs(self, mocker: MockerFixture) -> None:
        m_find_cfgs = mocker.patch("wmfdb.mycnf.Cnf._find_cfgs", return_value=["find1", "find2"])
        m_load_cfg = mocker.patch("wmfdb.mycnf.Cnf._load_cfg")
        c = mycnf.Cnf()
        paths = (Path("load1"), Path("load2"), Path("load3"))
        c.load_cfgs(paths)
        m_find_cfgs.assert_called_once_with(paths)
        m_load_cfg.assert_has_calls(
            [
                call("find1"),
                call("find2"),
            ]
        )

    def test__load_cfg(self) -> None:
        cnf_path = FIXTURES_BASE / "base.cnf"
        c = mycnf.Cnf()
        assert not c._parser.sections()
        c._load_cfg(cnf_path)
        assert c._parser.sections() == ["client", "clientextra"]
        assert c._parser.get("client", "user") == '"user1"'
        assert c._parser.get("client", "ssl-ca") == "/path/to/CA.pem  # inline comment"
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
        m_cp = mocker.patch("wmfdb.mycnf.configparser.ConfigParser")
        m_cp.return_value.has_option.side_effect = [False, True]
        m_cleanup = mocker.patch("wmfdb.mycnf.Cnf._cleanup_value")
        c = mycnf.Cnf(section_order=["clientextra"] + list(mycnf.DEF_SECTION_LIST))
        assert c._get("port") == ("client", m_cleanup.return_value, True)
        m_cp.return_value.has_option.assert_has_calls(
            [
                call("clientextra", "port"),
                call("client", "port"),
            ]
        )
        m_cp.return_value.get.assert_called_once_with("client", "port")
        m_cleanup.assert_called_once_with(m_cp.return_value.get.return_value)

    def test__get_missing(self) -> None:
        c = mycnf.Cnf()
        assert c._get("missing_key") == ("", "", False)

    @pytest.mark.parametrize(
        "val,expected",
        [
            (None, ""),
            ("value0", "value0"),
            ("value1#comment", "value1"),
            ("value2  # comment", "value2"),
            ("value3", "value3"),
        ],
    )
    def test__cleanup_value(self, val: Optional[str], expected: str) -> None:
        c = mycnf.Cnf()
        assert c._cleanup_value(val) == expected

    @pytest.mark.parametrize(
        "val,expected",
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
        assert val[0] == "+" and val[-1] == "+", "val is wrapped incorrectly"
        assert expected[0] == "*" and expected[-1] == "*", "expected is wrapped incorrectly"
        val = val.strip("+")
        expected = expected.strip("*")
        c = mycnf.Cnf()
        assert c._cleanup_value(val) == expected

    def test_get_str(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["section", "foo", True]
        c = mycnf.Cnf()
        assert c.get_str("key") == ("foo", True)
        m.assert_called_once_with("key")

    def test_get_int(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["section", "1001", True]
        c = mycnf.Cnf()
        assert c.get_int("key") == (1001, True)
        m.assert_called_once_with("key")

    def test_get_int_missing(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["", "", False]
        c = mycnf.Cnf()
        assert c.get_int("key") == (0, False)

    def test_get_int_err(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["test_section", "1001a", True]
        c = mycnf.Cnf()
        with pytest.raises(
            WmfdbValueError, match=r'\[test_section\]test_key has non-integer value: "1001a"'
        ):
            c.get_int("test_key")

    def test_get_float(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["section", "1001.03", True]
        c = mycnf.Cnf()
        assert c.get_float("key") == (1001.03, True)
        m.assert_called_once_with("key")

    def test_get_float_missing(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["", "", False]
        c = mycnf.Cnf()
        assert c.get_float("key") == (0, False)

    def test_get_float_err(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["test_section", "1001.03a", True]
        c = mycnf.Cnf()
        with pytest.raises(
            WmfdbValueError, match=r'\[test_section\]test_key has non-float value: "1001.03a"'
        ):
            c.get_float("test_key")

    @pytest.mark.parametrize(
        "val,expected",
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
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["section", val, True]
        c = mycnf.Cnf()
        assert c.get_bool("key") == (expected, True)
        m.assert_called_once_with("key")

    def test_get_bool_missing(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["", "", False]
        c = mycnf.Cnf()
        assert c.get_bool("key") == (False, False)

    def test_get_bool_err(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["test_section", "maybe", True]
        c = mycnf.Cnf()
        with pytest.raises(
            WmfdbValueError, match=r'\[test_section\]test_key has non-boolean value: "maybe"'
        ):
            c.get_bool("test_key")

    def test_get_no_value(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["test_section", None, True]
        c = mycnf.Cnf()
        assert c.get_no_value("key") == (True, True)

    def test_get_no_value_missing(self, mocker: MockerFixture) -> None:
        m = mocker.patch("wmfdb.mycnf.Cnf._get")
        m.return_value = ["test_section", None, False]
        c = mycnf.Cnf()
        assert c.get_no_value("key") == (False, False)

    def test_pymysql_conn_args_one_cnf(self) -> None:
        c = mycnf.Cnf()
        c.load_cfgs([FIXTURES_BASE / "base.cnf"])
        assert c.pymysql_conn_args() == {
            "user": "user1",
            "port": 3999,
            "connect_timeout": 0.3,
            "max_allowed_packet": "16M",
            "ssl_ca": "/path/to/CA.pem",
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
            "port": 3999,
            "connect_timeout": 0.3,
            "max_allowed_packet": "32M",
            "ssl_ca": "/path/to/CA.pem",
            "ssl_verify_cert": True,
            "ssl_verify_identity": True,
        }

    def test_pymysql_conn_args_multi_section(self) -> None:
        c = mycnf.Cnf(section_order=["clientextra", "client"])
        c.load_cfgs([FIXTURES_BASE / "base.cnf"])
        assert c.pymysql_conn_args() == {
            "user": "user1_extra",
            "port": 3999,
            "connect_timeout": 0.3,
            "max_allowed_packet": "16M",
            "ssl_ca": "/path/to/CA.pem",
        }
