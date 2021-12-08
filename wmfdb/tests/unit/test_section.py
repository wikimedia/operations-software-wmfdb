import pytest

from wmfdb import section
from wmfdb.exceptions import WmfdbIOError, WmfdbValueError


@pytest.fixture
def set_test_data_env(monkeypatch):
    monkeypatch.setenv(section.TEST_DATA_ENV, "y")


@pytest.mark.usefixtures("set_test_data_env")
class TestSectionMap:
    def _check_cfg_loaded(self, sm):
        num_sections = len(section.TEST_DATA)
        assert len(sm._section) == num_sections
        assert len(sm._port) == num_sections
        assert "f0" in sm._section
        assert sm._section["f0"] == 10110
        assert "alpha" in sm._section
        assert sm._section["alpha"] == 10320

    def test_init(self):
        sm = section.SectionMap()
        self._check_cfg_loaded(sm)

    def test_init_load(self, mocker):
        m_get_cfg = mocker.patch("wmfdb.section.SectionMap._get_cfg_file")
        m_parse_cfg = mocker.patch("wmfdb.section.SectionMap._parse_cfg")
        section.SectionMap()
        m_get_cfg.assert_called_once()
        m_parse_cfg.assert_called_once_with(m_get_cfg.return_value)

    def test_init_dont_load(self, mocker):
        m_get_cfg = mocker.patch("wmfdb.section.SectionMap._get_cfg_file")
        m_parse_cfg = mocker.patch("wmfdb.section.SectionMap._parse_cfg")
        sm = section.SectionMap(_load_cfg=False)
        assert len(sm._section) == 0
        assert len(sm._port) == 0
        m_get_cfg.assert_not_called()
        m_parse_cfg.assert_not_called()

    def test_get_cfg_file_default_path(self, monkeypatch, mocker):
        # Unset the env var so this test is hermetic.
        monkeypatch.delenv(section.TEST_DATA_ENV, raising=False)
        sm = section.SectionMap(_load_cfg=False)
        m = mocker.patch("builtins.open", mocker.mock_open())
        sm._get_cfg_file("")
        m.assert_called_once_with(section.DEFAULT_CFG_PATH, mode="r", newline="")

    def test_get_cfg_file_on_disk(self, monkeypatch, tmp_path):
        # Unset the env var so this test is hermetic.
        monkeypatch.delenv(section.TEST_DATA_ENV, raising=False)
        sm = section.SectionMap(_load_cfg=False)
        cfg = tmp_path / "section_ports.csv"
        with open(cfg, "w+") as f:
            for line in section.TEST_DATA:
                f.write(line)
        assert sm._get_cfg_file(str(cfg)) == section.TEST_DATA

    def test_get_cfg_file_missing(self, monkeypatch, tmp_path):
        # Unset the env var so this test is hermetic.
        monkeypatch.delenv(section.TEST_DATA_ENV, raising=False)
        sm = section.SectionMap(_load_cfg=False)
        with pytest.raises(WmfdbIOError, match="No such file"):
            sm._get_cfg_file(str(tmp_path / "section_ports.csv"))

    def test_get_cfg_file_eperm(self, monkeypatch, tmp_path):
        # Unset the env var so this test is hermetic.
        monkeypatch.delenv(section.TEST_DATA_ENV, raising=False)
        sm = section.SectionMap(_load_cfg=False)
        cfg = tmp_path / "section_ports.csv"
        cfg.touch(mode=0o000)
        with pytest.raises(WmfdbIOError, match="Permission denied"):
            sm._get_cfg_file(str(cfg))

    def test_get_cfg_file_test_data(self, mocker):
        sm = section.SectionMap(_load_cfg=False)
        m = mocker.patch("builtins.open", mocker.mock_open())
        lines = sm._get_cfg_file("")
        m.assert_not_called()
        assert lines[0] == section.TEST_DATA[0]

    def test_parse_cfg(self):
        sm = section.SectionMap(_load_cfg=False)
        cfg = sm._get_cfg_file("")
        sm._parse_cfg(cfg)
        self._check_cfg_loaded(sm)

    def test_parse_cfg_blank_section(self):
        sm = section.SectionMap(_load_cfg=False)
        cfg = "f0, 10110\n , 10111\nf2, 10112\n"
        with pytest.raises(WmfdbValueError, match=r"Line 1 .* blank section entry"):
            sm._parse_cfg(cfg.splitlines(keepends=True))

    def test_parse_cfg_invalid_int(self):
        sm = section.SectionMap(_load_cfg=False)
        cfg = "f0, 10110\nf1, 1011a\nf2, 10112\n"
        with pytest.raises(WmfdbValueError, match=r"Line 1 .* invalid port number"):
            sm._parse_cfg(cfg.splitlines(keepends=True))

    def test_names(self):
        sm = section.SectionMap()
        names = sm.names()
        assert len(names) == len(sm._section)
        assert names.index("alpha") == 0
        assert "f3" in names

    def test_ports(self):
        sm = section.SectionMap()
        ports = sm.ports()
        assert len(ports) == len(sm._port)
        assert ports.index(10110) == 0
        assert 10113 in ports

    @pytest.mark.parametrize(
        "name,exp_port",
        [
            (section.DEFAULT_SECTION, section.DEFAULT_PORT),
            ("f2", 10112),
        ],
    )
    def test_by_name(self, name, exp_port):
        sm = section.SectionMap()
        s = sm.by_name(name)
        assert s.name == name
        assert s.port == exp_port

    def test_by_name_invalid(self):
        sm = section.SectionMap()
        with pytest.raises(WmfdbValueError, match="Invalid section name"):
            sm.by_name("abcd")

    @pytest.mark.parametrize(
        "port, exp_name",
        [
            (section.DEFAULT_PORT, section.DEFAULT_SECTION),
            (10112, "f2"),
        ],
    )
    def test_by_port(self, port, exp_name):
        sm = section.SectionMap()
        s = sm.by_port(port)
        assert s.name == exp_name
        assert s.port == port

    def test_by_port_invalid(self):
        sm = section.SectionMap()
        with pytest.raises(WmfdbValueError, match="Invalid port number"):
            sm.by_port(1234)


