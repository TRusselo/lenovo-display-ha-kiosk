"""Run 2 and 3: a restored display stays unlocked, and unlocked stock hangs on
Google Assistant's loading dots. Restore now locks it again, but only when the
backup is provably stock: locking non-stock firmware can leave a display that
won't start."""
import hashlib
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from lhk import relock
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI


def vbmeta(alg=5, flags=0, magic=b"AVB0"):
    d = bytearray(65536)
    d[0:4] = magic
    d[28:32] = struct.pack(">I", alg)
    d[120:124] = struct.pack(">I", flags)
    return bytes(d)


def make_backup(tmp_path, boot=b"stock boot", vb_a=None, vb_b=None):
    parts = tmp_path / "bk" / "partitions"
    parts.mkdir(parents=True)
    for slot in "ab":
        (parts / f"boot_{slot}.bin").write_bytes(boot)
    (parts / "vbmeta_a.bin").write_bytes(vb_a or vbmeta())
    (parts / "vbmeta_b.bin").write_bytes(vb_b or vbmeta())
    return tmp_path / "bk"


def test_stock_backup_passes(tmp_path):
    assert relock.stock_problems(make_backup(tmp_path)) == []


def test_backup_holding_the_userdebug_boot_is_refused(tmp_path, monkeypatch):
    # A backup made with a new --name on an already-converted display.
    monkeypatch.setattr(relock, "USERDEBUG_BOOT_SHA256", hashlib.sha256(b"userdebug").hexdigest())
    problems = relock.stock_problems(make_backup(tmp_path, boot=b"userdebug"))
    assert any("boot_a" in p for p in problems)


def test_vbmeta_with_verification_flags_is_refused(tmp_path):
    # The userdebug vbmeta has flags=1 (hashtree off); locked, that won't start.
    problems = relock.stock_problems(make_backup(tmp_path, vb_b=vbmeta(flags=1)))
    assert any("vbmeta_b" in p for p in problems)


def test_unsigned_or_missing_vbmeta_is_refused(tmp_path):
    assert relock.stock_problems(make_backup(tmp_path / "u", vb_a=vbmeta(alg=0)))
    assert relock.stock_problems(make_backup(tmp_path / "m", vb_a=vbmeta(magic=b"\0\0\0\0")))
    bk = make_backup(tmp_path / "x")
    (bk / "partitions" / "vbmeta_b.bin").unlink()
    assert relock.stock_problems(bk)


