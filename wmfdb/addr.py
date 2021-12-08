"""Addr module."""

import ipaddress
import re
import socket
from typing import Tuple, Union

from wmfdb.exceptions import WmfdbValueError
from wmfdb.section import SectionMap


def resolve(host: str) -> str:
    """Resolve a hostname or IP to an fqdn.

    Args:
        host (str): hostname or IP.

    Returns:
        str: fqdn for host.
    """
    # First, check if its an IP:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Not an IP, treat as hostname.
        return _dc_map(host)
    else:
        # It's an IP, try to resolve it.
        return _resolve_ip(ip)


def _resolve_ip(ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> str:
    """Resolve an IP address to a hostname.

    Args:
        ip (Union[ipaddress.IPv4Address, ipaddress.IPv6Address]): IP address.
    Raises:
        WmfdbValueError: if IP cannot be resolved.

    Returns:
        str: FQDN for the IP address.
    """
    if ip.is_loopback:
        return "localhost"
    try:
        host, _, _ = socket.gethostbyaddr(ip.compressed)
    except socket.herror as e:
        raise WmfdbValueError(f"Unable to resolve ip address: '{ip}': {e}") from None
    return host


def _dc_map(host: str) -> str:
    """Map a bare hostname to a DC, and return the FQDN.

    Args:
        host (str): bare hostname.

    Raises:
        WmfdbValueError: if no DC id is found in host.
        WmfdbValueError: if DC id is not known.

    Returns:
        str: FQDN.
    """
    dcs = {
        1: "eqiad",
        2: "codfw",
        3: "esams",
        4: "ulsfo",
        5: "eqsin",
        6: "drmrs",
    }
    dc_rx = re.compile(r"^[a-zA-Z]+(?P<dc_id>\d)\d{3}$")
    m = dc_rx.match(host)
    if not m:
        raise WmfdbValueError(f"No datacenter ID detected in {host}")
    dc_id = int(m.group("dc_id"))
    if dc_id not in dcs:
        raise WmfdbValueError(f"Unknown datacenter ID '{dc_id}' (from '{host}')")
    return f"{host}.{dcs[dc_id]}.wmnet"


def split(addr: str, sm: SectionMap, def_port: int = 3306) -> Tuple[str, int]:
    """Split address into (host, port).

    Supports:
    - Plain ipv4: "192.0.2.1"
    - ipv4+port: "192.0.2.1:3007"
    - Plain ipv6: "2001:db8::11" or "[2001:db8::11]"
    - ipv6+port: "[2001:db8::11]:3116"
    - Plain hostname: "db2034"
    - Hostname+port: "db2054.codfw.wmnet:3241"

    Any port aliases (e.g. :s4) are mapped to the tcp port number.
    If the address doesn't contain a port, the def_port argument is used.
    No validation of the formatting of hostnames or ip addresses is done.

    Args:
        addr (str): Address.
        sm (wmfdb.section.SectionMap): A SectionMap to map port aliases to port numbers.
        def_port (int, optional): Default port to use if addr doesn't contain a port.
            Defaults to 3306.

    Raises:
        WmfdbValueError: if addr is a malformed [ipv6]:port format.
        WmfdbValueError: if port is not an integer.

    Returns:
        Tuple[str, int]: [description]
    """
    port = def_port
    port_str = ""
    if addr.count(":") > 1:
        # IPv6
        if addr[0] == "[":
            # [ipv6]:port
            addr_port_rx = re.compile(r"^\[(?P<host>[^]]+)\](?::(?P<port>\w+))?$")
            m = addr_port_rx.match(addr)
            if not m:
                raise WmfdbValueError(f"Invalid [ipv6]:port format: '{addr}'")
            addr = m.group("host")
            port_str = m.group("port")
        # plain ipv6
    elif ":" in addr:
        addr, port_str = addr.split(":")

    if port_str:
        try:
            port = int(port_str)
        except ValueError:
            sec = sm.by_name(port_str)
            port = sec.port
    return addr, port
