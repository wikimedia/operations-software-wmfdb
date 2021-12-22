from typing import List, Optional

import pytest

import wmfdb.mysql_cli as mysql_cli


@pytest.mark.parametrize(
    "host,port,skip_ssl,rest",
    [
        ("db2099", 3306, False, []),
        ("db2099", 10111, True, ["arg1", "--arg2"]),
        ("clouddb1099.eqiad.wmnet", 3306, False, ["arg1", "--arg2"]),
    ],
)
def test_build_args(host: str, port: int, skip_ssl: bool, rest: List[str]) -> None:
    args = mysql_cli.build_args(host, port, skip_ssl, rest)
    assert args.pop(0) == mysql_cli.CMD
    if host.startswith("clouddb"):
        assert args.pop(0) == "--defaults-group-suffix=labsdb"
    assert args.pop(0) == f"-h{host}"
    if port != 3306:
        assert args.pop(0) == f"-P{port}"
    if not skip_ssl:
        assert args[:3] == ["--ssl", f"--ssl-ca={mysql_cli.DEF_CA}", "--ssl-verify-server-cert"]
        args = args[3:]
    assert args == rest


@pytest.mark.parametrize(
    "ca,out_args",
    [
        (
            None,
            ["--ssl"],
        ),
        (
            "foo_ca_cert",
            ["--ssl", "--ssl-ca=foo_ca_cert", "--ssl-verify-server-cert"],
        ),
    ],
)
def test_ssl_args(ca: Optional[str], out_args: List[str]) -> None:
    assert mysql_cli.ssl_args(ssl_ca=ca) == out_args
