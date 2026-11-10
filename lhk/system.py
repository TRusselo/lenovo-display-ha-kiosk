"""Set up the freshly flashed system: root, Wi-Fi and time zone (on screen),
de-Google, mic gain."""
from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path

from lhk.downloads import _repo_file
from lhk.mixer import patch_mixer
from lhk.modes import Mode, MultipleDevices, detect
from lhk.steps import Step

MIXER_PATH = "/system/etc/mixer_paths_openq624_fep.xml"
NEVER_DISABLE = {"com.google.android.things.sparrow.oem",
                 "com.google.assistant.gallium.client.androidthingshost"}


class UnsafePackage(Exception):
    pass


class SetupFailed(Exception):
    pass


def serial(ctx) -> str:
    """The display's serial; found over adb when a resumed run doesn't know it yet."""
    if not ctx.state.get("serial"):
        found = [s for m, s in detect(ctx.runner, ctx.state["tools"]) if m == Mode.ADB]
        if len(found) > 1:
            raise MultipleDevices(f"More than one Android device is connected ({', '.join(found)}). "
                                  "Unplug everything except the display.")
        if not found:
            raise SetupFailed("The display isn't connected over USB, or hasn't finished starting.")
        bound = ctx.state.get("bound_serial")
        if bound and found[0] != bound:
            raise SetupFailed(f"This is a different display ({found[0]}) from the one this progress is "
                              f"for ({bound}). Connect that one, or use --name for a new display.")
        ctx.state["serial"] = found[0]
    return ctx.state["serial"]


def adb(ctx, *args, check=True, timeout=120, log_output=True):
    return ctx.runner.run([ctx.state["tools"].adb, "-s", serial(ctx), *args],
                          check=check, timeout=timeout, log_output=log_output)


def shell(ctx, *args, check=True, timeout=120) -> str:
    return adb(ctx, "shell", *args, check=check, timeout=timeout).out


def _booted(ctx) -> bool:
    try:
        return shell(ctx, "getprop", "sys.boot_completed", check=False, timeout=10).strip() == "1"
    except Exception:
        return False


def wait_booted(ctx, timeout=300, why="the display to start") -> None:
    """Wait until Android has finished starting. Silent when it already has."""
    if _booted(ctx):
        return
    with ctx.ui.busy(f"Waiting for {why}"):
        adb(ctx, "wait-for-device", timeout=timeout)
        end = time.monotonic() + timeout
        while not _booted(ctx):
            if time.monotonic() > end:
                raise SetupFailed("The display didn't finish starting. Unplug its power, plug it back "
                                  "in, and run again.")
            time.sleep(3)


def _boot_id(ctx) -> str:
    try:
        return shell(ctx, "cat", "/proc/sys/kernel/random/boot_id", check=False, timeout=20).strip()
    except Exception:
        return ""


def reboot_and_wait(ctx, timeout=300, why="the display to restart") -> None:
    """Reboot and wait for the *new* boot: right after `adb reboot`, adb and
    sys.boot_completed can still answer from the old one."""
    before = _boot_id(ctx)
    adb(ctx, "reboot")
    end = time.monotonic() + timeout
    while True:
        now = _boot_id(ctx)
        if now and now != before:
            break
        if time.monotonic() > end:
            raise SetupFailed("The display didn't come back after restarting. Unplug its power, plug it "
                              "back in, and run again.")
        time.sleep(3)
    wait_booted(ctx, timeout, why=why)


def _is_root_rw(ctx) -> tuple[bool, bool]:
    root = shell(ctx, "id", "-u", check=False).strip() == "0"
    rw = root and adb(ctx, "shell", "touch /system/.lhk-rw && rm /system/.lhk-rw", check=False).code == 0
    return root, rw


def ensure_root_rw(ctx) -> None:
    """Root and a writable /system don't survive a reboot or power cut, so every
    step that needs them restores them first. Safe to call any number of times."""
    root, rw = _is_root_rw(ctx)
    if not root:
        adb(ctx, "root", check=False)
        wait_booted(ctx, why="adb to restart with root")
    if not rw:
        adb(ctx, "remount", check=False)
    root, rw = _is_root_rw(ctx)
    if not (root and rw):
        raise SetupFailed("Couldn't get root with a writable /system. Run again from the root step: "
                          "lhk setup --from root")


def degoogle_packages() -> list[str]:
    text = _repo_file("assets/degoogle.txt").read_text(encoding="utf-8")
    return [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]


class RootStep(Step):
    name = "root"
    title = "Get root and make /system writable"

    def done(self, ctx) -> bool:
        try:
            return all(_is_root_rw(ctx))
        except Exception:
            return False

    def run(self, ctx) -> None:
        wait_booted(ctx, why="the new system's first start")
        adb(ctx, "root")
        wait_booted(ctx, why="adb to restart with root")
        out = adb(ctx, "disable-verity", check=False).out
        # The userdebug build ships with verity off; a restart only matters
        # when this actually changed something.
        lines = [l for l in out.lower().splitlines() if l.strip()]
        if not lines or not all("already disabled" in l for l in lines):
            ctx.ui.say("Restarting the display to turn off verity.")
            reboot_and_wait(ctx, why="the display to restart")
        ensure_root_rw(ctx)


