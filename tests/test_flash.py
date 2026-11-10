from pathlib import Path

import pytest

from lhk import flash, unlock
from lhk.flash import FlashStep, ForbiddenCommand, assert_safe
from lhk.modes import Mode
from lhk.runner import CommandFailed, Result, Tools
from lhk.steps import Context, Paths
from lhk.unlock import UnlockStep
from tests.fakes import FakeRunner, FakeUI

UNLOCKED = "(bootloader) avb-locked=0\n(bootloader) at-perm-attr-hash=802e273eca8ccaaa69b1623f96cd7e11\n"
LOCKED = UNLOCKED.replace("avb-locked=0", "avb-locked=1")


def fb_responses(vboot):
    return {
        ("-s", "S1", "getvar", "at-vboot-state"): Result(0, vboot),
        ("-s", "S1", "getvar", "product"): Result(0, "product: msm8x53\n"),
        ("-s", "S1", "getvar", "current-slot"): Result(0, "current-slot: a\n"),
        ("-s", "S1", "getvar", "max-download-size"): Result(0, "max-download-size: 0x1fe00000\n"),
    }


def make_ctx(tmp_path, runner):
    c = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    c.state["tools"] = Tools(adb=Path("adb"), fastboot=Path("fastboot"))
    c.state["unlocked_now"] = True     # as right after UnlockStep unlocked it
    return c


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(flash, "wait_for_mode", lambda target, ctx, **kw: "S1")
    monkeypatch.setattr(unlock, "wait_for_mode", lambda target, ctx, **kw: "S1")
    monkeypatch.setattr(unlock, "uv_path", lambda ctx: Path("uvbin"))
    monkeypatch.setattr(unlock, "detect", lambda runner, tools: [])
    monkeypatch.setattr(flash, "detect", lambda runner, tools: [])


def test_unlock_skipped_when_already_unlocked(tmp_path, monkeypatch):
    runner = FakeRunner(fb_responses(UNLOCKED))
    ctx = make_ctx(tmp_path, runner)
    monkeypatch.setattr(unlock, "fetch", lambda id_, ctx: pytest.fail("must not download the unlock tool"))
    UnlockStep().run(ctx)
    assert not any("at_auth_unlock.py" in " ".join(c) for c in runner.calls)


def test_unlock_runs_tool_then_checks(tmp_path, monkeypatch):
    responses = fb_responses(LOCKED)
    responses[("-s", "S1", "getvar", "at-vboot-state")] = [Result(0, LOCKED), Result(0, UNLOCKED)]
    runner = FakeRunner(responses)
    ctx = make_ctx(tmp_path, runner)
    tool = tmp_path / "avb"
    (tool / "creds").mkdir(parents=True)
    (tool / "at_auth_unlock.py").write_text("")
    monkeypatch.setattr(unlock, "fetch", lambda id_, ctx: tool)
    UnlockStep().run(ctx)
    calls = [" ".join(c) for c in runner.calls]
    assert any(c.endswith(f"at_auth_unlock.py -s S1 {tool / 'creds'}") for c in calls)
    # at_auth_unlock.py runs plain `fastboot`, so the downloaded platform-tools must be on PATH
    env = runner.envs[[i for i, c in enumerate(calls) if "at_auth_unlock.py" in c][0]]
    assert str(Path("fastboot").parent) in env["PATH"].split(__import__("os").pathsep)


def test_unlock_fails_if_still_locked(tmp_path, monkeypatch):
    runner = FakeRunner(fb_responses(LOCKED))
    ctx = make_ctx(tmp_path, runner)
    tool = tmp_path / "avb"
    (tool / "creds").mkdir(parents=True)
    (tool / "at_auth_unlock.py").write_text("")
    monkeypatch.setattr(unlock, "fetch", lambda id_, ctx: tool)
    with pytest.raises(unlock.UnlockFailed):
        UnlockStep().run(ctx)


