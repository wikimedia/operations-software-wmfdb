"""Mysql CLI module."""
import argparse
from typing import List, Optional


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


def ssl_args(
    ssl_ca: Optional[str] = "/etc/ssl/certs/Puppet_Internal_CA.pem",
) -> List[str]:
    """Add desired args to mysql commandline."""
    args = []
    args.append("--ssl")
    if ssl_ca is not None:
        args.append(f"--ssl-ca={ssl_ca}")
        args.append("--ssl-verify-server-cert")
    return args
