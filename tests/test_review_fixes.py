"""Regression tests for the final whole-branch review findings (C1-C5, I6-I14)."""
import json
import logging
import subprocess
import sys
from pathlib import Path

import pytest

from lhk import backup as bk, flash, kiosk, log, modes, system, unlock
from lhk.modes import Mode
from lhk.runner import RealRunner, Result, Tools
from lhk.steps import Context, Paths, Step, run_steps
from tests.fakes import FakeRunner, FakeUI
from tests.test_backup import FakeEdl, GPT

UNLOCKED = "(bootloader) avb-locked=0\n(bootloader) at-perm-attr-hash=802e273eca8ccaaa69b1623f96cd7e11\n"
FINGERPRINT = "Things/x:8.1.0/OIMK.211005.001/7795499:userdebug/dev-keys\n"


def make_ctx(tmp_path, runner, ui=None, **state):
    c = Context(runner=runner, ui=ui or FakeUI(), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1")
    c.state.update(state)
    return c


def converted_runner():
    return FakeRunner({
        ("-s", "S1", "shell", "getprop", "ro.build.fingerprint"): Result(0, FINGERPRINT),
        ("-s", "S1", "shell", "wm", "size"): Result(0, "Physical size: 800x1280\n"),
        ("-s", "S1", "getvar", "at-vboot-state"): Result(0, UNLOCKED),
    })


# C1: a lost progress file must not lead to re-flashing a converted display
def test_unlock_done_when_display_already_converted(tmp_path, monkeypatch):
    monkeypatch.setattr(unlock, "detect", lambda runner, tools: [(Mode.ADB, "S1")])
    assert unlock.UnlockStep().done(make_ctx(tmp_path, converted_runner())) is True


def test_flash_asks_before_wiping_an_already_unlocked_display(tmp_path, monkeypatch):
    monkeypatch.setattr(flash, "wait_for_mode", lambda target, ctx, **kw: "S1")
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: {n: tmp_path / n for n in flash.FLASH_SET})
    runner = converted_runner()
    ctx = make_ctx(tmp_path, runner, ui=FakeUI(answers=["no"]))
    with pytest.raises(flash.FlashRefused):
        flash.FlashStep().run(ctx)
    assert not [c for c in runner.calls if "flash" in c[3:4] or "erase" in c[3:4]]


def test_flash_needs_no_question_right_after_unlocking(tmp_path, monkeypatch):
    monkeypatch.setattr(flash, "wait_for_mode", lambda target, ctx, **kw: "S1")
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: {n: tmp_path / n for n in flash.FLASH_SET})
    runner = converted_runner()
    ctx = make_ctx(tmp_path, runner, unlocked_now=True)
    flash.FlashStep().run(ctx)
    assert ["erase", "userdata"] in [c[3:] for c in runner.calls]


# C2: restore must accept the display's own backup after slot switches
def test_restore_accepts_own_backup_after_slot_attribute_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "SECTOR", 1)
    ctx = make_ctx(tmp_path, FakeRunner(), ui=FakeUI(answers=["restore"]))
    out = tmp_path / "bk"
    e = FakeEdl(); e._tmp = tmp_path
    bk.backup(ctx, out, e)
    changed = bytearray(GPT.read_bytes())
    i = changed.find(b"EFI PART")
    changed[i + 16:i + 20] = b"\xde\xad\xbe\xef"          # header CRC
    changed[i + 512 + 48:i + 512 + 56] = b"\x7b" * 8    # first entry's attributes (A/B slot bits)
    e2 = FakeEdl(gpt_bytes=bytes(changed)); e2._tmp = tmp_path
    bk.restore(ctx, out, e2)
    assert e2.written


# C3: the standalone build runs at_auth_unlock.py through uv, with pycryptodome
def test_unlock_runs_tool_through_uv(tmp_path, monkeypatch):
    locked = UNLOCKED.replace("avb-locked=0", "avb-locked=1")
    runner = FakeRunner({("-s", "S1", "getvar", "at-vboot-state"): [Result(0, locked), Result(0, UNLOCKED)]})
    tool = tmp_path / "avb"
    (tool / "creds").mkdir(parents=True)
    monkeypatch.setattr(unlock, "fetch", lambda id_, ctx: tool)
    monkeypatch.setattr(unlock, "uv_path", lambda ctx: Path("uvbin"))
    monkeypatch.setattr(unlock, "wait_for_mode", lambda target, ctx, **kw: "S1")
    unlock.UnlockStep().run(make_ctx(tmp_path, runner))
    cmd = [c for c in runner.calls if any("at_auth_unlock.py" in a for a in c)][0]
    assert cmd == ["uvbin", "run", "--no-project", "--python", "3.12", "--with", "pycryptodome", "python",
                   str(tool / "at_auth_unlock.py"), "-s", "S1", str(tool / "creds")]


