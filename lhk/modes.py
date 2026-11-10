"""Which mode is the display in? The screen stays blank in EDL and fastboot,
so the tool shows this instead. The user lets go of the buttons 3 to 5 seconds
after plugging in (held for about 15 seconds, they reset the display). A
display that starts normally doesn't appear on USB at all, so after a while
with nothing the tool points at what the user can see: the Lenovo logo."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
import time
from enum import Enum

from lhk.ui import choose
from lhk import doc
from lhk.runner import CommandFailed

EDL_USB_ID = (0x05C6, 0x9008)
POLL_SECONDS = 0.25
HINT_AFTER = 20
NOTHING_HINT = ("Nothing yet. If the screen shows the Lenovo logo, the display is starting normally: "
                "the buttons weren't held as it powered on. Unplug its power and try again.")
RETRY_ASK = "Press Enter to try again, or type stop: "


class Mode(Enum):
    NONE = "none"
    EDL = "EDL"
    FASTBOOT = "FASTBOOT"
    ADB = "ADB"


class MultipleDevices(Exception):
    pass


class ModeTimeout(Exception):
    pass


class ToolBroken(Exception):
    pass


class UsbNoPermission(Exception):
    pass


NO_PERMISSION = ("The display is connected, but this computer account isn't allowed to use it. Do the "
                 "one-time USB access setup in " + doc("docs/LINUX.md", "step 4") + ", then unplug the "
                 "display's USB and plug it back in, and run the same command again.")


def usb_access(dev_id: str) -> bool:
    """Can this account open the USB device? Only Linux has per-device permissions."""
    if not sys.platform.startswith("linux"):
        return True
    bus, addr = dev_id.removeprefix("usb:").split("-")
    return os.access(f"/dev/bus/usb/{int(bus):03d}/{int(addr):03d}", os.R_OK | os.W_OK)


class UsbBackendMissing(Exception):
    """pyusb has no libusb backend. The message says how to fix it on this OS."""


def _usb_backend():
    """libusb from the libusb-package wheel (bundled for Windows and macOS), else the system's."""
    try:
        import libusb_package
        return libusb_package.get_libusb1_backend()
    except Exception:
        return None


def usb_scan_edl() -> list[str]:
    try:
        import usb.core
        devs = list(usb.core.find(find_all=True, idVendor=EDL_USB_ID[0], idProduct=EDL_USB_ID[1],
                                  backend=_usb_backend()))
    except Exception as e:  # usb.core.NoBackendError and import errors
        if type(e).__name__ == "NoBackendError" or isinstance(e, ImportError):
            raise UsbBackendMissing(
                "EDL detection needs libusb, which couldn't be loaded. Linux: install libusb-1.0. "
                "See " + doc("docs/drivers.md") + ".") from e
        raise
    return [f"usb:{d.bus}-{d.address}" for d in devs]


def _safe_scan(scan) -> list[str]:
    # Waiting for fastboot or adb must never fail just because libusb is missing.
    try:
        return scan()
    except UsbBackendMissing:
        return []


def _list(runner, tool, mode, word):
    try:
        out = runner.run([tool, "devices"], check=False, timeout=15).out
    except FileNotFoundError:
        return []  # not downloaded yet: no device can be in that mode
    except (CommandFailed, subprocess.TimeoutExpired):
        return []
    except OSError as e:  # present but can't run: say so instead of showing "no device"
        raise ToolBroken(f"Can't run {Path(tool).name} ({e.strerror}). Delete the tool's cache folder "
                         f"({Path(tool).parent.parent}) and run the same command again.") from e
    found = []
    for line in out.splitlines():
        if "no permissions" in line:
            raise UsbNoPermission(NO_PERMISSION)
        parts = line.split()
        if len(parts) >= 2 and parts[1] == word:
            found.append((mode, parts[0]))
    return found


def detect(runner, tools, usb_scan=usb_scan_edl, strict_usb=False,
           usb_access=usb_access) -> list[tuple[Mode, str]]:
    edl = usb_scan() if strict_usb else _safe_scan(usb_scan)
    # Only an EDL wait opens the device; elsewhere it's just passing through EDL.
    if strict_usb and any(not usb_access(d) for d in edl):
        raise UsbNoPermission(NO_PERMISSION)
    return (_list(runner, tools.adb, Mode.ADB, "device")
            + _list(runner, tools.fastboot, Mode.FASTBOOT, "fastboot")
            + [(Mode.EDL, d) for d in edl])


def wait_for_mode(target: Mode, ctx, *, prompt: str, timeout: float, detect_fn=None,
                  sleep=time.sleep, clock=time.monotonic) -> str:
    if detect_fn is None:
        # Only an EDL wait needs libusb; then a missing backend is reported, not hidden.
        detect_fn = lambda: detect(ctx.runner, ctx.state["tools"],  # noqa: E731
                                   strict_usb=(target == Mode.EDL))
    ui = ctx.ui
    start = clock()
    last_status = None
    wrong_reported = None
    hinted = False
    prompted = False
    # The mode the display is in when the wait starts (EDL right after a
    # backup or restore) is where the user starts from, not a mistake: it
    # only counts as wrong once the display has gone and come back in it.
    starting = None
    while True:
        found = detect_fn()
        if len(found) > 1:
            listed = ", ".join(f"{m.value} {s}" for m, s in found)
            raise MultipleDevices(f"More than one device is connected ({listed}). "
                                  "Unplug everything except the display and try again.")
        mode = found[0][0] if found else Mode.NONE
        if mode == target and not prompted:
            ui.say(f"The display is already in {target.value} mode.")
            return found[0][1]
        if not prompted:
            ui.physical(prompt)
            prompted, start = True, clock()
            starting = mode if mode != Mode.NONE else None
        if starting is not None and mode != starting:
            starting = None
        if mode.value != last_status:
            ui.status(mode.value)
            last_status = mode.value
        if mode == target:
            ui.say("Found it. Let go of the buttons if you're still holding them.")
            return found[0][1]
        if mode not in (Mode.NONE, target, starting) and wrong_reported != mode:
            ui.say(f"The display is in {mode.value} mode, not {target.value}. "
                   "Unplug its power and try again:")
            ui.physical(prompt)
            wrong_reported = mode
        elapsed = clock() - start
        if mode == Mode.NONE and not hinted and elapsed >= HINT_AFTER:
            ui.say(NOTHING_HINT)
            hinted = True
        if elapsed > timeout:
            lead = ("Still nothing. " if mode == Mode.NONE
                    else f"The display still isn't in {target.value} mode. ")
            if choose(ui, lead + RETRY_ASK, "stop"):
                raise ModeTimeout(f"The display didn't reach {target.value} mode.")
            ui.physical(prompt)
            start, hinted, wrong_reported = clock(), False, None
        sleep(POLL_SECONDS)
