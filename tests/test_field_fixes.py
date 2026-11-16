"""Fixes from the first Mac conversion (HA Community thread, post 30): Cast's
data filled /data, Wi-Fi dropped before Kiosk Satellite's setup, edl needed
libusb from Homebrew, and a USB-C to USB-C cable hid the display from adb."""
import subprocess
from pathlib import Path

import pytest

from lhk import edl as edl_mod
from lhk import kiosk, modes, system
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI

CAST = "com.google.android.apps.mediashell"
DF = ("-s", "S1", "shell", "df", "-k", "/data")


@pytest.fixture(autouse=True)
def no_root_dance(monkeypatch):
    monkeypatch.setattr(system, "ensure_root_rw", lambda ctx: None)
    monkeypatch.setattr(kiosk, "ensure_root_rw", lambda ctx: None)
    monkeypatch.setattr(system.time, "sleep", lambda s: None)


def make_ctx(tmp_path, runner):
    c = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1")
    return c


def df(avail_kb):
    return Result(0, "Filesystem            1K-blocks   Used Available Use% Mounted on\n"
                     f"/dev/block/dm-0         3000000 2000000 {avail_kb}  93% /data\n")


def cleared(runner):
    return [c for c in runner.calls if c[3:] == ["shell", "pm", "clear", CAST]]


# --- Cast's data -------------------------------------------------------------

def test_degoogle_clears_cast_data(tmp_path):
    runner = FakeRunner()
    system.DegoogleStep().run(make_ctx(tmp_path, runner))
    assert cleared(runner)


def test_degoogle_clears_cast_data_after_disabling_it(tmp_path):
    runner = FakeRunner()
    system.DegoogleStep().run(make_ctx(tmp_path, runner))
    disable = next(i for i, c in enumerate(runner.calls) if c[4:7] == ["pm", "disable", CAST])
    clear = next(i for i, c in enumerate(runner.calls) if c[4:7] == ["pm", "clear", CAST])
    assert disable < clear


# --- free space before the install --------------------------------------------

@pytest.fixture
def apk(tmp_path, monkeypatch):
    f = tmp_path / "ks.apk"
    f.write_bytes(b"x" * 100 * 1024 * 1024)  # 100 MB: needs 300 MB free
    monkeypatch.setattr(kiosk, "fetch_apk", lambda ctx: f)
    return f


def installs(runner):
    return [c for c in runner.calls if c[3:4] == ["install"]]


def test_install_with_room_doesnt_clear_anything(tmp_path, apk):
    runner = FakeRunner({DF: df(2_000_000)})
    kiosk.InstallStep().run(make_ctx(tmp_path, runner))
    assert installs(runner) and not cleared(runner)


def test_install_short_of_space_clears_cast_then_installs(tmp_path, apk):
    runner = FakeRunner({DF: [df(150_000), df(1_000_000)]})
    kiosk.InstallStep().run(make_ctx(tmp_path, runner))
    assert cleared(runner) and installs(runner)


def test_install_still_short_of_space_stops_with_the_numbers(tmp_path, apk):
    runner = FakeRunner({DF: df(150_000)})
    with pytest.raises(kiosk.KioskError) as e:
        kiosk.InstallStep().run(make_ctx(tmp_path, runner))
    assert not installs(runner)
    assert "146 MB free" in str(e.value) and "300 MB" in str(e.value)


def test_install_goes_ahead_when_df_cant_be_read(tmp_path, apk):
    runner = FakeRunner({DF: Result(1, "df: /data: No such file")})
    kiosk.InstallStep().run(make_ctx(tmp_path, runner))
    assert installs(runner)


# --- Wi-Fi before Kiosk Satellite's setup -------------------------------------

IP = ("-s", "S1", "shell", "ip", "-4", "addr", "show", "wlan0")
HAS_IP = Result(0, "    inet 10.0.0.5/24 brd 10.0.0.255 scope global wlan0\n")


def test_reconnect_wifi_is_silent_when_connected(tmp_path):
    runner = FakeRunner({IP: HAS_IP})
    ctx = make_ctx(tmp_path, runner)
    system.reconnect_wifi(ctx)
    assert not ctx.ui.lines
    assert not any("monkey" in c for c in runner.calls)


def test_reconnect_wifi_opens_settings_and_waits(tmp_path):
    runner = FakeRunner({IP: [Result(0, ""), Result(0, ""), HAS_IP]})
    ctx = make_ctx(tmp_path, runner)
    system.reconnect_wifi(ctx)
    assert any(c[4:7] == ["monkey", "-p", "com.android.iotlauncher"] for c in runner.calls)
    text = " ".join(ctx.ui.lines)
    assert "lost Wi-Fi" in text and "Networks" in text and "Wi-Fi connected" in text


def test_kiosk_setup_checks_wifi_first(tmp_path, monkeypatch):
    order = []
    monkeypatch.setattr(kiosk, "reconnect_wifi", lambda ctx: order.append("wifi"))
    runner = FakeRunner()
    real_run = runner.run

    def run(args, **kw):
        if "monkey" in [str(a) for a in args]:
            order.append("open")
            raise RuntimeError("stop here")
        return real_run(args, **kw)

    runner.run = run
    with pytest.raises(RuntimeError):
        kiosk.SettingsStep().run(make_ctx(tmp_path, runner))
    assert order == ["wifi", "open"]


# --- no adb after flashing: see test_live_screen (a replug prompt, not a stop) ---


# --- libusb for edl on a Mac ----------------------------------------------------

def test_mac_without_homebrew_libusb_stops_before_edl():
    with pytest.raises(modes.UsbBackendMissing) as e:
        edl_mod.check_libusb(platform="darwin", exists=lambda p: False)
    assert "brew install libusb" in str(e.value)


@pytest.mark.parametrize("path", ["/opt/homebrew/lib/libusb-1.0.dylib", "/usr/local/lib/libusb-1.0.dylib"])
def test_mac_with_homebrew_libusb_is_fine(path):
    edl_mod.check_libusb(platform="darwin", exists=lambda p: p == path)


@pytest.mark.parametrize("plat", ["linux", "win32"])
def test_other_systems_arent_checked(plat):
    edl_mod.check_libusb(platform=plat, exists=lambda p: False)


def test_edl_checks_libusb_before_anything_else(tmp_path, monkeypatch):
    monkeypatch.setattr(edl_mod, "check_libusb", lambda: (_ for _ in ()).throw(modes.UsbBackendMissing("x")))
    monkeypatch.setattr(edl_mod, "fetch", lambda *a: pytest.fail("fetched before the libusb check"))
    with pytest.raises(modes.UsbBackendMissing):
        edl_mod.Edl(Context(runner=FakeRunner(), ui=FakeUI(), paths=Paths(tmp_path)))


def test_libusb_message_mentions_the_mac():
    assert "brew install libusb" in modes.LIBUSB_MISSING
