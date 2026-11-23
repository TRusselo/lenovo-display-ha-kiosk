"""A fixed address for the display's Wi-Fi (from the clock tool's lck/staticip.py): only the saved network's
<IpConfiguration> changes, every other byte stays, and no Wi-Fi password is needed."""
from __future__ import annotations

import xml.dom.minidom as xml_dom

import pytest

from lhk import staticip
from lhk.staticip import StaticIp
from tests.fakes import FakeUI

HOME = StaticIp("10.1.1.40", 24, "10.1.1.254", ("10.1.1.254",))


def _network(ssid: str, ip: str) -> str:
    return ("<Network>\n<WifiConfiguration>\n"
            f'<string name="ConfigKey">&quot;{ssid}&quot;WPA_PSK</string>\n'
            f'<string name="SSID">&quot;{ssid}&quot;</string>\n'
            f'<string name="PreSharedKey">&quot;pw-{ssid}-secret&quot;</string>\n'
            "</WifiConfiguration>\n<NetworkStatus>\n"
            '<string name="SelectionStatus">NETWORK_SELECTION_ENABLED</string>\n'
            f"</NetworkStatus>\n{ip}</Network>\n")


DHCP = staticip.ip_block(None)
STORE = ("<?xml version='1.0' encoding='utf-8' standalone='yes' ?>\n<WifiConfigStoreData>\n"
         '<int name="Version" value="1" />\n<NetworkList>\n'
         + _network("Shed", DHCP) + _network("Home", DHCP) +
         "</NetworkList>\n<DeletedEphemeralSSIDList />\n</WifiConfigStoreData>\n")


# --- the saved network ------------------------------------------------------------

def test_a_fixed_address_is_saved_as_android_writes_it():
    xml = staticip.with_fixed_address(STORE, "Home", StaticIp("10.1.1.40", 24, "10.1.1.254", ("1.1.1.1", "8.8.8.8")))
    xml_dom.parseString(xml)                                     # still well-formed
    home = xml[xml.index("&quot;Home&quot;"):]
    block = home[home.index("<IpConfiguration>"):home.index("</IpConfiguration>")]
    assert '<string name="IpAssignment">STATIC</string>' in block
    assert '<string name="LinkAddress">10.1.1.40</string>' in block
    assert '<int name="LinkPrefixLength" value="24" />' in block
    assert '<string name="GatewayAddress">10.1.1.254</string>' in block
    assert ('<string-array name="DNSServers" num="2">\n<item value="1.1.1.1" />\n<item value="8.8.8.8" />\n'
            '</string-array>') in block
    assert '<string name="ProxySettings">NONE</string>' in block


def test_only_that_networks_address_changes_and_every_other_byte_stays():
    xml = staticip.with_fixed_address(STORE, "Home", HOME)
    assert xml.count("STATIC") == 1
    assert xml.replace(staticip.ip_block(HOME), DHCP) == STORE
    assert "pw-Home-secret" in xml and "pw-Shed-secret" in xml      # kept, never needed


def test_none_puts_the_address_back_to_automatic():
    fixed = staticip.with_fixed_address(STORE, "Home", HOME)
    assert staticip.is_fixed(fixed, "Home") and not staticip.is_fixed(fixed, "Shed")
    assert staticip.with_fixed_address(fixed, "Home", None) == STORE
    assert not staticip.is_fixed(STORE, "Home")


def test_names_are_matched_as_android_escapes_them():
    store = STORE.replace("&quot;Home&quot;", "&quot;Tom&apos;s &amp; Co&quot;")
    xml = staticip.with_fixed_address(store, "Tom's & Co", HOME)
    assert xml.count("STATIC") == 1


@pytest.mark.parametrize("xml", [STORE.replace("Home", "Other"), "", "not xml"])
def test_a_network_that_isnt_saved_is_refused(xml):
    with pytest.raises(ValueError):
        staticip.with_fixed_address(xml, "Home", HOME)


# --- checking what was typed ------------------------------------------------------