# C4: no libusb must not break fastboot/adb detection
def test_detect_without_libusb_backend_returns_no_edl(monkeypatch):
    def missing():
        raise modes.UsbBackendMissing("no libusb")
    runner = FakeRunner({("devices",): Result(0, "S1\tfastboot\n")})
    found = modes.detect(runner, Tools(adb=Path("noadb"), fastboot=Path("fastboot")), usb_scan=missing)
    assert found == [(Mode.FASTBOOT, "S1")]


# C5: two displays on USB, or a different display than the one being converted
def test_flash_done_false_with_two_adb_devices(tmp_path, monkeypatch):
    monkeypatch.setattr(flash, "detect", lambda runner, tools: [(Mode.ADB, "S1"), (Mode.ADB, "S2")])
    assert flash.FlashStep().done(make_ctx(tmp_path, converted_runner())) is False


def test_serial_refuses_a_different_display_than_the_bound_one(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "detect", lambda runner, tools: [(Mode.ADB, "OTHER")])
    ctx = make_ctx(tmp_path, FakeRunner(), bound_serial="S1")
    ctx.state.pop("serial")
    with pytest.raises(system.SetupFailed):
        system.serial(ctx)


def test_progress_remembers_the_display_serial(tmp_path):
    class Bind(Step):
        name = title = "bind"

        def run(self, ctx):
            ctx.state["serial"] = "S9"

    ctx = Context(runner=None, ui=FakeUI(), paths=Paths(tmp_path), state={"progress_id": "d"})
    run_steps([Bind()], ctx)
    assert json.loads((tmp_path / "progress" / "d.json").read_text())["serial"] == "S9"
    ctx2 = Context(runner=None, ui=FakeUI(), paths=Paths(tmp_path), state={"progress_id": "d"})
    run_steps([Bind()], ctx2)
    assert ctx2.state["bound_serial"] == "S9"


# I6: root/remount don't survive reboots
def test_ensure_root_rw_runs_root_and_remount(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "wait_booted", lambda ctx, timeout=300, **kw: None)
    runner = FakeRunner({("-s", "S1", "shell", "id", "-u"): [Result(0, "2000\n"), Result(0, "0\n")],
                         ("-s", "S1", "shell", "touch /system/.lhk-rw && rm /system/.lhk-rw"):
                             Result(0, "")})
    system.ensure_root_rw(make_ctx(tmp_path, runner))
    ops = [c[3] for c in runner.calls]
    assert "root" in ops and "remount" in ops


def test_settings_wait_stops_with_a_message_when_the_user_types_stop(tmp_path, monkeypatch):
    monkeypatch.setattr(kiosk, "ensure_root_rw", lambda ctx: None)
    runner = FakeRunner({("-s", "S1", "shell", "cat", kiosk.PREFS): Result(0, "<map></map>")})
    ctx = make_ctx(tmp_path, runner)
    ctx.ui.answers = ["", "stop"]
    with pytest.raises(kiosk.KioskError, match="run the same command again"):
        kiosk.SettingsStep().run(ctx)


# I7: log is written, and real secret formats are masked
def test_redact_masks_xml_password_and_bearer_tokens():
    out = log.redact('<string name="flutter.ks.remote.password">abc123</string> Authorization: Bearer tok999')
    assert "abc123" not in out and "tok999" not in out


def test_runner_logs_commands_but_not_secret_output(tmp_path):
    logger = log.setup(tmp_path / "run.log")
    r = RealRunner(logger=logger)
    r.run([sys.executable, "-c", "print('visible-output')"])
    r.run([sys.executable, "-c", "print('hidden' + '-secret')"], log_output=False)
    for h in logger.handlers:
        h.flush()
    text = (tmp_path / "run.log").read_text(encoding="utf-8")
    assert "visible-output" in text and "hidden-secret" not in text and "-c" in text


# I8: a second display mustn't reuse the first one's backup folder
def test_backup_refuses_another_displays_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "SECTOR", 1)
    ctx = make_ctx(tmp_path, FakeRunner())
    out = tmp_path / "bk"
    e = FakeEdl(); e._tmp = tmp_path
    bk.backup(ctx, out, e)
    other = bytearray(GPT.read_bytes())
    i = other.find(b"EFI PART")
    other[i + 56:i + 72] = b"\x33" * 16
    e2 = FakeEdl(gpt_bytes=bytes(other)); e2._tmp = tmp_path
    with pytest.raises(bk.BackupMismatch):
        bk.backup(ctx, out, e2)


def test_run_steps_says_when_everything_is_done(tmp_path):
    class A(Step):
        name = title = "a"

        def run(self, ctx):
            pass

    ctx = Context(runner=None, ui=FakeUI(), paths=Paths(tmp_path), state={"progress_id": "d"})
    run_steps([A()], ctx)
    run_steps([A()], ctx)
    assert any("already done" in l for l in ctx.ui.lines)


