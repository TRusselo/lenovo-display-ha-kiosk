"""An optional fixed address for the display's Wi-Fi, from the clock tool (lck/staticip.py).

Android 8.1 keeps it in WifiConfigStore.xml, in the saved network's <IpConfiguration> (IpConfigurationXmlUtil):
IpAssignment STATIC, LinkAddress, LinkPrefixLength, GatewayAddress and a DNSServers string array. Only that
block of the network the display is on changes: every other byte stays, so no Wi-Fi password is needed.
Asked after Wi-Fi in setup, and in lhk wifi; Enter keeps it automatic.
"""
from __future__ import annotations

import ipaddress
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StaticIp:
    address: str
    prefix: int
    gateway: str
    dns: tuple[str, ...]


def ip(text: str) -> str:
    """A plain IPv4 address, or ValueError."""
    text = text.strip()
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", text):
        raise ValueError(f'"{text}" isn\'t an address. It looks like four numbers with dots between them.')
    try:
        return str(ipaddress.IPv4Address(text))
    except ipaddress.AddressValueError:
        raise ValueError(f'"{text}" isn\'t an address: each number is 0 to 255.') from None


def parse_prefix(text: str) -> int:
    """24, /24 or 255.255.255.0."""
    text = text.strip().lstrip("/")
    if text.isdigit():
        n = int(text)
        if 1 <= n <= 30:
            return n
    elif re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", text):
        try:
            return ipaddress.IPv4Network(f"0.0.0.0/{text}").prefixlen
        except ValueError:
            pass
    raise ValueError(f'"{text}" isn\'t a subnet mask. It\'s usually 255.255.255.0 (or 24).')


def network(address: str, prefix: int) -> ipaddress.IPv4Network:
    return ipaddress.IPv4Network(f"{address}/{prefix}", strict=False)


def check(s: StaticIp) -> None:
    """ValueError, in plain words, for an address the display couldn't use."""
    net = network(s.address, s.prefix)
    addr = ipaddress.IPv4Address(s.address)
    if addr == net.network_address:
        raise ValueError(f"{s.address} is the network's own address, not one a device can have.")
    if addr == net.broadcast_address:
        raise ValueError(f"{s.address} is the network's broadcast address, not one a device can have.")
    if ipaddress.IPv4Address(s.gateway) not in net:
        raise ValueError(f"The gateway {s.gateway} is outside {net}, the display's network.")
    if s.gateway == s.address:
        raise ValueError(f"{s.address} is the gateway's (your router's) own address.")
    if not s.dns:
        raise ValueError("At least one DNS server is needed.")


def default_gateway(address: str, prefix: int, pc_gateway: str | None) -> str:
    """This computer's own gateway when it's on the display's network, else the network's first address."""
    net = network(address, prefix)
    if pc_gateway and ipaddress.IPv4Address(pc_gateway) in net and pc_gateway != address:
        return pc_gateway
    return str(net.network_address + 1)


def gateway_from_proc_route(text: str) -> str | None:
    """Linux /proc/net/route: the default route's gateway (little-endian hex)."""
    for line in text.splitlines()[1:]:
        f = line.split()
        if len(f) > 7 and f[1] == "00000000" and f[7] == "00000000" and f[2] != "00000000":
            return str(ipaddress.IPv4Address(bytes.fromhex(f[2])[::-1]))
    return None


def gateway_from_route_get(text: str) -> str | None:
    """macOS `route -n get default`."""
    m = re.search(r"gateway:\s*(\d+\.\d+\.\d+\.\d+)", text)
    return m.group(1) if m else None


def gateway_from_route_print(text: str) -> str | None:
    """Windows `route print -4 0.0.0.0`."""
    m = re.search(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)\s", text, re.M)
    return m.group(1) if m else None


