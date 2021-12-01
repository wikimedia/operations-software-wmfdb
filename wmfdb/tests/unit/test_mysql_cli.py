from typing import List, Optional

import pytest

import wmfdb.mysql_cli as mysql_cli


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
