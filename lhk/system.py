"""Set up the freshly flashed system: root, Wi-Fi and time zone (on screen),
de-Google, mic gain."""
from __future__ import annotations

import hashlib
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

from lhk.downloads import _repo_file, fetch
from lhk.identity import check_adb_identity
from lhk.mixer import patch_mixer
from lhk.modes import Mode, MultipleDevices, _list, detect
from lhk.steps import Step
from lhk.ui import choose

MIXER_PATH = "/system/etc/mixer_paths_openq624_fep.xml"
CAST = "com.google.android.apps.mediashell"
# Run 7 (2026-11-15) and a Mac tester: after the flash the display can stay off USB
# for 9 minutes or more, until its USB cable is unplugged and plugged back in.
REPLUG = ("The display hasn't shown up over USB. Unplug the USB cable from the display, count to 3, and plug "
          "it back in. Leave the power plugged in. The four dots can keep spinning even when it's ready.")
OTHER_PORT = ("Still nothing? Try a USB-A port on the computer, with a USB-A to USB-C cable (through a hub "
              "or adapter if the computer has no USB-A ports).")
NO_ADB = ("Stopped waiting for the display to show up over USB. Unplug its USB cable, count to 3, plug it back "
          "in, and run the same command again. If it never shows up, try another cable (a USB-A to USB-C "
          "one), or flip the plug at the display end.")
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


def adb(ctx, *args, check=True, timeout=120, log_output=True, hide=()):
    if hide:
        return ctx.runner.run([ctx.state["tools"].adb, "-s", serial(ctx), *args],
                              check=check, timeout=timeout, log_output=log_output, hide=hide)
    return ctx.runner.run([ctx.state["tools"].adb, "-s", serial(ctx), *args],
                          check=check, timeout=timeout, log_output=log_output)


def shell(ctx, *args, check=True, timeout=120) -> str:
    return adb(ctx, "shell", *args, check=check, timeout=timeout).out


def _booted(ctx) -> bool:
    try:
        return shell(ctx, "getprop", "sys.boot_completed", check=False, timeout=10).strip() == "1"
    except Exception:
        return False


FELL_BACK = ("The new system didn't start, and the display went back to its old one: adb on the display is "
             "asking to be allowed, which only the old system does. Nothing more was changed. Please report "
             "this on GitHub with the log. To put the stock software back fully, run lhk restore with the "
             "backup.")


def _wait_usb(ctx, timeout) -> None:
    """Like adb wait-for-device, but stops when this display shows up unauthorized. The
    flashed userdebug system never asks to allow adb, so that means the bootloader gave up on
    slot A and started the old system on slot B (GitHub issue 6)."""
    me = ctx.state.get("serial")
    end = time.monotonic() + timeout
    while True:
        if me and me in [s for _, s in _list(ctx.runner, ctx.state["tools"].adb, Mode.ADB, "unauthorized")]:
            raise SetupFailed(FELL_BACK)
        if [s for _, s in _list(ctx.runner, ctx.state["tools"].adb, Mode.ADB, "device") if not me or s == me]:
            return
        if time.monotonic() > end:
            raise subprocess.TimeoutExpired("adb wait-for-device", timeout)
        time.sleep(3)


def wait_booted(ctx, timeout=300, why="the display to start", first_start=False) -> None:
    """Wait until Android has finished starting. Silent when it already has. first_start:
    right after flashing, when the display can go back to its old system instead."""
    if _booted(ctx):
        return
    tries = 0
    while True:
        with ctx.ui.busy("Waiting for the display on USB") as job:
            try:
                if first_start:
                    _wait_usb(ctx, timeout)
                else:
                    adb(ctx, "wait-for-device", timeout=timeout)
                break
            except subprocess.TimeoutExpired:
                job.pause("Not on USB yet")
        tries += 1
        ctx.ui.physical(REPLUG if tries == 1 else REPLUG + " " + OTHER_PORT)
        if choose(ctx.ui, "Press Enter to try again, or type stop: ", "stop"):
            raise SetupFailed(NO_ADB)
        ctx.ui.redraw()
    with ctx.ui.busy(f"Waiting for {why}"):
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
        if ctx.state.get("confirm_screen"):
            return False
        try:
            return all(_is_root_rw(ctx))
        except Exception:
            return False

    def run(self, ctx) -> None:
        wait_booted(ctx, why="the new system's first start", first_start=True)
        if ctx.state.get("confirm_screen"):
            # fastboot gave no hardware ID: the screen size is the model check,
            # before the mixer, buttons and light sensor are set up for the 8".
            check_adb_identity(ctx, serial(ctx))
            ctx.state.pop("confirm_screen")
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


