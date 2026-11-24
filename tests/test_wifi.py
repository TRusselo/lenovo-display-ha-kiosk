"""lhk wifi (from the clock tool's lck wifi) and the fixed address, on the display: over USB, with root.
The saved-network file holds every Wi-Fi password: it never reaches the log, and no copy is left behind."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

import pytest

from lhk import plan, staticip, wifi
from lhk.runner import Result, Tools
from lhk.staticip import StaticIp
from lhk.steps import Context, Paths
from lhk.system import SetupFailed
from tests.fakes import FakeRunner, FakeUI
from tests.test_static_ip import STORE

HOME = StaticIp("10.1.1.40", 24, "10.1.1.254", ("10.1.1.254",))
DUMPSYS = "Wi-Fi is enabled\nmWifiInfo SSID: Home, BSSID: 00:11:22:33:44:55, MAC: 02:00:00:00:00:00\n"
CAT = ("-s", "S1", "shell", "cat", wifi.STORE)


class Display:
    """The display's side: its saved networks, its Wi-Fi address and what was pushed."""

    def __init__(self, monkeypatch, store=STORE, ssid="Home", ip_after="10.1.1.40", write_code=0, md5_ok=True):
        self.store, self.ip, self.ip_after, self.reboots, self.pushed = store, "10.1.1.77", ip_after, 0, []
        self.local_copies, self.md5_ok = [], md5_ok
        # adb shell's output isn't byte-exact on Windows (CR LF): the file must come by adb pull.
        self.runner = FakeRunner({CAT: Result(0, store.replace("\n", "\r\n")), ("-s", "S1", "shell", "dumpsys", "wifi"):
                                  Result(0, DUMPSYS.replace("Home", ssid) if ssid else "Wi-Fi is disabled\n"),
                                  ("-s", "S1", "shell", f"cp {wifi.REMOTE} {wifi.STORE}"): Result(write_code, "")})
        orig = self.runner.run

        def run(args, **kw):
            if args[3:4] == ["push"]:
                self.pushed.append(Path(args[4]).read_bytes().decode("utf-8"))
                self.local_copies.append(Path(args[4]))
                assert args[5] == wifi.REMOTE
            if args[3:4] == ["pull"]:
                assert args[4] == wifi.STORE
                Path(args[5]).write_bytes(self.store.encode("utf-8"))
                self.local_copies.append(Path(args[5]))
            if args[3:5] == ["shell", "md5sum"]:
                orig(args, **kw)
                data = self.pushed[-1] if self.md5_ok else "something else"
                return Result(0, hashlib.md5(data.encode()).hexdigest() + "  " + wifi.STORE)
            return orig(args, **kw)
        self.runner.run = run
        monkeypatch.setattr(wifi, "ensure_root_rw", lambda ctx: None)
        monkeypatch.setattr(wifi, "reboot_and_wait", self._reboot)
        monkeypatch.setattr(wifi, "wifi_ip", lambda ctx: self.ip)
        monkeypatch.setattr(wifi.time, "sleep", lambda s: None)

    def _reboot(self, ctx, **kw):
        self.reboots += 1
        self.ip = self.ip_after

    def shells(self):
        return [c[4:] for c in self.runner.calls if c[3:4] == ["shell"]]