# I9: allow-list, case-insensitive
@pytest.mark.parametrize("args", [["flashing", "lock_critical"], ["flashing", "LOCK"], ["-w"], ["update", "x.zip"],
                                  ["flashall"], ["boot", "x.img"], ["flash", "userdata", "img"],
                                  ["FLASH", "partition", "x"], ["oem", "device-info"], ["set_active", "b"]])
def test_assert_safe_is_an_allow_list(args):
    with pytest.raises(flash.ForbiddenCommand):
        flash.assert_safe(args)


# I10: dropout retry must stay on the same display and survive timeouts
def test_flash_retry_refuses_a_different_display(tmp_path, monkeypatch):
    serials = iter(["S1", "S2"])
    monkeypatch.setattr(flash, "wait_for_mode", lambda target, ctx, **kw: next(serials))
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: {n: tmp_path / n for n in flash.FLASH_SET})
    runner = converted_runner()
    runner.responses[("-s", "S1", "flash", "boot_a")] = Result(1, "FAILED (no link)")
    with pytest.raises(flash.FlashRefused):
        flash.FlashStep().run(make_ctx(tmp_path, runner, unlocked_now=True))


def test_flash_retry_survives_a_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(flash, "wait_for_mode", lambda target, ctx, **kw: "S1")
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: {n: tmp_path / n for n in flash.FLASH_SET})
    runner = converted_runner()
    runner.responses[("-s", "S1", "flash", "boot_a")] = [subprocess.TimeoutExpired("fastboot", 600), Result(0, "OKAY")]
    flash.FlashStep().run(make_ctx(tmp_path, runner, unlocked_now=True))
    assert len([c for c in runner.calls if c[3:5] == ["flash", "boot_a"]]) == 2


# I11: wait for the *new* boot after a reboot
def test_reboot_waits_for_a_new_boot_id(tmp_path, monkeypatch):
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    runner = FakeRunner({
        ("-s", "S1", "shell", "cat", "/proc/sys/kernel/random/boot_id"):
            [Result(0, "old\n"), Result(0, "old\n"), Result(0, "new\n")],
        ("-s", "S1", "shell", "getprop", "sys.boot_completed"): Result(0, "1\n"),
    })
    system.reboot_and_wait(make_ctx(tmp_path, runner))
    reads = [c for c in runner.calls if c[-1] == "/proc/sys/kernel/random/boot_id"]
    assert len(reads) == 3 and ["reboot"] in [c[3:] for c in runner.calls]


# I12: edl gets one partition per call, so commas in paths can't split
def test_edl_reads_one_partition_per_call(tmp_path, monkeypatch):
    from lhk import edl as edl_mod
    e = edl_mod.Edl.__new__(edl_mod.Edl)
    calls = []
    e._run = lambda *a, **kw: calls.append(a)
    e.read(["boot_a", "boot_b"], tmp_path / "Smith, John")
    assert calls == [("r", "boot_a", str(tmp_path / "Smith, John" / "boot_a.bin")),
                     ("r", "boot_b", str(tmp_path / "Smith, John" / "boot_b.bin"))]


# I13: no retired runner labels in the release matrix
def test_release_matrix_has_no_retired_runners():
    text = (Path(__file__).parent.parent / ".github" / "workflows" / "release.yml").read_text()
    assert "macos-13" not in text


# I14: restore asks first, and clears userdata so stock starts clean
def test_restore_requires_typed_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "SECTOR", 1)
    out = tmp_path / "bk"
    e = FakeEdl(); e._tmp = tmp_path
    bk.backup(make_ctx(tmp_path, FakeRunner()), out, e)
    e2 = FakeEdl(); e2._tmp = tmp_path
    with pytest.raises(bk.BackupMismatch):
        bk.restore(make_ctx(tmp_path, FakeRunner(), ui=FakeUI(answers=["yes"])), out, e2)
    assert not e2.written


def test_restore_erases_userdata(tmp_path, monkeypatch):
    monkeypatch.setattr(bk, "SECTOR", 1)
    out = tmp_path / "bk"
    e = FakeEdl(); e._tmp = tmp_path
    bk.backup(make_ctx(tmp_path, FakeRunner()), out, e)
    e2 = FakeEdl(); e2._tmp = tmp_path
    bk.restore(make_ctx(tmp_path, FakeRunner(), ui=FakeUI(answers=["restore"])), out, e2)
    assert ("e", "userdata") in e2.calls


def test_flashed_message_says_restarts_are_normal(tmp_path, monkeypatch):
    # Run 3: the new system restarts on its own while it sets itself up.
    monkeypatch.setattr(flash, "wait_for_mode", lambda target, ctx, **kw: "S1")
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: {n: tmp_path / n for n in flash.FLASH_SET})
    ctx = make_ctx(tmp_path, converted_runner(), unlocked_now=True)
    flash.FlashStep().run(ctx)
    msg = next(l for l in ctx.ui.lines if l.startswith("Flashed."))
    assert "restarts" in msg and "normal" in msg
