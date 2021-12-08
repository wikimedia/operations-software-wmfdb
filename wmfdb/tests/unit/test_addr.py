import ipaddress
import socket

import pytest

from wmfdb import addr
from wmfdb.exceptions import WmfdbValueError
from wmfdb.section import SectionMap


def test_resolve_ip(mocker):
    ip_str = "127.0.0.1"
    dc_mock = mocker.patch("wmfdb.addr._dc_map")
    res_ip_mock = mocker.patch("wmfdb.addr._resolve_ip")
    ret = addr.resolve(ip_str)
    dc_mock.assert_not_called()
    res_ip_mock.assert_called_once_with(ipaddress.ip_address(ip_str))
    assert ret == res_ip_mock.return_value


def test_resolve_host(mocker):
    host = "localhost"
    dc_mock = mocker.patch("wmfdb.addr._dc_map")
    res_ip_mock = mocker.patch("wmfdb.addr._resolve_ip")
    ret = addr.resolve(host)
    assert ret == dc_mock.return_value
    dc_mock.assert_called_once_with(host)
    res_ip_mock.assert_not_called()


@pytest.mark.parametrize(
    "ip, host",
    [
        ("127.0.0.1", "localhost"),
        ("::1", "localhost"),
        ("192.0.2.1", "host-192.0.2.1"),
        ("2001:db8::11", "host-2001:db8::11"),
    ],
)
def test__resolve_ip(mocker, ip, host):
    m = mocker.patch("wmfdb.addr.socket.gethostbyaddr")
    m.side_effect = lambda ip: ("host-%s" % ip, None, None)
    assert addr._resolve_ip(ipaddress.ip_address(ip)) == host


def test__resolve_ip_error(mocker):
    m = mocker.patch("wmfdb.addr.socket.gethostbyaddr")
    m.side_effect = socket.herror()
    with pytest.raises(WmfdbValueError, match="Unable to resolve"):
        addr._resolve_ip(ipaddress.ip_address("192.168.1.1"))


@pytest.mark.parametrize(
    "host,expected",
    [
        ("host1102", "host1102.eqiad.wmnet"),
        ("h6003", "h6003.drmrs.wmnet"),
    ],
)
def test_dc_map(host, expected):
    assert addr._dc_map(host) == expected


def test_dc_map_no_dcid():
    with pytest.raises(WmfdbValueError, match="No datacenter ID"):
        addr._dc_map("host333")


def test_dc_map_bad_dcid():
    with pytest.raises(WmfdbValueError, match="Unknown datacenter ID"):
        addr._dc_map("host9001")


@pytest.mark.parametrize(
    "addr_, host, port",
    [
        ("2001:db8::11", "2001:db8::11", 3306),
        ("[2001:db8::11]", "2001:db8::11", 3306),
        ("[2001:db8::11]:3317", "2001:db8::11", 3317),
        ("[2001:db8::11]:f1", "2001:db8::11", 10111),
        ("192.0.2.1", "192.0.2.1", 3306),
        ("192.0.2.1:3317", "192.0.2.1", 3317),
        ("192.0.2.1:f1", "192.0.2.1", 10111),
        ("db2099", "db2099", 3306),
        ("db2099:3317", "db2099", 3317),
        ("db2099:f1", "db2099", 10111),
        ("db2099.codfw.wmnet", "db2099.codfw.wmnet", 3306),
        ("db2099.codfw.wmnet:3317", "db2099.codfw.wmnet", 3317),
        ("db2099.codfw.wmnet:f1", "db2099.codfw.wmnet", 10111),
    ],
)
def test_split(addr_, host, port):
    sm = SectionMap()
    assert addr.split(addr_, sm) == (host, port)


def test_split_invalid():
    with pytest.raises(WmfdbValueError, match=r"Invalid .*ipv6.* format"):
        addr.split("[1::", None)