@pytest.mark.parametrize("args", [
    ["flash", "partition", "x.img"],
    ["flash", "devinfo", "x.img"],
    ["flash", "sbl1_a", "x.img"],
    ["flash", "dsp_a", "x.img"],
    ["oem", "at-lock-vboot"],
    ["flashing", "lock"],
    ["format", "userdata"],
    ["erase", "persist"],
])
def test_assert_safe_blocks_lock_and_partition_table(args):
    with pytest.raises(ForbiddenCommand):
        assert_safe(args)


def test_assert_safe_allows_the_plan():
    for args in (["flash", "boot_a", "b.img"], ["erase", "userdata"], ["set_active", "a"], ["reboot"],
                 ["getvar", "at-vboot-state"]):
        assert_safe(args)


def fake_images(tmp_path):
    imgs = {}
    for n in flash.FLASH_SET:
        p = tmp_path / "img" / f"{n}.img"
        p.parent.mkdir(exist_ok=True)
        p.write_bytes(b"x")
        imgs[n] = p
    return imgs


def test_flash_commands_exact(tmp_path, monkeypatch):
    runner = FakeRunner(fb_responses(UNLOCKED))
    ctx = make_ctx(tmp_path, runner)
    imgs = fake_images(tmp_path)
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: imgs)
    FlashStep().run(ctx)
    ops = [c[1:] for c in runner.calls if c[0] == "fastboot" and "getvar" not in c]
    assert ops == ([["-s", "S1", "flash", n, str(imgs[n])] for n in flash.FLASH_SET]
                   + [["-s", "S1", "erase", "userdata"], ["-s", "S1", "set_active", "a"],
                      ["-s", "S1", "reboot"]])


def test_flash_refuses_while_avb_locked(tmp_path, monkeypatch):
    runner = FakeRunner(fb_responses(LOCKED))
    ctx = make_ctx(tmp_path, runner)
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: fake_images(tmp_path))
    with pytest.raises(flash.FlashRefused):
        FlashStep().run(ctx)
    assert not any("flash" in c[3:4] for c in runner.calls if len(c) > 3)


def test_flash_retries_after_dropout(tmp_path, monkeypatch):
    responses = fb_responses(UNLOCKED)
    imgs = fake_images(tmp_path)
    responses[("-s", "S1", "flash", "system_a")] = [Result(1, "FAILED (Write to device failed (no link))"),
                                                   Result(0, "OKAY")]
    runner = FakeRunner(responses)
    ctx = make_ctx(tmp_path, runner)
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: imgs)
    FlashStep().run(ctx)
    system_calls = [c for c in runner.calls if c[3:5] == ["flash", "system_a"]]
    assert len(system_calls) == 2
    assert any("try again" in l.lower() or "lost" in l.lower() for l in ctx.ui.lines)


def test_flash_skipped_when_userdebug_already_booted(tmp_path, monkeypatch):
    runner = FakeRunner({
        ("-s", "S1", "shell", "getprop", "ro.build.fingerprint"):
            Result(0, "Things/iot_msm8x53_som/msm8x53_som:8.1.0/OIMK.211005.001/7795499:userdebug/dev-keys\n"),
        ("-s", "S1", "shell", "wm", "size"): Result(0, "Physical size: 800x1280\n"),
    })
    ctx = make_ctx(tmp_path, runner)
    monkeypatch.setattr(flash, "detect", lambda runner, tools: [(Mode.ADB, "S1")])
    assert FlashStep().done(ctx) is True


def write_backup(tmp_path, differ=()):
    """A finished backup folder where the slot-A/B firmware matches, except `differ`."""
    from lhk.slots import SLOT_FIRMWARE
    parts = tmp_path / "backup" / "display" / "partitions"
    parts.mkdir(parents=True)
    for base in SLOT_FIRMWARE:
        (parts / f"{base}_a.bin").write_bytes(b"same")
        (parts / f"{base}_b.bin").write_bytes(b"older" if base in differ else b"same")
    return parts


def test_slot_firmware_list_is_the_never_flashed_ab_partitions():
    from lhk.slots import SLOT_FIRMWARE
    assert SLOT_FIRMWARE == ["sbl1", "aboot", "tz", "rpm", "keymaster", "cmnlib", "devcfg",
                             "oem_bootloader", "dsp", "modem", "drm", "bluetooth"]