def _ctx(tmp_path, d, answers=()):
    c = Context(runner=d.runner, ui=FakeUI(answers), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1")
    return c


# --- the fixed address on the display ----------------------------------------------

def test_the_fixed_address_is_written_with_wifi_off_then_the_display_restarts_on_it(tmp_path, monkeypatch):
    d = Display(monkeypatch)
    c = _ctx(tmp_path, d)
    wifi.set_address(c, HOME)
    assert d.pushed == [staticip.with_fixed_address(STORE, "Home", HOME)]
    shells = d.shells()
    off = shells.index(["svc", "wifi", "disable"])
    write = next(i for i, s in enumerate(shells) if s[0].startswith("cp "))
    on_again = len(shells) - 1 - shells[::-1].index(["svc", "wifi", "enable"])
    assert off < write < on_again
    cmd = " ".join(shells[write])
    assert "chown 1000:1000" in cmd and "chmod 600" in cmd and "restorecon" in cmd and cmd.endswith("&& sync")
    # The restart is its own adb reboot, never inside that command (the clock's adb shell hung on one).
    assert "reboot" not in cmd
    assert ["rm", "-f", wifi.REMOTE] in shells
    assert d.reboots == 1
    assert any(l.startswith("[ok]") and "10.1.1.40" in l for l in c.ui.lines)


def test_the_file_with_the_passwords_never_reaches_the_log_or_stays_on_this_computer(tmp_path, monkeypatch, caplog):
    d = Display(monkeypatch)
    c = _ctx(tmp_path, d)
    with caplog.at_level(logging.DEBUG):
        wifi.set_address(c, HOME)
    assert "pw-Home-secret" not in caplog.text
    assert not any("pw-Home-secret" in l for l in c.ui.lines)
    assert d.local_copies and not any(p.exists() for p in d.local_copies)


@pytest.mark.parametrize("fault", [{"write_code": 1}, {"md5_ok": False}])
def test_wifi_is_switched_back_on_and_nothing_restarts_when_the_write_fails(tmp_path, monkeypatch, fault):
    d = Display(monkeypatch, **fault)
    with pytest.raises(SetupFailed):
        wifi.set_address(_ctx(tmp_path, d), HOME)
    shells = d.shells()
    assert shells[-1] == ["svc", "wifi", "enable"] and d.reboots == 0


def test_the_file_is_read_byte_exact_never_through_adb_shell(tmp_path, monkeypatch):
    d = Display(monkeypatch)
    wifi.set_address(_ctx(tmp_path, d), HOME)
    assert "\r" not in d.pushed[0]
    assert ["cat", wifi.STORE] not in d.shells()


def test_wifi_is_switched_on_first_when_a_stopped_run_left_it_off(tmp_path, monkeypatch):
    d = Display(monkeypatch)
    wifi.set_address(_ctx(tmp_path, d), HOME)
    assert d.shells()[0] == ["svc", "wifi", "enable"]


def test_a_display_that_comes_back_at_another_address_says_how_to_undo_it(tmp_path, monkeypatch):
    d = Display(monkeypatch, ip_after="10.1.1.99")
    with pytest.raises(SetupFailed, match="lhk wifi"):
        wifi.set_address(_ctx(tmp_path, d), HOME)


def test_a_display_off_wifi_or_on_an_unsaved_network_is_refused_before_anything_changes(tmp_path, monkeypatch):
    for d in (Display(monkeypatch, ssid=""), Display(monkeypatch, ssid="Cafe")):
        with pytest.raises(SetupFailed):
            wifi.set_address(_ctx(tmp_path, d), HOME)
        assert ["svc", "wifi", "disable"] not in d.shells() and d.reboots == 0


def test_none_puts_a_fixed_address_back_to_automatic(tmp_path, monkeypatch):
    fixed = staticip.with_fixed_address(STORE, "Home", HOME)
    d = Display(monkeypatch, store=fixed, ip_after="10.1.1.77")
    wifi.set_address(_ctx(tmp_path, d), None)
    assert d.pushed == [STORE]


# --- in setup ------------------------------------------------------------------------

def test_setup_asks_for_a_fixed_address_right_after_wifi():
    names = [s.name for s in plan.setup_steps()]
    assert names.index("fixed-address") == names.index("things-settings") + 1


def test_enter_in_setup_keeps_the_address_automatic_and_changes_nothing(tmp_path, monkeypatch):
    d = Display(monkeypatch)
    wifi.FixedAddressStep().run(_ctx(tmp_path, d, [""]))
    assert d.pushed == [] and d.reboots == 0


def test_a_fixed_address_typed_in_setup_is_set(tmp_path, monkeypatch):
    monkeypatch.setattr(staticip, "pc_gateway", lambda: "10.1.1.254")
    d = Display(monkeypatch)
    wifi.FixedAddressStep().run(_ctx(tmp_path, d, ["10.1.1.40", "", "", ""]))
    assert d.pushed == [staticip.with_fixed_address(STORE, "Home", HOME)]


# --- lhk wifi ------------------------------------------------------------------------

@pytest.fixture
def converted(monkeypatch):
    monkeypatch.setattr(wifi, "fetch", lambda id_, ctx: None)
    monkeypatch.setattr(wifi, "wait_booted", lambda ctx, **kw: None)
    monkeypatch.setattr(wifi, "detect", lambda runner, tools: [(wifi.Mode.ADB, "S1")])
    monkeypatch.setattr(wifi, "check_adb_identity",
                        lambda ctx, s: type("I", (), {"is_target_build": True})())
    joined = []
    monkeypatch.setattr(wifi, "join_wifi", lambda ctx, ssid, pw: joined.append((ssid, pw)))
    return joined


def test_lhk_wifi_joins_a_new_network_and_keeps_the_address_automatic(tmp_path, monkeypatch, converted):
    d = Display(monkeypatch, ssid="Home")
    c = _ctx(tmp_path, d, ["Cabin", "cabin-password", ""])
    seen = iter([DUMPSYS, DUMPSYS.replace("Home", "Cabin"), DUMPSYS.replace("Home", "Cabin")])
    d.runner.responses[("-s", "S1", "shell", "dumpsys", "wifi")] = [Result(0, s) for s in seen]
    assert wifi.change(c)
    assert converted == [("Cabin", "cabin-password")]
    assert d.pushed == [] and d.reboots == 0
    assert any(l.startswith("[ok]") and "Cabin" in l for l in c.ui.lines)
    assert any("saved before stay saved" in l for l in c.ui.lines)


def test_lhk_wifi_can_just_fix_the_address_of_the_network_its_on(tmp_path, monkeypatch, converted):
    monkeypatch.setattr(staticip, "pc_gateway", lambda: "10.1.1.254")
    d = Display(monkeypatch)
    c = _ctx(tmp_path, d, ["", "10.1.1.40", "", "", ""])
    assert wifi.change(c)
    assert converted == [] and d.pushed == [staticip.with_fixed_address(STORE, "Home", HOME)]


def test_lhk_wifi_enter_puts_a_fixed_address_back_to_automatic(tmp_path, monkeypatch, converted):
    d = Display(monkeypatch, store=staticip.with_fixed_address(STORE, "Home", HOME), ip_after="10.1.1.77")
    assert wifi.change(_ctx(tmp_path, d, ["", ""]))
    assert d.pushed == [STORE]


def test_lhk_wifi_says_so_when_the_display_cant_join(tmp_path, monkeypatch, converted):
    d = Display(monkeypatch)
    c = _ctx(tmp_path, d, ["Cabin", "wrong-password"])
    assert not wifi.change(c)
    assert d.pushed == [] and any("didn't join Cabin" in l for l in c.ui.lines)


def test_lhk_wifi_refuses_a_display_that_isnt_converted(tmp_path, monkeypatch, converted):
    monkeypatch.setattr(wifi, "check_adb_identity",
                        lambda ctx, s: type("I", (), {"is_target_build": False})())
    d = Display(monkeypatch)
    with pytest.raises(SetupFailed, match="converted"):
        wifi.change(_ctx(tmp_path, d, ["Cabin", "pw-pw-pw-pw"]))
    assert converted == []


def test_the_wifi_command_stops_adb_at_the_end(tmp_path, monkeypatch):
    from lhk import cli
    called = []
    monkeypatch.setattr(wifi, "change", lambda ctx: called.append("change") or True)
    monkeypatch.setattr(cli, "_stop_adb", lambda ctx: called.append("stop"))
    assert cli.main(["wifi", "--workdir", str(tmp_path)]) == 0
    assert called == ["change", "stop"]


def test_lhk_wifi_waits_for_the_display_to_be_plugged_in(tmp_path, monkeypatch, converted):
    # It stopped at once with "isn't connected over USB" when started before the display was plugged in.
    from lhk import wifi as w
    d = Display(monkeypatch)
    c = _ctx(tmp_path, d, ["", ""])
    c.state.pop("serial")
    found = iter([[], [], [(w.Mode.ADB, "S1")]])
    monkeypatch.setattr(w, "detect", lambda runner, tools: next(found))
    assert w.change(c)
    assert c.state["serial"] == "S1"
    assert any("[physical]" in l and "USB" in l for l in c.ui.lines)