def pc_gateway() -> str | None:
    """This computer's default gateway, or None. Only a default answer: never needed."""
    try:
        if sys.platform.startswith("linux"):
            return gateway_from_proc_route(Path("/proc/net/route").read_text())
        if sys.platform == "darwin":
            return gateway_from_route_get(subprocess.run(["route", "-n", "get", "default"], capture_output=True,
                                                         text=True, timeout=10).stdout)
        if sys.platform == "win32":
            return gateway_from_route_print(subprocess.run(["route", "print", "-4", "0.0.0.0"], capture_output=True,
                                                           text=True, timeout=10).stdout)
    except Exception:
        pass
    return None


def ip_block(s: StaticIp | None) -> str:
    """The <IpConfiguration> block of a saved network."""
    if s is None:
        return ('<IpConfiguration>\n<string name="IpAssignment">DHCP</string>\n'
                '<string name="ProxySettings">NONE</string>\n</IpConfiguration>\n')
    dns = "".join(f'<item value="{d}" />\n' for d in s.dns)
    return ('<IpConfiguration>\n<string name="IpAssignment">STATIC</string>\n'
            f'<string name="LinkAddress">{s.address}</string>\n'
            f'<int name="LinkPrefixLength" value="{s.prefix}" />\n'
            f'<string name="GatewayAddress">{s.gateway}</string>\n'
            f'<string-array name="DNSServers" num="{len(s.dns)}">\n{dns}</string-array>\n'
            '<string name="ProxySettings">NONE</string>\n</IpConfiguration>\n')


def _escaped(text: str) -> str:
    """A value as Android writes it in WifiConfigStore.xml: in double quotes, XML-escaped."""
    from xml.sax.saxutils import escape
    return escape(f'"{text}"', {'"': "&quot;", "'": "&apos;"})


_NETWORK = re.compile(r"<Network>.*?</Network>", re.S)
_IP = re.compile(r"<IpConfiguration>.*?</IpConfiguration>\n?", re.S)


def _find(xml: str, ssid: str) -> re.Match:
    name = f'<string name="SSID">{_escaped(ssid)}</string>'
    for m in _NETWORK.finditer(xml):
        if name in m.group(0) and _IP.search(m.group(0)):
            return m
    raise ValueError(f"{ssid} isn't among the display's saved networks.")


def is_fixed(xml: str, ssid: str) -> bool:
    return '<string name="IpAssignment">STATIC</string>' in _find(xml, ssid).group(0)


def with_fixed_address(xml: str, ssid: str, static: StaticIp | None) -> str:
    """The saved-network list with this network's address fixed (static), or automatic again (None)."""
    m = _find(xml, ssid)
    network = _IP.sub(lambda _: ip_block(static), m.group(0), count=1)
    return xml[:m.start()] + network + xml[m.end():]


WHY = ("The display gets its address from your router (automatic). To give it a fixed one instead, type it "
       "now: the address must be free on your network, outside the range your router hands out.")


def ask(ui) -> StaticIp | None:
    """An optional fixed address: a StaticIp, or None (Enter) for automatic. The mask, gateway and DNS
    each offer a default, kept with Enter."""
    ui.say(WHY)

    def question(text, parse):
        while True:
            try:
                return parse(ui.ask(text))
            except ValueError as e:
                ui.say(str(e))

    address = question("Fixed address for the display, or press Enter for automatic: ",
                       lambda a: ip(a) if a.strip() else None)
    if address is None:
        return None
    prefix = question("Subnet mask [255.255.255.0]: ", lambda a: parse_prefix(a) if a.strip() else 24)
    suggested = default_gateway(address, prefix, pc_gateway())

    def gateway(a):
        g = ip(a) if a.strip() else suggested
        check(StaticIp(address, prefix, g, (g,)))
        return g

    gw = question(f"Gateway (your router) [{suggested}]: ", gateway)
    dns = question(f"DNS servers, with commas between [{gw}]: ",
                   lambda a: tuple(ip(d) for d in a.split(",") if d.strip()) if a.strip() else (gw,))
    return StaticIp(address, prefix, gw, dns)