def open_things_settings(ctx) -> None:
    shell(ctx, "monkey", "-p", "com.android.iotlauncher", "-c", "android.intent.category.HOME", "1",
          check=False)


def reconnect_wifi(ctx, timeout=15 * 60) -> None:
    """Kiosk Satellite's setup needs the display on Wi-Fi, and it can drop during the
    long steps before it without coming back on its own. Silent when it's connected."""
    if wifi_ip(ctx):
        return
    open_things_settings(ctx)
    ctx.ui.say("The display has lost Wi-Fi. The Android Things settings are now on the display: open "
               "Networks and connect to your Wi-Fi again.")
    end = time.monotonic() + timeout
    while not wifi_ip(ctx):
        if time.monotonic() > end:
            raise SetupFailed("The display didn't get back on Wi-Fi within 15 minutes.")
        time.sleep(3)
    ctx.ui.say("Wi-Fi connected.")


class OpenThingsSettingsStep(Step):
    name = "things-settings"
    title = "Connect Wi-Fi and set the time zone on the display"

    def _ip(self, ctx) -> str:
        return wifi_ip(ctx)

    def done(self, ctx) -> bool:
        return bool(self._ip(ctx))

    def _open(self, ctx) -> None:
        open_things_settings(ctx)

    def run(self, ctx) -> None:
        # Untested models: the Wi-Fi name and password are asked here first. On an SD-X701B no
        # on-screen keyboard showed, and Google's screen covered the settings while this tool
        # waited at its question (GitHub issue 5).
        if ctx.state.get("force_model") and self._join_here(ctx):
            ctx.ui.say("Wi-Fi connected.")
            self._ask_zone(ctx, listed=False)
            return
        self._open(ctx)
        ctx.ui.physical("The Android Things settings are open:\n"
                        "  1. Menu (☰) > System > Date & time: pick your time zone. If yours isn't in the "
                        "list, pick any: you can type the right one here afterwards.\n"
                        "  2. Networks: pick your Wi-Fi and type its password on the on-screen keyboard.\n"
                        "Don't press Check for update or Factory data reset on that page.")
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

    def _join_here(self, ctx) -> bool:
        """Join Wi-Fi from this computer. False when the person presses Enter to use the
        display's settings instead."""
        while not self._ip(ctx):
            ssid = ctx.ui.ask("Type your Wi-Fi name to join it from this computer, or press Enter to "
                              "join on the display instead: ").strip()
            if not ssid:
                return False
            password = ctx.ui.ask("Its password (leave empty for an open network; it isn't saved or "
                                  "logged): ", secret=True)
            join_wifi(ctx, ssid, password)
            end = time.monotonic() + 60
            while not self._ip(ctx) and time.monotonic() < end:
                time.sleep(3)
            if not self._ip(ctx):
                ctx.ui.say(f"The display hasn't joined {ssid} yet. Check the name and password, and that "
                           "it's a 2.4 or 5 GHz WPA network, then try again.")
        return True

    def _ask_zone(self, ctx, listed=True) -> None:
        # The picker is a fixed list: it lacks zones such as America/Edmonton.
        from lhk.tzdata import zone_names
        names = zone_names()
        current = shell(ctx, "getprop", "persist.sys.timezone", check=False).strip()
        which = "If your zone wasn't in the list, type its name" if listed else "Type your time zone's name"
        ask = (f"The display's time zone is {current or 'not set'}. {which} (for example America/Edmonton), "
               "or press Enter to keep it: ")
        while True:
            zone = ctx.ui.ask(ask).strip()
            if not zone:
                return
            if zone in names:
                break
            ctx.ui.say(f"{zone} isn't a time zone name. Names look like America/Edmonton or Europe/Berlin.")
        shell(ctx, "setprop", "persist.sys.timezone", zone)
        ctx.ui.keep(f"Time zone set to {zone}. It takes effect when the display restarts, which this tool "
                   "does near the end. Don't pick a zone in the list again, or it replaces this one.")