def test_differing_slots_names_mismatches(tmp_path):
    from lhk.slots import differing_slots
    assert differing_slots(write_backup(tmp_path, differ={"aboot", "dsp"})) == ["aboot", "dsp"]


def test_flash_refuses_when_bootloader_slots_differ(tmp_path, monkeypatch):
    write_backup(tmp_path, differ={"sbl1"})
    runner = FakeRunner(fb_responses(UNLOCKED))
    ctx = make_ctx(tmp_path, runner)
    ctx.state["progress_id"] = "display"
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: fake_images(tmp_path))
    with pytest.raises(flash.FlashRefused) as e:
        FlashStep().run(ctx)
    assert "sbl1" in str(e.value)
    assert not [c for c in runner.calls if c[3:4] in (["flash"], ["erase"])]


def test_flash_proceeds_when_slots_match(tmp_path, monkeypatch):
    write_backup(tmp_path)
    runner = FakeRunner(fb_responses(UNLOCKED))
    ctx = make_ctx(tmp_path, runner)
    ctx.state["progress_id"] = "display"
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: fake_images(tmp_path))
    FlashStep().run(ctx)
    assert ["erase", "userdata"] in [c[3:] for c in runner.calls]


def test_flash_warns_when_there_is_no_backup_to_check(tmp_path, monkeypatch):
    runner = FakeRunner(fb_responses(UNLOCKED))
    ctx = make_ctx(tmp_path, runner)
    ctx.state["progress_id"] = "display"
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: fake_images(tmp_path))
    FlashStep().run(ctx)
    assert any("slot" in l.lower() and "backup" in l.lower() for l in ctx.ui.lines)


def test_flash_shows_progress_per_image(tmp_path, monkeypatch):
    ctx = make_ctx(tmp_path, FakeRunner(fb_responses(UNLOCKED)))
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: fake_images(tmp_path))
    FlashStep().run(ctx)
    busy = [l for l in ctx.ui.lines if l.startswith("[busy] Flashing")]
    assert len(busy) == len(flash.FLASH_SET)
    assert busy[0] == f"[busy] Flashing {flash.FLASH_SET[0]} (1 of {len(flash.FLASH_SET)})"


def _stock_backup(tmp_path):
    from tests.test_relock import make_backup
    parts = make_backup(tmp_path / "backup" / "x") / "partitions"
    dest = tmp_path / "backup" / "display" / "partitions"
    dest.mkdir(parents=True)
    for f in parts.iterdir():
        (dest / f.name).write_bytes(f.read_bytes())


def test_unlocked_stock_with_a_fresh_stock_backup_flashes_without_the_wipe_warning(tmp_path, monkeypatch):
    # Run 5: restored stock left unlocked; "may already be converted" was wrong there.
    _stock_backup(tmp_path)
    ctx = make_ctx(tmp_path, FakeRunner(fb_responses(UNLOCKED)))
    ctx.state.update(unlocked_now=False, progress_id="display", backup_this_run=True)
    monkeypatch.setattr(flash, "check_slot_firmware", lambda ctx: None)
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: fake_images(tmp_path))
    FlashStep().run(ctx)
    assert not any("converted" in l for l in ctx.ui.lines)
    assert not any(l.startswith("[ask]") for l in ctx.ui.lines)
    assert any("already unlocked" in l and "stock" in l for l in ctx.ui.lines)


def test_unlocked_without_a_backup_this_run_still_asks(tmp_path, monkeypatch):
    _stock_backup(tmp_path)
    ctx = make_ctx(tmp_path, FakeRunner(fb_responses(UNLOCKED)))
    ctx.state.update(unlocked_now=False, progress_id="display")
    ctx.ui.answers = ["flash"]
    monkeypatch.setattr(flash, "check_slot_firmware", lambda ctx: None)
    monkeypatch.setattr(flash, "prepare_images", lambda ctx: fake_images(tmp_path))
    FlashStep().run(ctx)
    assert any(l.startswith("[ask]") and "flash" in l for l in ctx.ui.lines)
