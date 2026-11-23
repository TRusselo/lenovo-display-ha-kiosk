"""Change a converted display's Wi-Fi (lhk wifi), and give it a fixed address (also asked in setup).

From the clock tool's lck wifi. The display is simpler: adb over USB always works, so a new network is
joined from this computer with adb-join-wifi, as setup does for untested models, and a network it can't
join never cuts this tool off.

The fixed address goes in Android's saved-network file (lhk/staticip.py). Wi-Fi is switched off first and
left a few seconds, so Android has saved its own changes and has nothing left to write over the edit; then
the file is written, with root, as Android keeps it (owner system, 0600, its SELinux label), and the display
restarts, reading it as it starts. Only once the display is back on the fixed address does the tool say so.
The file holds every saved Wi-Fi password: it's never logged, and no copy is left on either side.
"""
from __future__ import annotations

import hashlib
import re
import tempfile
import time
from pathlib import Path

from lhk import staticip
from lhk.downloads import fetch
from lhk.identity import check_adb_identity
from lhk.runner import Tools, platform_id
from lhk.steps import Step
from lhk.system import (SetupFailed, adb, ensure_root_rw, join_wifi, reboot_and_wait, serial, shell,
                        wait_booted, wifi_ip)

STORE = "/data/misc/wifi/WifiConfigStore.xml"
REMOTE = "/data/local/tmp/lhk-wifi.xml"
SETTLE = 12         # Android saves the network list up to 10 s after a change
JOIN_WAIT = 60
ADDRESS_WAIT = 120


def current_ssid(ctx) -> str:
    """The network the display is on now, or ""."""
    out = adb(ctx, "shell", "dumpsys", "wifi", check=False, timeout=30, log_output=False).out
    m = re.search(r"mWifiInfo SSID: (.*?), BSSID", out)
    name = m.group(1) if m else ""
    return "" if name in ("<unknown ssid>", "") else name


def _store(ctx) -> str:
    """The saved-network file, byte for byte: adb pull, never adb shell, whose output comes with CR LF
    on Windows (GitHub issue 5). "" when it can't be read. The copy here is deleted at once."""
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "store.xml"
        adb(ctx, "pull", STORE, str(local), check=False, timeout=60)
        try:
            return local.read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            return ""