@pytest.mark.parametrize("text, prefix", [("24", 24), ("/24", 24), ("255.255.255.0", 24), ("255.255.0.0", 16),
                                          (" 22 ", 22)])
def test_a_prefix_or_a_mask_is_understood(text, prefix):
    assert staticip.parse_prefix(text) == prefix


@pytest.mark.parametrize("text", ["33", "0", "255.0.255.0", "abc", "255.255.255.256"])
def test_a_wrong_prefix_or_mask_is_refused(text):
    with pytest.raises(ValueError):
        staticip.parse_prefix(text)


def test_a_router_at_254_is_inside_a_24():
    staticip.check(HOME)


@pytest.mark.parametrize("bad, words", [
    (StaticIp("10.1.1.40", 24, "10.1.2.1", ("10.1.1.254",)), "gateway"),
    (StaticIp("10.1.1.0", 24, "10.1.1.254", ("10.1.1.254",)), "network"),
    (StaticIp("10.1.1.255", 24, "10.1.1.254", ("10.1.1.254",)), "broadcast"),
    (StaticIp("10.1.1.254", 24, "10.1.1.254", ("10.1.1.254",)), "gateway"),
    (StaticIp("10.1.1.40", 24, "10.1.1.254", ()), "DNS"),
])
def test_addresses_that_cant_work_are_refused(bad, words):
    with pytest.raises(ValueError, match=words):
        staticip.check(bad)


# --- the default gateway ----------------------------------------------------------

def test_the_default_gateway_is_this_computers_when_on_the_same_network():
    assert staticip.default_gateway("10.1.1.40", 24, pc_gateway="10.1.1.254") == "10.1.1.254"


def test_otherwise_the_default_gateway_is_the_first_address():
    assert staticip.default_gateway("10.0.5.20", 24, pc_gateway="10.1.1.254") == "10.0.5.1"
    assert staticip.default_gateway("10.0.5.20", 24, pc_gateway=None) == "10.0.5.1"


def test_linux_routes_give_the_gateway():
    table = ("Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
             "enp5s0\t0001010A\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\n"
             "enp5s0\t00000000\tFE01010A\t0003\t0\t0\t100\t00000000\t0\t0\t0\n")
    assert staticip.gateway_from_proc_route(table) == "10.1.1.254"


def test_mac_and_windows_routes_give_the_gateway():
    assert staticip.gateway_from_route_get("   route to: default\n    gateway: 10.1.1.254\n") == "10.1.1.254"
    windows = ("Network Destination        Netmask          Gateway       Interface  Metric\n"
               "          0.0.0.0          0.0.0.0    10.1.1.254    10.1.1.10     25\n")
    assert staticip.gateway_from_route_print(windows) == "10.1.1.254"


# --- the questions ----------------------------------------------------------------

def _ask(answers, monkeypatch, pc="10.1.1.254"):
    monkeypatch.setattr(staticip, "pc_gateway", lambda: pc)
    ui = FakeUI(answers)
    return staticip.ask(ui), ui


def test_enter_keeps_the_address_automatic(monkeypatch):
    got, _ = _ask([""], monkeypatch)
    assert got is None


def test_enter_takes_each_default(monkeypatch):
    got, _ = _ask(["10.1.1.40", "", "", ""], monkeypatch)
    assert got == HOME


def test_the_gateway_dns_and_mask_can_each_be_typed(monkeypatch):
    got, _ = _ask(["10.0.5.20", "255.255.0.0", "10.0.0.1", "1.1.1.1, 8.8.8.8"], monkeypatch)
    assert got == StaticIp("10.0.5.20", 16, "10.0.0.1", ("1.1.1.1", "8.8.8.8"))


def test_a_mistyped_answer_asks_that_question_again(monkeypatch):
    got, ui = _ask(["10.1.1.400", "10.1.1.40", "abc", "", "10.1.2.1", "", ""], monkeypatch)
    assert got == HOME
    said = [l for l in ui.lines if not l.startswith("[ask]")]
    assert sum("isn't" in line or "outside" in line for line in said[1:]) == 3   # [0]: the intro