JOIN_WIFI = "com.steinwurf.adbjoinwifi/.MainActivity"


def join_wifi(ctx, ssid: str, password: str) -> None:
    """Join Wi-Fi with steinwurf/adb-join-wifi (BSD-3-Clause). It stays installed: Android
    forgets the networks an app added when that app is removed. Never made device owner:
    Kiosk Satellite needs that."""
    apk = fetch("adb-join-wifi", ctx)
    with ctx.ui.busy("Installing adb-join-wifi"):
        adb(ctx, "install", "-r", str(apk), timeout=300)
    # adb joins these into one command line for the display's shell, so each value is quoted.
    args = ["am", "start", "-n", JOIN_WIFI, "-e", "ssid", shlex.quote(ssid)]
    hide = []
    if password:
        args += ["-e", "password_type", "WPA", "-e", "password", shlex.quote(password)]
        hide = [shlex.quote(password), password]
    # check=False: a failure's message would carry the command line, password included.
    try:
        r = adb(ctx, "shell", *args, check=False, hide=hide)
    except subprocess.TimeoutExpired:
        # Its message carries the command line, password included: never pass it on.
        r = None
    if r is None or r.code != 0:
        raise SetupFailed("adb-join-wifi didn't start. Join Wi-Fi on the display instead, or report "
                          "this on GitHub with the log.") from None
    ctx.ui.say(f"Asked the display to join {ssid}. It can take up to a minute.")


IME = "rkr.simplekeyboard.inputmethod/.latin.LatinIME"


class KeyboardStep(Step):
    """Untested models only (--force-model): the Wi-Fi password needs an on-screen keyboard,
    and an SD-X701B had none (GitHub issue 5). Simple Keyboard (Apache-2.0), as the clock
    tool installs. The supported SD-8 has its own, and is left alone."""
    name = "keyboard"
    title = "Add an on-screen keyboard (untested models)"

    def done(self, ctx) -> bool:
        if not ctx.state.get("force_model"):
            return True
        # Not "is there any keyboard": both models run the same flashed system, so that can't
        # tell them apart. As the clock tool does: done once Simple Keyboard is the keyboard.
        return shell(ctx, "settings", "get", "secure", "default_input_method", check=False).strip() == IME

    def run(self, ctx) -> None:
        apk = fetch("simple-keyboard", ctx)
        ctx.ui.say("Untested model: adding Simple Keyboard, so the Wi-Fi password can be typed on the display.")
        with ctx.ui.busy("Installing Simple Keyboard"):
            adb(ctx, "install", "-r", str(apk), timeout=300)
        shell(ctx, "ime", "enable", IME)
        shell(ctx, "ime", "set", IME)
        if not self.done(ctx):
            raise SetupFailed("Simple Keyboard installed, but Android didn't switch to it. Please report "
                              "this on GitHub, with the log.")


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
        # Disabling leaves Cast's data behind: up to 850 MB, enough to leave no room for Kiosk Satellite.
        shell(ctx, "pm", "clear", CAST, check=False)


def _verify_pushed(ctx, expected: str) -> None:
    """Checksum the file on the display. Reading it back over adb isn't byte-exact: on
    Windows the read-back came with CR LF line endings that weren't written (GitHub issue 5)."""
    want = hashlib.md5(expected.encode("utf-8")).hexdigest()
    out = shell(ctx, "md5sum", MIXER_PATH).split()
    got = out[0].lower() if out else "(none)"
    if got != want:
        raise SetupFailed(f"The mixer file on the display doesn't match what was written (MD5 on the "
                          f"display {got}, written {want}).")


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