GALLIUM = "com.google.assistant.gallium.client.androidthingshost"


def wifi_ip(ctx) -> str:
    """The display's Wi-Fi address, or "" while it has none."""
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)", shell(ctx, "ip", "-4", "addr", "show", "wlan0",
                                                      check=False))
    return m.group(1) if m else ""


class OpenThingsSettingsStep(Step):
    name = "things-settings"
    title = "Connect Wi-Fi and set the time zone on the display"

    def _ip(self, ctx) -> str:
        return wifi_ip(ctx)

    def done(self, ctx) -> bool:
        return bool(self._ip(ctx))

    def _open(self, ctx) -> None:
        shell(ctx, "monkey", "-p", "com.android.iotlauncher", "-c", "android.intent.category.HOME", "1",
              check=False)

    def run(self, ctx) -> None:
        self._open(ctx)
        ctx.ui.say("The Android Things settings are now on the display. On the display:\n"
                   "  1. Menu (☰) > System > Date & time: pick your time zone. If yours isn't in the\n"
                   "     list, pick any; you can type the right one here afterwards.\n"
                   "  2. Networks: pick your Wi-Fi and type its password on the on-screen keyboard.\n"
                   "  Don't press Check for update or Factory data reset on that page.")
        end = time.monotonic() + 15 * 60
        while not self._ip(ctx):
            if time.monotonic() > end:
                raise SetupFailed("The display didn't join Wi-Fi within 15 minutes.")
            # Google Assistant's screen can start just after the settings opened and cover them.
            focus = shell(ctx, "dumpsys", "window", check=False)
            if "mCurrentFocus=" in focus and GALLIUM in focus.split("mCurrentFocus=", 1)[1].split("\n", 1)[0]:
                self._open(ctx)
            time.sleep(3)
        ctx.ui.say("Wi-Fi connected.")
        self._ask_zone(ctx)

    def _ask_zone(self, ctx) -> None:
        # The picker is a fixed list: it lacks zones such as America/Edmonton.
        from lhk.tzdata import zone_names
        names = zone_names()
        current = shell(ctx, "getprop", "persist.sys.timezone", check=False).strip()
        ask = (f"The display's time zone is {current or 'not set'}. If your zone wasn't in the list, type its "
               "name (for example America/Edmonton), or press Enter to keep it: ")
        while True:
            zone = ctx.ui.ask(ask).strip()
            if not zone:
                return
            if zone in names:
                break
            ctx.ui.say(f"{zone} isn't a time zone name. Names look like America/Edmonton or Europe/Berlin.")
        shell(ctx, "setprop", "persist.sys.timezone", zone)
        ctx.ui.say(f"Time zone set to {zone}. It takes effect when the display restarts, which this tool "
                   "does near the end. Don't pick a zone in the list again, or it replaces this one.")


class DegoogleStep(Step):
    name = "degoogle"
    title = "Turn off Google Assistant, Cast and check-ins"

    def _disabled(self, ctx) -> set[str]:
        out = shell(ctx, "pm", "list", "packages", "-d", check=False)
        return {l.split(":", 1)[1].strip() for l in out.splitlines() if l.startswith("package:")}

    def done(self, ctx) -> bool:
        return set(degoogle_packages()) <= self._disabled(ctx)

    def run(self, ctx) -> None:
        ensure_root_rw(ctx)
        pkgs = degoogle_packages()
        unsafe = NEVER_DISABLE & set(pkgs)
        if unsafe:
            raise UnsafePackage(f"refusing to disable {', '.join(sorted(unsafe))}")
        already = self._disabled(ctx)
        for p in pkgs:
            if p not in already:
                shell(ctx, "pm", "disable", p)


def _verify_pushed(ctx, expected: str) -> None:
    if shell(ctx, "cat", MIXER_PATH) != expected:
        raise SetupFailed("The mixer file on the display doesn't match what was written.")


class MixerStep(Step):
    name = "mixer"
    title = "Raise the microphone gain"

    def done(self, ctx) -> bool:
        current = shell(ctx, "cat", MIXER_PATH, check=False)
        try:
            return patch_mixer(current) == current and 'value="12"' in current
        except Exception:
            return False

    def run(self, ctx) -> None:
        ensure_root_rw(ctx)
        current = shell(ctx, "cat", MIXER_PATH)
        if "�" in current:
            raise SetupFailed("The mixer file has bytes this tool can't read safely; not changing it.")
        patched = patch_mixer(current)
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "mixer.xml"
            f.write_bytes(patched.encode("utf-8"))
            adb(ctx, "push", str(f), MIXER_PATH)
        adb(ctx, "shell", "chmod", "644", MIXER_PATH)
        _verify_pushed(ctx, patched)
