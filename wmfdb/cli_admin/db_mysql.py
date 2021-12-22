#!/usr/bin/python3

import logging
import os
import sys

import wmfdb
from wmfdb import addr, log, mysql_cli, section
from wmfdb.exceptions import WmfdbError, WmfdbValueError


def main() -> None:
    try:
        run()
    except WmfdbError as e:
        logging.fatal(f"{e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("Ctrl-c pressed ...")
        sys.exit(1)


def run() -> None:
    parser = mysql_cli.build_parser(
        prog="db-mysql",
        description="A wrapper around the mysql cmdline client. It resolves the fqdn,\n"
        "converts section port aliases (e.g. :s3), and configures ssl\n"
        "appropriately.",
        epilog="Example usage:\n  db-mysql --log=debug db1115:s3 -e 'ghow global status'",
    )
    # Note: This overrides the mysql client's --version flag.
    parser.add_argument("--version", action="version", version=f"%(prog)s {wmfdb.__version__}")
    known, rest = parser.parse_known_args()
    try:
        log.setup(known.log.upper())
    except WmfdbValueError as e:
        # Logging isn't setup, so print error direct to stderr.
        print(e, file=sys.stderr)
        sys.exit(1)

    sm = section.SectionMap()
    host, port = addr.split(known.instance[0], sm)
    host = addr.resolve(host)

    args = mysql_cli.build_args(host, port, known.skip_ssl, rest)
    logging.info(f"Execing: {args}")
    try:
        sys.exit(os.execvp(mysql_cli.CMD, args))
    except FileNotFoundError as e:
        logging.fatal(f"Unable to execute command '{mysql_cli.CMD}': {e}")