def _wait(cond, seconds) -> bool:
    """Every 3 seconds, for about `seconds`: counted in tries, not by the clock."""
    for _ in range(max(1, seconds // 3)):
        if cond():
            return True
        time.sleep(3)
    return cond()


def _wait_for_ssid(ctx) -> str:
    """Wi-Fi takes a few seconds to join after being switched on."""
    found = []
    _wait(lambda: found.append(current_ssid(ctx)) or found[-1], 30)
    return found[-1] if found else ""


def set_address(ctx, static) -> None:
    """The fixed address (a StaticIp) for the network the display is on, or None for automatic again."""
    ensure_root_rw(ctx)
    shell(ctx, "svc", "wifi", "enable", check=False)     # a run stopped while it was off
    ssid = _wait_for_ssid(ctx)
    if not ssid:
        raise SetupFailed("The display isn't on Wi-Fi, so there's no network to give a fixed address. Run "
                          "lhk wifi to join one.")
    try:
        staticip.with_fixed_address(_store(ctx), ssid, static)     # checked before anything changes
    except ValueError as e:
        raise SetupFailed(f"{e} The tool couldn't read the display's saved networks, so nothing changed.") from None
    shell(ctx, "svc", "wifi", "disable")
    try:
        with ctx.ui.busy("Switching Wi-Fi off while the address is saved"):
            time.sleep(SETTLE)
        new = staticip.with_fixed_address(_store(ctx), ssid, static)
        data = new.encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "lhk-wifi.xml"
            local.write_bytes(data)
            adb(ctx, "push", str(local), REMOTE, timeout=60)
        r = adb(ctx, "shell", f"cp {REMOTE} {STORE}",
                f"&& chown 1000:1000 {STORE} && chmod 600 {STORE} && restorecon {STORE}", check=False)
        shell(ctx, "rm", "-f", REMOTE, check=False)
        if r.code != 0:
            raise SetupFailed("The display didn't take the new address: its saved networks weren't changed.")
        got = (shell(ctx, "md5sum", STORE, check=False).split() or ["(none)"])[0].lower()
        if got != hashlib.md5(data).hexdigest():
            raise SetupFailed("The saved networks on the display don't match what was written, so it isn't "
                              "restarted. Run lhk wifi again; if it keeps failing, report it with the log.")
    except BaseException:
        shell(ctx, "svc", "wifi", "enable", check=False)
        raise
    reboot_and_wait(ctx, why="the display to restart with its new address")
    shell(ctx, "svc", "wifi", "enable")
    want = static.address if static is not None else None
    with ctx.ui.busy(f"Waiting for the display to join {ssid}"):
        _wait(lambda: (wifi_ip(ctx) == want) if want else bool(wifi_ip(ctx)), ADDRESS_WAIT)
    got = wifi_ip(ctx)
    if want and got != want:
        raise SetupFailed(f"The display restarted, but its address is {got or 'not set'}, not {want}. Run lhk "
                          "wifi, press Enter to stay on the same network, and type another address, or press "
                          "Enter again for automatic.")
    if not want:
        if not got:
            raise SetupFailed(f"The display restarted but hasn't joined {ssid} yet. Run lhk wifi to try again.")
        ctx.ui.ok(f"The display is on {ssid}, with an automatic address again ({got}).")
        return
    if adb(ctx, "shell", "ping", "-c", "2", "-W", "2", static.gateway, check=False, timeout=30).code != 0:
        ctx.ui.say(f"Note: the display can't reach the gateway {static.gateway}. If Home Assistant doesn't load, "
                   "check the gateway with lhk wifi, or press Enter there for automatic.")
    ctx.ui.ok(f"The display is on {ssid}, at its fixed address {want}.")


class FixedAddressStep(Step):
    name = "fixed-address"
    title = "Give the display a fixed address (optional)"

    def run(self, ctx) -> None:
        static = staticip.ask(ctx.ui)
        if static is None:
            ctx.ui.say("The address stays automatic. To fix it later: lhk wifi.")
            return
        set_address(ctx, static)


def change(ctx) -> bool:
    """lhk wifi: a new network, a fixed address, or both. False when the display couldn't join."""
    fetch(f"platform-tools-{platform_id()}", ctx)
    ctx.state["tools"] = Tools.locate(ctx.paths.cache)
    wait_booted(ctx, why="the display to start")
    if not check_adb_identity(ctx, serial(ctx)).is_target_build:
        raise SetupFailed("This display isn't converted (lhk setup hasn't run on it), so lhk wifi doesn't "
                          "change it. Nothing changed.")
    ensure_root_rw(ctx)
    shell(ctx, "svc", "wifi", "enable", check=False)     # a run stopped while it was off
    now = current_ssid(ctx)
    ctx.ui.say(f"The display is on {now}." if now else "The display isn't on Wi-Fi now.")
    while True:
        stay = f", or press Enter to stay on {now}" if now else ""
        ssid = ctx.ui.ask(f"Wi-Fi name{stay}: ").strip()
        if ssid or now:
            break
    if ssid:
        password = ctx.ui.ask("Its password (leave empty for an open network; it isn't saved or logged): ",
                              secret=True)
        join_wifi(ctx, ssid, password)
        with ctx.ui.busy(f"Waiting for the display to join {ssid}"):
            joined = _wait(lambda: current_ssid(ctx) == ssid and bool(wifi_ip(ctx)), JOIN_WAIT)
        if not joined:
            ctx.ui.say(f"The display didn't join {ssid}. Check the name and password, and that it's a 2.4 or "
                       "5 GHz WPA network, then run lhk wifi again." + (f" It's still on {now}." if now else ""))
            return False
        ctx.ui.ok(f"The display is on {ssid}, at {wifi_ip(ctx)}.")
        ctx.ui.say("Networks it saved before stay saved: if it ever goes back to one of them after a restart, "
                   "run lhk wifi again.")
        now = ssid
    static = staticip.ask(ctx.ui)
    if static is None:
        try:
            fixed = staticip.is_fixed(_store(ctx), now)
        except ValueError:
            fixed = False
        if fixed:
            set_address(ctx, None)
        return True
    set_address(ctx, static)
    return True
