"""Mysql CLI module."""
import argparse
from typing import List, Optional

CMD = "mysql"
DEF_CA = "/etc/ssl/certs/Puppet_Internal_CA.pem"


class _HelpFormatter(
    argparse.RawDescriptionHelpFormatter,
    argparse.ArgumentDefaultsHelpFormatter,
):
    # From https://stackoverflow.com/a/68260107/13706377
    pass


def build_parser(
    prog: str,
    description: Optional[str],
    epilog: Optional[str],
) -> argparse.ArgumentParser:
    """Build argparse parser for mysql cli wrappers.

    Args:
        prog (str): Name of program.
        description (Optional[str]): argparse Description.
        epilog (Optional[str]): argparse Epilog.

    Returns:
        argparse.ArgumentParser: Configured parser
    """
    parser = argparse.ArgumentParser(
        prog=prog,
        description=description,
        epilog=epilog,
        formatter_class=_HelpFormatter,
        # Disallow automatic prefix matching, to avoid any unfortunate overlap with the
        # mysql binary flags.
        allow_abbrev=False,
    )
    parser.add_argument("instance", nargs=1)
    parser.add_argument("--log", default="WARN", help="Set logging level")
    parser.add_argument("--skip-ssl", action="store_true")
    return parser


def build_args(host: str, port: int, skip_ssl: bool, rest: List[str]) -> List[str]:
    """Build cmdline for mysql cli

    Args:
        host (str): Mysql host.
        port (int): Mysql port.
        skip_ssl (bool): Don't add ssl verification.
        rest (List[str]): Additional parameters to pass to mysql.

    Returns:
        List[str]: mysql cli arguments.
    """
    args = [CMD]
    if host.startswith("clouddb"):
        # This has to appear before any other options.
        args.append("--defaults-group-suffix=labsdb")
    args.append(f"-h{host}")
    if port != 3306:
        args.append(f"-P{port}")
    if not skip_ssl:
        args.extend(ssl_args())
    args.extend(rest)
    return args


def ssl_args(
    ssl_ca: Optional[str] = DEF_CA,
) -> List[str]:
    """Add desired args to mysql commandline.

    Args:
        ssl_ca (Optional[str], optional): Path to ssl CA. Defaults to DEF_CA.

    Returns:
        List[str]: mysql cli arguments.
    """
    args = []
    args.append("--ssl")
    if ssl_ca is not None:
        args.append(f"--ssl-ca={ssl_ca}")
        args.append("--ssl-verify-server-cert")
    return args
