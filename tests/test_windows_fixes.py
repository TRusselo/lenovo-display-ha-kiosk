"""Fixes from the first Windows and untested-model reports (GitHub issues 1, 3 and 5)."""
from pathlib import Path

import pytest

from lhk import bootfix, edl as edl_mod, flash, system
from lhk.downloads import _repo_file, load_manifest
from lhk.modes import UsbBackendMissing
from lhk.runner import CommandFailed, Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI

REPO = Path(__file__).resolve().parent.parent


# --- Issue 1, 3, 5: edl crashed at 0% in Windows' cp1252 console ---------------------------

def _edl(tmp_path, monkeypatch, runner):
    (tmp_path / "edl" / "edl-abc").mkdir(parents=True)
    (tmp_path / "edl" / "edl-abc" / "edl.py").write_text("")
    (tmp_path / "edl" / "edl-abc" / "requirements.txt").write_text("")
    (tmp_path / "fw").mkdir()
    dirs = {"edl": tmp_path / "edl", "firehose": tmp_path / "fw"}
    monkeypatch.setattr(edl_mod, "fetch", lambda id_, ctx: dirs[id_])
    monkeypatch.setattr(edl_mod, "uv_path", lambda ctx: Path("uv"))
    return edl_mod.Edl(Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path)))


def test_edl_runs_with_utf8_output(tmp_path, monkeypatch):
    runner = FakeRunner()
    e = _edl(tmp_path, monkeypatch, runner)
    e.prepare()
    e.read(["boot_a"], tmp_path / "out")
    assert len(runner.envs) == 2
    for env in runner.envs:
        assert env["PYTHONUTF8"] == "1" and env["PYTHONIOENCODING"] == "utf-8"
        assert "PATH" in env or "Path" in env       # the rest of the environment is kept


ZADIG_OUT = ("main - [LIB]: Please first install libusb_win32 driver from Zadig\n"
             "NotImplementedError: Operation not supported or unimplemented on this platform\n")


def test_edl_without_the_windows_driver_says_zadig(tmp_path, monkeypatch):
    runner = FakeRunner(default=Result(1, ZADIG_OUT))
    e = _edl(tmp_path, monkeypatch, runner)
    with pytest.raises(UsbBackendMissing) as err:
        e.dump_gpt(tmp_path / "out")
    assert "Zadig" in str(err.value) and "drivers.md" in str(err.value)


def test_other_edl_failures_are_unchanged(tmp_path, monkeypatch):
    runner = FakeRunner(default=Result(1, "something else\n"))
    e = _edl(tmp_path, monkeypatch, runner)
    with pytest.raises(CommandFailed):
        e.dump_gpt(tmp_path / "out")


# --- Issue 3: the Windows build shipped the boot scripts with CRLF line endings -------------

SHIPPED_TEXT = ["assets/bootfix/ks-boot-fix.sh", "assets/bootfix/ks-volume-keys.sh",
                "assets/bootfix/ks-boot-fix.rc", "assets/degoogle.txt"]


@pytest.mark.parametrize("name", SHIPPED_TEXT)
def test_files_pushed_to_the_display_have_unix_line_endings(name):
    # Fails on the Windows CI runner if git converts them to CRLF on checkout.
    assert b"\r" not in (REPO / name).read_bytes()


def test_gitattributes_keeps_lf_on_windows_checkouts():
    text = (REPO / ".gitattributes").read_text(encoding="utf-8")
    assert "eol=lf" in text


def test_bootfix_pushes_lf_even_from_a_crlf_copy(tmp_path, monkeypatch):
    # Running from source on Windows with core.autocrlf: strip \r before pushing.
    src = tmp_path / "src"
    src.mkdir()
    for name in ("ks-boot-fix.sh", "ks-volume-keys.sh", "ks-boot-fix.rc"):
        (src / name).write_bytes(b"#!/system/bin/sh\r\necho hi\r\n")
    monkeypatch.setattr(bootfix, "_repo_file", lambda rel: src / Path(rel).name)
    monkeypatch.setattr(bootfix, "ensure_root_rw", lambda ctx: None)
    monkeypatch.setattr(bootfix, "reboot_and_wait", lambda ctx, **kw: None)
    monkeypatch.setattr(bootfix, "verify", lambda ctx, wait=90: [])
    monkeypatch.setattr(bootfix, "check_buttons", lambda ctx: None)
    jar = tmp_path / "ks-volkeys.jar"
    jar.write_bytes(b"PK\r\n")
    runner = FakeRunner()
    ctx = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path / "work"))
    ctx.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1", volkeys_jar=jar)
    bootfix.BootFixStep().run(ctx)
    pushed = {Path(c[5]).name: Path(c[4]) for c in runner.calls if c[3] == "push"}
    for name in ("ks-boot-fix.sh", "ks-volume-keys.sh", "ks-boot-fix.rc"):
        assert pushed[name].read_bytes() == b"#!/system/bin/sh\necho hi\n"
    assert pushed["ks-volkeys.jar"].read_bytes() == b"PK\r\n"     # binary: untouched


# --- Issues 1 and 5: the slot check stopped displays that were safe to flash ----------------

