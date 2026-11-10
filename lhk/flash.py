"""Flash the userdebug build to slot A. Slot B stays stock as a fallback.

Every fastboot command goes through assert_safe(), an allow-list: getvar,
flashing the five FLASH_SET images, erasing userdata, set_active a, reboot.
Anything else (relocking, a partition table, the bootloader chain,
unit-specific data, format, update, boot) is refused.
"""
from __future__ import annotations

import subprocess

from lhk.ui import choose
from lhk.downloads import fetch
from lhk.firmware import FLASH_SET, extract
from lhk.identity import check_adb_identity, check_fastboot_identity
from lhk.modes import Mode, detect, wait_for_mode
from lhk.runner import CommandFailed
from lhk.slots import differing_slots, has_slot_backup
from lhk.steps import Step
from lhk.unlock import FASTBOOT_PROMPT

RETRIES = 3
WIPE_WARNING = ("This display's verified boot was already unlocked before this run, so it may already "
                "be converted. Flashing erases its setup: Kiosk Satellite, Wi-Fi and everything on it.")


class ForbiddenCommand(Exception):
    pass


class FlashRefused(Exception):
    pass


def assert_safe(args: list[str]) -> None:
    words = [str(a) for a in args]
    low = [w.lower() for w in words]
    ok = (
        (len(low) == 2 and low[0] == "getvar")
        or (len(low) == 3 and low[0] == "flash" and words[1] in FLASH_SET)
        or low == ["erase", "userdata"]
        or low == ["set_active", "a"]
        or low == ["reboot"]
    )
    if not ok:
        raise ForbiddenCommand(f"refusing: fastboot {' '.join(words)}")


def _fresh_stock_backup(ctx) -> bool:
    """A backup taken in this run that proves the display is on stock."""
    from lhk.relock import stock_problems
    if not ctx.state.get("backup_this_run"):
        return False
    out = ctx.paths.backup / ctx.state.get("progress_id", "display")
    return out.exists() and stock_problems(out) == []


def prepare_images(ctx) -> dict:
    frw = fetch("oimk-userdebug-frw", ctx) / "FRW.bin"
    with ctx.ui.busy("Extracting the system images"):
        return extract(frw, FLASH_SET, ctx.paths.cache / "images")


def check_slot_firmware(ctx) -> None:
    """Refuse to flash when the two slots' never-flashed firmware differs (see lhk/slots.py)."""
    parts = ctx.paths.backup / ctx.state.get("progress_id", "display") / "partitions"
    if not has_slot_backup(parts):
        ctx.ui.say("Note: without a backup, the tool can't check that both slots have the same bootloader "
                   "firmware. On a display that was running from slot B, the new system may not start.")
        return
    differ = differing_slots(parts)
    if differ:
        raise FlashRefused(
            "This display's two slots have different firmware (" + ", ".join(differ) + "). It was "
            "probably running from slot B after an update that left slot A older. Flashing slot A could "
            "leave it unable to start, so nothing was written. Please report this, with the output of "
            "`fastboot getvar all`, so a safe fix can be added.")


def _fastboot(ctx, serial, *args, timeout=600):
    assert_safe(list(args))
    return ctx.runner.run([ctx.state["tools"].fastboot, "-s", serial, *args], timeout=timeout)


class FlashStep(Step):
    name = "flash"
    title = "Flash the userdebug build to slot A"

    def done(self, ctx) -> bool:
        found = detect(ctx.runner, ctx.state["tools"])
        if len(found) != 1 or found[0][0] != Mode.ADB:
            return False
        serial = found[0][1]
        if ctx.state.get("bound_serial") not in (None, serial):
            return False
        return check_adb_identity(ctx, serial).is_target_build

    def _reconnect(self, ctx, serial) -> str:
        again = wait_for_mode(Mode.FASTBOOT, ctx, prompt=FASTBOOT_PROMPT, timeout=180)
        if again != serial:
            raise FlashRefused(f"A different device ({again}) came back instead of the display "
                               f"being flashed ({serial}). Stopped; nothing more was written.")
        check_fastboot_identity(ctx, again)
        return again

    def run(self, ctx) -> None:
        images = prepare_images(ctx)
        serial = wait_for_mode(Mode.FASTBOOT, ctx, prompt=FASTBOOT_PROMPT, timeout=180)
        if ctx.state.get("bound_serial") not in (None, serial):
            raise FlashRefused(f"This is a different display ({serial}) from the one this progress is "
                               f"for ({ctx.state['bound_serial']}).")
        ctx.state["serial"] = serial
        if check_fastboot_identity(ctx, serial).avb_locked is not False:
            raise FlashRefused("Verified boot is still locked; run the unlock step first.")
        check_slot_firmware(ctx)
        if not ctx.state.get("unlocked_now") and _fresh_stock_backup(ctx):
            ctx.ui.say("Verified boot was already unlocked (a restore left it that way, or it was unlocked "
                       "by hand). The backup just made shows this display is on stock, so there's nothing "
                       "on it to lose.")
        elif not ctx.state.get("unlocked_now"):
            ctx.ui.say("WARNING: " + WIPE_WARNING)
            if not choose(ctx.ui, "Type flash to flash it anyway, or press Enter to stop: ", "flash"):
                raise FlashRefused("Stopped before flashing. Nothing was changed.")
        for i, name in enumerate(FLASH_SET, 1):
            for attempt in range(1, RETRIES + 1):
                try:
                    with ctx.ui.busy(f"Flashing {name} ({i} of {len(FLASH_SET)})"):
                        _fastboot(ctx, serial, "flash", name, images[name])
                    break
                except (CommandFailed, subprocess.TimeoutExpired):
                    if attempt == RETRIES:
                        raise
                    ctx.ui.say(f"Lost the display while writing {name}. Let's try again.")
                    serial = self._reconnect(ctx, serial)
        _fastboot(ctx, serial, "erase", "userdata")
        _fastboot(ctx, serial, "set_active", "a")
        _fastboot(ctx, serial, "reboot")
        ctx.ui.say("Flashed. The display is starting the new system; the first start takes a few minutes. "
                   "It restarts several times on its own while this tool sets it up: that's normal.")
