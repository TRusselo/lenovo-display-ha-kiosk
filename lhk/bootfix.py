"""Boot fixes: light sensor after boot, and the hardware volume buttons.

Installed as a separate init file in /system/etc/init, which init loads on
its own. /init.rc is never touched: editing it soft-bricked a display. The
two scripts are labelled dumpstate_exec, so init starts them in the
dumpstate domain (init may not switch to su).
"""
from __future__ import annotations

import time
from pathlib import Path

from lhk.ui import choose
from lhk import doc
from lhk.downloads import _repo_file
from lhk.steps import Step
from lhk.system import adb, ensure_root_rw, reboot_and_wait, shell, wait_booted

LABEL = "u:object_r:dumpstate_exec:s0"
# (asset, path on the display, mode, label or None for restorecon)
FILES = [
    ("assets/bootfix/ks-boot-fix.sh", "/system/bin/ks-boot-fix.sh", "755", LABEL),
    ("assets/bootfix/ks-volume-keys.sh", "/system/bin/ks-volume-keys.sh", "755", LABEL),
    ("ks-volkeys.jar", "/system/framework/ks-volkeys.jar", "644", None),
    ("assets/bootfix/ks-boot-fix.rc", "/system/etc/init/ks-boot-fix.rc", "644", None),
]


class BootFixFailed(Exception):
    pass


def _jar(ctx) -> Path:
    for p in (ctx.state.get("volkeys_jar"), _repo_file("ks-volkeys.jar"),
              _repo_file("assets/bootfix/volkeys/build/ks-volkeys.jar")):
        if p and Path(p).exists():
            return Path(p)
    raise BootFixFailed("ks-volkeys.jar is missing. It comes with each release; when running from "
                        "source, build it (" + doc("docs/PYTHON.md") + ") or download it from the "
                        "release page.")


def _volume_problems(ctx) -> list[str]:
    problems = []
    if shell(ctx, "getprop", "init.svc.ks_volume_keys", check=False).strip() != "running":
        problems.append("the volume button service isn't running")
    ps = shell(ctx, "ps", "-A", "-o", "LABEL,ARGS", check=False)
    if not any("ks.VolKeys" in l and "u:r:dumpstate:s0" in l for l in ps.splitlines()):
        problems.append("the volume button helper isn't running in the expected security domain")
    return problems


def verify(ctx, wait: float = 90) -> list[str]:
    # init starts the helpers on sys.boot_completed=1, the moment the tool sees
    # the display as booted, so everything gets up to `wait` seconds to appear.
    end = time.monotonic() + wait
    while (problems := _volume_problems(ctx)) and time.monotonic() < end:
        time.sleep(3)
    while "kiosk_satellite.LightSensor" not in shell(ctx, "dumpsys", "sensorservice", check=False):
        if time.monotonic() >= end:
            problems.append("Kiosk Satellite isn't reading the light sensor")
            break
        time.sleep(5)
    home = shell(ctx, "cmd", "package", "resolve-activity", "--brief", "-c", "android.intent.category.HOME",
                 "-a", "android.intent.action.MAIN", check=False).strip().splitlines()
    if not home or not home[-1].startswith("me.jxl.kiosk_satellite/"):
        problems.append("Kiosk Satellite isn't the home screen (its 'Act as the home screen' setting is off), "
                        "so the display starts on Google Assistant's loading dots")
    if "nav_input_consumer" in shell(ctx, "dumpsys", "input", check=False):
        problems.append("the hidden navigation bar layer is still eating taps "
                        "(Kiosk Satellite's 'Hide navigation bar' is on)")
    return problems


def _volume(ctx) -> int:
    v = shell(ctx, "settings", "get", "system", "volume_music_speaker", check=False).strip()
    return int(v) if v.isdigit() else -1


def _pressed(ctx, before: int, sign: int, wait: float) -> bool:
    end = time.monotonic() + wait
    while (_volume(ctx) - before) * sign < 3:
        if time.monotonic() > end:
            return False
        time.sleep(1)
    return True


def check_buttons(ctx, wait: float = 60) -> None:
    ctx.ui.alert("NOT DONE YET! THIS TOOL NEEDS YOU TO PRESS THE VOLUME BUTTONS ON THE DISPLAY.")
    for name, sign in (("VOLUME UP", 1), ("VOLUME DOWN", -1)):
        while True:
            before = _volume(ctx)
            ctx.ui.say(f"Press {name} on the display once.")
            if _pressed(ctx, before, sign, wait):
                break
            if choose(ctx.ui, f"The volume didn't change after {name}. Press Enter to try again, "
                              "or type skip: ", "skip"):
                ctx.ui.say("Button check skipped. The volume fix is installed and running; if the "
                           "buttons don't change the volume later, see "
                           + doc("devices/amber/README.md", "step 14") + ".")
                return
    ctx.ui.say("Volume buttons work.")


class BootFixStep(Step):
    name = "bootfix"
    title = "Install the light sensor and volume button fixes"

    def done(self, ctx) -> bool:
        listing = shell(ctx, "ls", *[remote for _, remote, _, _ in FILES], check=False)
        return all(remote in listing for _, remote, _, _ in FILES) and verify(ctx, wait=0) == []

    def run(self, ctx) -> None:
        ensure_root_rw(ctx)
        for asset, remote, mode, label in FILES:
            if remote == "/init.rc":
                raise BootFixFailed("refusing to write /init.rc")
            local = _jar(ctx) if asset == "ks-volkeys.jar" else _repo_file(asset)
            adb(ctx, "push", str(local), remote)
            shell(ctx, "chmod", mode, remote)
            if label:
                shell(ctx, "chcon", label, remote)
            else:
                shell(ctx, "restorecon", remote)
        ctx.ui.say("Restarting the display to check the boot fixes. This takes about a minute.")
        reboot_and_wait(ctx, why="the display to restart with the boot fixes")
        ensure_root_rw(ctx)
        problems = verify(ctx)
        if problems:
            raise BootFixFailed("After the reboot: " + "; ".join(problems) + ".")
        check_buttons(ctx)
