"""Flash the userdebug build to slot A. Slot B stays stock as a fallback.

Every fastboot command goes through assert_safe(), an allow-list: getvar,
flashing the five FLASH_SET images, erasing userdata, set_active a, reboot, and
Lenovo's legacy unlock for the original 2018 bootloader.
Anything else (relocking, a partition table, the bootloader chain,
unit-specific data, format, update, boot) is refused.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from lhk.ui import choose
from lhk.downloads import fetch
from lhk.firmware import FLASH_SET, extract
from lhk.identity import check_adb_identity, check_fastboot_identity
from lhk.modes import Mode, detect, wait_for_mode
from lhk.runner import CommandFailed
from lhk.slots import BOOT_CHAIN, RADIO, differing_slots, has_slot_backup
from lhk.steps import Step
from lhk import vbmeta
from lhk.unlock import FASTBOOT_PROMPT

RETRIES = 3
WIPE_WARNING = ("This display's verified boot was already unlocked before this run, so it may already "
                "be converted. Flashing erases its setup: Kiosk Satellite, Wi-Fi and everything on it. "
                "If it runs LANovo or another custom system you mean to replace, type flash: there's no "
                "need to move or rename the backup.")


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
        # Lenovo's own legacy unlock, for the original 2018 bootloader (GitHub issue 7)
        or words == ["oem", "at-unlock-vboot", "default_credential"]
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


def check_slot_firmware(ctx, ident=None) -> None:
    """Refuse to flash when slot A's never-flashed bootloader firmware differs from that of
    slot B, the one running (see lhk/slots.py)."""
    if ident is not None and ident.current_slot.lstrip("_") == "a" and ident.slot_a_successful:
        # Slot A's own firmware is starting the display now: flashing A keeps it. Only when slot A
        # has started: after set_active a on a slot-B display, it reports slot A before it ever has.
        return
    parts = ctx.paths.backup / ctx.state.get("progress_id", "display") / "partitions"
    if not has_slot_backup(parts):
        ctx.ui.say("Note: without a backup, the tool can't check that both slots have the same bootloader "
                   "firmware. On a display that was running from slot B, the new system may not start.")
        return
    differ = differing_slots(parts)
    chain = [p for p in differ if p in BOOT_CHAIN]
    if chain:
        raise FlashRefused(
            "This display runs from slot B, and slot A has a different bootloader (" + ", ".join(chain) + "). "
            "It was probably updated in slot B and left slot A older. Flashing slot A could leave it unable "
            "to start, so nothing was written. Please report this on GitHub, with the output of "
            "`fastboot getvar all`, so a safe fix can be added. Don't move the backup away to get past this "
            "check: lhk restore needs it to put the display back to stock.")
    radio = [p for p in differ if p in RADIO]
    if radio:
        ctx.ui.say("Note: this display runs from slot B, and slot A has older radio firmware (" + ", ".join(radio)
                   + "). Another display like this worked after the conversion, so setup carries on.")


OLD_BOOTLOADER = ("This display still has Lenovo's original 2018 bootloader: it never got Lenovo's final update. "
                  "That bootloader can't read the new system's vbmeta as it is, so setup flashes a copy without "
                  "the two entries it can't read (factory and oem_bootloader). With verified boot unlocked, "
                  "that's all it needs (GitHub issue 6).")


def old_bootloader(ctx) -> bool:
    """Lenovo's original 2018 bootloader (libavb 1.0), told by slot A's aboot in the backup,
    or by the unlock step having needed the legacy command."""
    if ctx.state.get("old_bootloader"):
        return True
    aboot = ctx.paths.backup / ctx.state.get("progress_id", "display") / "partitions" / "aboot_a.bin"
    return aboot.is_file() and not vbmeta.supports_avb_1_1(aboot.read_bytes())


def vbmeta_for_old_bootloader(ctx, image: Path) -> Path:
    out = ctx.paths.cache / "images" / "vbmeta_a-libavb-1.0.img"
    out.parent.mkdir(parents=True, exist_ok=True)
    with ctx.ui.busy("Preparing a vbmeta for the 2018 bootloader"):
        out.write_bytes(vbmeta.for_old_bootloader(image.read_bytes()))
    return out


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
        ident = check_fastboot_identity(ctx, serial)
        if ident.avb_locked is not False:
            raise FlashRefused("Verified boot is still locked; run the unlock step first.")
        check_slot_firmware(ctx, ident)
        if not ctx.state.get("unlocked_now") and _fresh_stock_backup(ctx):
            ctx.ui.say("Verified boot was already unlocked (a restore left it that way, or it was unlocked "
                       "by hand). The backup just made shows this display is on stock, so there's nothing "
                       "on it to lose.")
        elif not ctx.state.get("unlocked_now"):
            ctx.ui.say("WARNING: " + WIPE_WARNING)
            if not choose(ctx.ui, "Type flash to flash it anyway, or press Enter to stop: ", "flash"):
                raise FlashRefused("Stopped before flashing. Nothing was changed.")
        if old_bootloader(ctx):
            ctx.ui.say("Note: " + OLD_BOOTLOADER)
            images = dict(images, vbmeta_a=vbmeta_for_old_bootloader(ctx, images["vbmeta_a"]))
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