UNLOCKED = "(bootloader) avb-locked=0\n(bootloader) at-perm-attr-hash=802e273eca8ccaaa69b1623f96cd7e11\n"


def _flash_ctx(tmp_path, monkeypatch, slot, differ):
    from lhk.slots import SLOT_FIRMWARE
    parts = tmp_path / "backup" / "display" / "partitions"
    parts.mkdir(parents=True)
    for base in SLOT_FIRMWARE:
        (parts / f"{base}_a.bin").write_bytes(b"same")
        (parts / f"{base}_b.bin").write_bytes(b"other" if base in differ else b"same")
    runner = FakeRunner({
        ("-s", "S1", "getvar", "at-vboot-state"): Result(0, UNLOCKED),
        ("-s", "S1", "getvar", "product"): Result(0, "product: msm8x53\n"),
        ("-s", "S1", "getvar", "current-slot"): Result(0, f"current-slot: {slot}\n"),
        ("-s", "S1", "getvar", "max-download-size"): Result(0, "max-download-size: 0x1fe00000\n"),
    })
    ctx = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    ctx.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), unlocked_now=True,
                     progress_id="display")
    monkeypatch.setattr(flash, "wait_for_mode", lambda target, ctx, **kw: "S1")
    monkeypatch.setattr(flash, "detect", lambda runner, tools: [])
    images = {n: tmp_path / f"{n}.img" for n in flash.FLASH_SET}
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: images)
    return ctx, runner


def _flashed(runner):
    return ["erase", "userdata"] in [c[3:] for c in runner.calls]


def test_running_slot_a_flashes_even_when_slot_b_differs(tmp_path, monkeypatch):
    # Issue 5: slot A was running and marked successful; only slot B differed.
    ctx, runner = _flash_ctx(tmp_path, monkeypatch, "a", {"keymaster", "cmnlib", "oem_bootloader"})
    flash.FlashStep().run(ctx)
    assert _flashed(runner)


def test_running_slot_b_with_only_radio_firmware_differing_warns_and_flashes(tmp_path, monkeypatch):
    # Issue 1: slot B running, dsp/modem/drm/bluetooth older in A. It started fine after flashing.
    ctx, runner = _flash_ctx(tmp_path, monkeypatch, "b", {"dsp", "modem", "drm", "bluetooth"})
    flash.FlashStep().run(ctx)
    assert _flashed(runner)
    assert any("dsp" in l and "Note" in l for l in ctx.ui.lines)


def test_running_slot_b_with_a_different_bootloader_still_stops(tmp_path, monkeypatch):
    ctx, runner = _flash_ctx(tmp_path, monkeypatch, "b", {"aboot", "dsp"})
    with pytest.raises(flash.FlashRefused) as e:
        flash.FlashStep().run(ctx)
    assert "aboot" in str(e.value) and "dsp" not in str(e.value)
    assert "lhk restore" in str(e.value)       # don't move the backup away to get past it
    assert not _flashed(runner)


# --- Issue 5: an untested model had no on-screen keyboard for its Wi-Fi password ------------

def _kb_ctx(tmp_path, runner, force):
    ctx = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    ctx.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1", force_model=force)
    return ctx


def test_keyboard_step_comes_before_wifi():
    from lhk.plan import setup_steps
    names = [s.name for s in setup_steps()]
    assert names.index("keyboard") < names.index("things-settings")


def test_keyboard_is_left_alone_on_the_supported_model(tmp_path):
    runner = FakeRunner()
    assert system.KeyboardStep().done(_kb_ctx(tmp_path, runner, force=False))
    assert runner.calls == []


def test_keyboard_already_there_on_a_forced_model(tmp_path):
    runner = FakeRunner({("-s", "S1", "shell", "ime", "list", "-s"): Result(0, "com.example/.Ime\n")})
    assert system.KeyboardStep().done(_kb_ctx(tmp_path, runner, force=True))


def test_keyboard_installed_on_a_forced_model_without_one(tmp_path, monkeypatch):
    apk = tmp_path / "app-release.apk"
    apk.write_bytes(b"PK")
    monkeypatch.setattr(system, "fetch", lambda id_, ctx: apk if id_ == "simple-keyboard" else None)
    runner = FakeRunner({
        ("-s", "S1", "shell", "ime", "list", "-s"): [Result(0, ""), Result(0, system.IME + "\n")],
        ("-s", "S1", "shell", "settings", "get", "secure", "default_input_method"): Result(0, system.IME + "\n"),
    })
    ctx = _kb_ctx(tmp_path, runner, force=True)
    step = system.KeyboardStep()
    assert not step.done(ctx)
    step.run(ctx)
    tails = [c[3:] for c in runner.calls]
    assert ["install", "-r", str(apk)] in tails
    assert ["shell", "ime", "enable", system.IME] in tails
    assert ["shell", "ime", "set", system.IME] in tails


def test_manifest_pins_simple_keyboard():
    e = load_manifest()["simple-keyboard"]
    assert e["url"].startswith("https://github.com/rkkr/simple-keyboard/") and len(e["sha256"]) == 64
