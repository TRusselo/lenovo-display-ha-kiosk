"""Lock verified boot again after a restore.

Restoring doesn't touch the lock, and stock Android Things won't finish
starting while unlocked: Google Assistant's home screen shows its loading dots
forever (Cast can't load its factory credentials). Locking fixes that.

Locking is only safe on firmware Google signed. A backup made on a display
already running the userdebug build would hold that build, and locked, a
display with it may never start again. So the backup has to prove it is
stock first:
  - vbmeta_a and vbmeta_b are signed AVB images with no verification flags
    (the userdebug vbmeta turns hashtree checking off: flags=1);
  - boot_a and boot_b aren't the userdebug boot image this tool flashes.
"""
from __future__ import annotations

import hashlib
import struct
import tempfile
from pathlib import Path

from lhk.ui import choose
from lhk.identity import check_fastboot_identity
from lhk.modes import Mode, wait_for_mode
from lhk.unlock import FASTBOOT_PROMPT

# boot_a.img from OIMK.211005.001-userdebug-blueberry-FRW (what FlashStep writes).
USERDEBUG_BOOT_SHA256 = "dfc2591d85fc0cdda9a0522a101c6e45369de91c7eb3b55a3538a9af1714d7db"
RESTART_FROM_EDL = "The display is still in EDL mode: unplug its power and plug it back in to restart it."
UNLOCKED_NOTE = ("Until it's locked, stock stays on Google Assistant's loading dots and never "
                 "finishes starting.")


class RelockFailed(Exception):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _vbmeta_problem(path: Path) -> str | None:
    if not path.exists():
        return f"{path.stem} is missing"
    head = path.read_bytes()[:128]
    if len(head) < 128 or head[:4] != b"AVB0":
        return f"{path.stem} isn't a verified boot image"
    if struct.unpack(">I", head[28:32])[0] == 0:
        return f"{path.stem} isn't signed"
    if struct.unpack(">I", head[120:124])[0] != 0:
        return f"{path.stem} turns verification off, so it isn't stock"
    return None


def stock_problems(backup_dir: Path) -> list[str]:
    parts = Path(backup_dir) / "partitions"
    problems = [p for s in "ab" if (p := _vbmeta_problem(parts / f"vbmeta_{s}.bin"))]
    for s in "ab":
        boot = parts / f"boot_{s}.bin"
        if not boot.exists():
            problems.append(f"boot_{s} is missing")
        elif _sha(boot) == USERDEBUG_BOOT_SHA256:
            problems.append(f"boot_{s} is the converted system, not stock")
    return problems


def _fastboot(ctx, serial, *args):
    return ctx.runner.run([ctx.state["tools"].fastboot, "-s", serial, *args], timeout=60)


CHECKED = ["boot_a", "boot_b", "vbmeta_a", "vbmeta_b"]


def wait_for_edl(ctx) -> None:
    from lhk.plan import EDL_PROMPT
    wait_for_mode(Mode.EDL, ctx, prompt=EDL_PROMPT, timeout=180)


def lock_only(ctx, edl) -> bool:
    """Lock a display left unlocked after a restore, without writing it all
    again. A backup on disk proves nothing about what the display holds now,
    so this reads the display's own boot and vbmeta first."""
    wait_for_edl(ctx)
    with tempfile.TemporaryDirectory() as tmp:
        parts = Path(tmp) / "partitions"
        parts.mkdir()
        with ctx.ui.busy("Reading the display's boot images"):
            edl.read(CHECKED, parts)
        problems = stock_problems(Path(tmp))
        if any("converted system" in p or "turns verification off" in p for p in problems):
            ctx.ui.say("This display runs the converted system, not stock, so there's nothing to lock: "
                       "locking it could stop it starting. Nothing was changed. " + RESTART_FROM_EDL)
            return False
        return relock(ctx, Path(tmp), source="what's on this display",
                      done="The display is starting its stock software.")


def relock(ctx, backup_dir: Path, source: str = "this backup",
           done: str = "Restore complete. The display is starting its stock software and will show its "
                       "first-time setup.") -> bool:
    """True when verified boot ends up locked."""
    problems = stock_problems(backup_dir)
    if problems:
        ctx.ui.say(f"This tool won't lock verified boot with {source}: " + "; ".join(problems) +
                   ". Locking firmware that isn't Google's can leave a display that won't start. "
                   + UNLOCKED_NOTE + " " + RESTART_FROM_EDL)
        return False
    ctx.ui.say("Next, verified boot gets locked again, the way the display came from the factory.")
    serial = wait_for_mode(Mode.FASTBOOT, ctx, prompt=FASTBOOT_PROMPT, timeout=180)
    if check_fastboot_identity(ctx, serial).avb_locked is True:
        ctx.ui.say("Verified boot is already locked.")
    else:
        if not choose(ctx.ui, f"Type lock to lock verified boot on display {serial}, or press Enter to "
                              "leave it unlocked: ", "lock"):
            _fastboot(ctx, serial, "reboot")
            ctx.ui.say("Left unlocked, and restarting. " + UNLOCKED_NOTE + " To lock it later without "
                       "restoring again, run: lhk lock")
            return False
        _fastboot(ctx, serial, "oem", "at-lock-vboot")
        if check_fastboot_identity(ctx, serial).avb_locked is not True:
            raise RelockFailed("The display didn't report verified boot as locked. Leave it in fastboot "
                               "mode and check the log folder before trying anything else.")
        ctx.ui.say("Locked.")
    _fastboot(ctx, serial, "reboot")
    ctx.ui.say(done)
    return True