def make_ctx(tmp_path, runner, answers):
    c = Context(runner=runner, ui=FakeUI(answers=answers), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")))
    return c


@pytest.fixture
def in_fastboot(monkeypatch):
    monkeypatch.setattr(relock, "wait_for_mode", lambda mode, ctx, **kw: "S1")
    states = []
    monkeypatch.setattr(relock, "check_fastboot_identity",
                        lambda ctx, serial: SimpleNamespace(avb_locked=states.pop(0)))
    return states


def oem_calls(runner):
    return [c for c in runner.calls if "oem" in c]


def test_relock_locks_after_typed_word_then_restarts(tmp_path, in_fastboot):
    in_fastboot.extend([False, True])
    runner = FakeRunner()
    ctx = make_ctx(tmp_path, runner, ["lock"])
    relock.relock(ctx, make_backup(tmp_path))
    assert [c[1:] for c in oem_calls(runner)] == [["-s", "S1", "oem", "at-lock-vboot"]]
    assert runner.calls[-1][1:] == ["-s", "S1", "reboot"]
    assert any("Locked" in l for l in ctx.ui.lines)


def test_relock_enter_leaves_it_unlocked_and_says_what_that_means(tmp_path, in_fastboot):
    in_fastboot.extend([False])
    runner = FakeRunner()
    ctx = make_ctx(tmp_path, runner, [""])
    relock.relock(ctx, make_backup(tmp_path))
    assert oem_calls(runner) == []
    assert any("loading dots" in l for l in ctx.ui.lines)


def test_relock_refuses_non_stock_backup_without_any_oem_command(tmp_path, in_fastboot):
    runner = FakeRunner()
    ctx = make_ctx(tmp_path, runner, ["lock"])
    relock.relock(ctx, make_backup(tmp_path, vb_a=vbmeta(flags=1)))
    assert oem_calls(runner) == []
    assert any("won't lock" in l for l in ctx.ui.lines)


def test_relock_fails_loudly_if_the_lock_does_not_take(tmp_path, in_fastboot):
    in_fastboot.extend([False, False])
    ctx = make_ctx(tmp_path, FakeRunner(), ["lock"])
    with pytest.raises(relock.RelockFailed):
        relock.relock(ctx, make_backup(tmp_path))


def test_already_locked_just_restarts(tmp_path, in_fastboot):
    in_fastboot.extend([True])
    runner = FakeRunner()
    relock.relock(make_ctx(tmp_path, runner, []), make_backup(tmp_path))
    assert oem_calls(runner) == [] and runner.calls[-1][1:] == ["-s", "S1", "reboot"]


def test_lock_prompt_names_the_display(tmp_path, in_fastboot):
    # Several displays; the power is cycled between EDL and fastboot.
    in_fastboot.extend([False])
    ctx = make_ctx(tmp_path, FakeRunner(), [""])
    relock.relock(ctx, make_backup(tmp_path))
    assert any(l.startswith("[ask]") and "S1" in l for l in ctx.ui.lines)


def test_relock_reports_whether_it_locked(tmp_path, in_fastboot):
    in_fastboot.extend([False, True])
    assert relock.relock(make_ctx(tmp_path, FakeRunner(), ["lock"]), make_backup(tmp_path / "a")) is True
    in_fastboot.extend([False])
    assert relock.relock(make_ctx(tmp_path, FakeRunner(), [""]), make_backup(tmp_path / "b")) is False


class ReadEdl:
    """Hands back the display's boot and vbmeta images."""

    def __init__(self, images):
        self.images = images
        self.reads = []

    def read(self, names, dest_dir):
        for n in names:
            self.reads.append(n)
            (Path(dest_dir) / f"{n}.bin").write_bytes(self.images[n])


def _images(boot=b"stock boot", vb=None):
    return {"boot_a": boot, "boot_b": boot, "vbmeta_a": vb or vbmeta(), "vbmeta_b": vb or vbmeta()}


def test_lock_only_checks_what_is_on_the_display_then_locks(tmp_path, in_fastboot, monkeypatch):
    in_fastboot.extend([False, True])
    monkeypatch.setattr(relock, "wait_for_edl", lambda ctx: None)
    runner = FakeRunner()
    edl = ReadEdl(_images())
    assert relock.lock_only(make_ctx(tmp_path, runner, ["lock"]), edl) is True
    assert sorted(edl.reads) == ["boot_a", "boot_b", "vbmeta_a", "vbmeta_b"]
    assert oem_calls(runner)


def test_lock_only_refuses_a_converted_display(tmp_path, in_fastboot, monkeypatch):
    # A stock backup on disk proves nothing about the display: read the display.
    monkeypatch.setattr(relock, "wait_for_edl", lambda ctx: None)
    runner = FakeRunner()
    ctx = make_ctx(tmp_path, runner, ["lock"])
    assert relock.lock_only(ctx, ReadEdl(_images(vb=vbmeta(flags=1)))) is False
    assert oem_calls(runner) == []
    assert any("converted system" in l and "Nothing was changed" in l for l in ctx.ui.lines)


def test_left_unlocked_points_to_lhk_lock(tmp_path, in_fastboot):
    in_fastboot.extend([False])
    ctx = make_ctx(tmp_path, FakeRunner(), [""])
    relock.relock(ctx, make_backup(tmp_path))
    assert any("lhk lock" in l for l in ctx.ui.lines)


def test_mistyped_lock_asks_again_instead_of_leaving_it_unlocked(tmp_path, in_fastboot):
    in_fastboot.extend([False, True])
    runner = FakeRunner()
    assert relock.relock(make_ctx(tmp_path, runner, ["lcok", "lock"]), make_backup(tmp_path)) is True
    assert oem_calls(runner)


def test_lock_refusal_on_a_converted_display_says_so_and_how_to_restart(tmp_path, in_fastboot, monkeypatch):
    # Run 6: the refusal talked about stock's loading dots and left the display in EDL unexplained.
    monkeypatch.setattr(relock, "wait_for_edl", lambda ctx: None)
    monkeypatch.setattr(relock, "USERDEBUG_BOOT_SHA256", hashlib.sha256(b"userdebug").hexdigest())
    ctx = make_ctx(tmp_path, FakeRunner(), [])
    relock.lock_only(ctx, ReadEdl(_images(boot=b"userdebug", vb=vbmeta(flags=1))))
    text = " ".join(ctx.ui.lines)
    assert "converted system" in text and "unplug" in text.lower() and "loading dots" not in text


def test_refused_restore_lock_says_how_to_restart(tmp_path, in_fastboot):
    ctx = make_ctx(tmp_path, FakeRunner(), [])
    relock.relock(ctx, make_backup(tmp_path, vb_a=vbmeta(flags=1)))
    assert "unplug" in " ".join(ctx.ui.lines).lower()


def test_left_unlocked_restarts_the_display_out_of_fastboot(tmp_path, in_fastboot):
    in_fastboot.extend([False])
    runner = FakeRunner()
    ctx = make_ctx(tmp_path, runner, [""])
    relock.relock(ctx, make_backup(tmp_path))
    assert runner.calls[-1][1:] == ["-s", "S1", "reboot"] and oem_calls(runner) == []