class TestSection:
    def test_init(self):
        s = section.Section(name="abcd", port=1234)
        assert s.name == "abcd"
        assert s.port == 1234

    def test_blank_name(self):
        with pytest.raises(WmfdbValueError, match="Empty/blank section"):
            section.Section(name=" ", port=3306)

    def test_invalid_port(self):
        with pytest.raises(WmfdbValueError, match="Invalid port number"):
            section.Section(name="abcd", port=0)

    def test_init_def_name_error(self):
        with pytest.raises(WmfdbValueError, match="must have default port"):
            section.Section(name=section.DEFAULT_SECTION, port=1234)

    def test_init_def_port_error(self):
        with pytest.raises(WmfdbValueError, match=r"must have .* section name"):
            section.Section(name="abcd", port=3306)

    @pytest.mark.parametrize(
        "name,port,expected",
        [
            (section.DEFAULT_SECTION, section.DEFAULT_PORT, "/run/mysqld/mysqld.sock"),
            ("abcd", 1234, "/run/mysqld/mysqld.abcd.sock"),
        ],
    )
    def test_socket_path(self, name, port, expected):
        s = section.Section(name=name, port=port)
        assert s.socket_path() == expected

    @pytest.mark.parametrize(
        "name,port,expected",
        [
            (section.DEFAULT_SECTION, section.DEFAULT_PORT, "/srv/sqldata"),
            ("abcd", 1234, "/srv/sqldata.abcd"),
        ],
    )
    def test_datadir(self, name, port, expected):
        s = section.Section(name=name, port=port)
        assert s.datadir() == expected

    @pytest.mark.parametrize(
        "name,port,expected",
        [
            (section.DEFAULT_SECTION, section.DEFAULT_PORT, section.DEFAULT_PROM_PORT),
            ("abcd", 3321, 13321),
        ],
    )
    def test_prom_port(self, name, port, expected):
        s = section.Section(name=name, port=port)
        assert s.prom_port() == expected
