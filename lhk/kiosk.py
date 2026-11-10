"""Kiosk Satellite: install the newest release (verified), grant what it needs,
make it device owner, then apply the settings proven on these displays.

The remote admin password is read from the app's own settings file over
root, kept in memory, sent only to the app over the adb tunnel, and never
printed or logged. The settings file itself is never edited: rewriting it
drops its SELinux categories and the app falls back to its setup wizard.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import re
import time
from pathlib import Path

import requests

from lhk.ui import choose
from lhk.apkcert import check as check_cert
from lhk.system import adb, ensure_root_rw, shell, wifi_ip
from lhk.steps import Step

PKG = "me.jxl.kiosk_satellite"
ADMIN = f"{PKG}/.KioskAdminReceiver"
# Signing certificate of jxlarrea's releases (also pinned by echo-dot-assist).
KS_CERT_SHA256 = "2a77134ce11f65ba9d08bed669fdcb742a25633c5665a6135aeca30040b068fc"
RELEASES = "https://api.github.com/repos/jxlarrea/kiosk-satellite/releases/latest"
PREFS = f"/data/data/{PKG}/shared_prefs/FlutterSharedPreferences.xml"
LOCAL_PORT = 23240
SETTINGS = {
    # Hiding a navigation bar these displays don't have makes Android 8 eat taps
    # (kiosk-satellite#1358).
    "screen.hide_navigation_bar": False,
    "audio.mic_gain_db": 24,
    "audio.mic_capture_mode": "voice_communication",
    # "Act as the home screen": off by default and not set by the setup wizard.
    # Without it Android's home is Google Assistant's screen, which can't load
    # here (Cast is off), so every restart showed its loading dots.
    "home.enabled": True,
}
GRANTS = [
    ["appops", "set", PKG, "REQUEST_INSTALL_PACKAGES", "allow"],
    ["appops", "set", PKG, "WRITE_SETTINGS", "allow"],
    ["appops", "set", PKG, "SYSTEM_ALERT_WINDOW", "allow"],
    ["appops", "set", PKG, "GET_USAGE_STATS", "allow"],
    ["dumpsys", "deviceidle", "whitelist", f"+{PKG}"],
    ["cmd", "notification", "allow_listener", f"{PKG}/.MediaSessionListener"],
    ["dpm", "set-active-admin", ADMIN],
]


class KioskError(Exception):
    pass


def _rate_limited(r) -> None:
    headers = getattr(r, "headers", None) or {}
    if getattr(r, "status_code", 200) in (403, 429) and headers.get("X-RateLimit-Remaining") == "0":
        when = ""
        if str(headers.get("X-RateLimit-Reset", "")).isdigit():
            when = " after " + datetime.datetime.fromtimestamp(int(headers["X-RateLimit-Reset"])).strftime("%H:%M")
        raise KioskError("GitHub is limiting lookups from your internet connection right now. It allows "
                         "60 an hour, shared by every device on your network. Run the same command "
                         f"again{when}.")


def latest_release(http) -> tuple[str, str, str]:
    r = http.get(RELEASES, timeout=30)
    _rate_limited(r)
    r.raise_for_status()
    for a in r.json().get("assets", []):
        if "armeabi-v7a" in a["name"] and a["name"].endswith(".apk"):
            digest = a.get("digest") or ""
            if not digest.startswith("sha256:"):
                raise KioskError("The Kiosk Satellite release has no published checksum.")
            return a["browser_download_url"], digest.split(":", 1)[1], a["name"]
    raise KioskError("The newest Kiosk Satellite release has no armeabi-v7a APK.")


def verify_apk(path: Path, sha256: str, cert: str) -> None:
    if hashlib.sha256(Path(path).read_bytes()).hexdigest() != sha256:
        raise KioskError("The Kiosk Satellite download doesn't match its published checksum.")
    check_cert(str(path), cert)


def _http(ctx):
    return ctx.state.get("http") or requests


def fetch_apk(ctx) -> Path:
    """The newest Kiosk Satellite APK, checked. The release lookup is saved in
    the workdir, so a rerun doesn't ask GitHub again."""
    folder = ctx.paths.cache / "kiosk"
    folder.mkdir(parents=True, exist_ok=True)
    saved = folder / "release.json"
    cert = ctx.state.get("ks_cert", KS_CERT_SHA256)
    if saved.exists():
        rel = json.loads(saved.read_text(encoding="utf-8"))
        dest = folder / rel["name"]
        if dest.exists():
            try:
                verify_apk(dest, rel["sha256"], cert)
                return dest
            except Exception:
                dest.unlink(missing_ok=True)
    http = _http(ctx)
    url, sha, name = latest_release(http)
    saved.write_text(json.dumps({"url": url, "sha256": sha, "name": name}), encoding="utf-8")
    dest = folder / name
    with http.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    try:
        verify_apk(dest, sha, cert)
    except Exception:
        dest.unlink(missing_ok=True)
        raise
    return dest


class InstallStep(Step):
    name = "kiosk-install"
    title = "Install Kiosk Satellite"

    def done(self, ctx) -> bool:
        return "package:" in shell(ctx, "pm", "path", PKG, check=False)

    def run(self, ctx) -> None:
        dest = fetch_apk(ctx)
        with ctx.ui.busy("Installing Kiosk Satellite"):
            adb(ctx, "install", "-r", "-g", str(dest), timeout=600)


class GrantsStep(Step):
    name = "kiosk-grants"
    title = "Give Kiosk Satellite its permissions and make it device owner"

    def _is_owner(self, ctx) -> bool:
        out = shell(ctx, "dumpsys", "device_policy", check=False)
        return "Device Owner" in out and PKG in out.split("Device Owner", 1)[1][:400]

    def done(self, ctx) -> bool:
        return self._is_owner(ctx) and "allow" in shell(
            ctx, "appops", "get", PKG, "REQUEST_INSTALL_PACKAGES", check=False)

    def run(self, ctx) -> None:
        for g in GRANTS:
            shell(ctx, *g)
        if not self._is_owner(ctx):
            shell(ctx, "dpm", "set-device-owner", ADMIN)


def _prefs(ctx) -> str:
    # Holds the remote admin password: read with root, never written to the log.
    return adb(ctx, "shell", "cat", PREFS, check=False, log_output=False).out


def _password(xml: str) -> str:
    m = re.search(r'<string name="flutter\.ks\.remote\.password">([^<]*)</string>', xml)
    return m.group(1) if m else ""


def _signed_in(xml: str) -> bool:
    # Set once the user signs in to Home Assistant. The admin password exists
    # earlier, so it can't show that the wizard is finished. Value never read.
    return re.search(r'<string name="flutter\.ks\.ha\.token">[^<]+</string>', xml) is not None


def _current(xml: str) -> dict:
    out = {}
    for key in SETTINGS:
        k = re.escape(f"flutter.ks.{key}")
        m = (re.search(rf'<(?:boolean|long|int) name="{k}" value="([^"]*)"', xml)
             or re.search(rf'<string name="{k}">([^<]*)</string>', xml))
        if m:
            v = m.group(1)
            out[key] = {"true": True, "false": False}.get(v, int(v) if v.lstrip("-").isdigit() else v)
    return out


class SettingsStep(Step):
    name = "kiosk-settings"
    title = "Apply the recommended Kiosk Satellite settings"

    def done(self, ctx) -> bool:
        xml = _prefs(ctx)
        return _signed_in(xml) and _current(xml) == SETTINGS

    def run(self, ctx) -> None:
        # Nothing else opens it: without this the display stays on the Android Things settings.
        shell(ctx, "monkey", "-p", PKG, "-c", "android.intent.category.LAUNCHER", "1", check=False)
        ctx.ui.say("Kiosk Satellite is open on the display. Go through its setup there:\n"
                   "  1. A name for the display, and an admin password for its remote admin.\n"
                   "  2. Your Home Assistant address, and a sign-in or a long-lived access token.\n"
                   "  3. The dashboard to show.\n"
                   "  4. Voice satellite and ESPHome options.\n"
                   "  5. Permissions: already granted by this tool, so just press Finish.\n"
                   "Kiosk Satellite saves your sign-in on page 2, before setup is finished, so this "
                   "tool waits for you.")
        ensure_root_rw(ctx)
        ip = wifi_ip(ctx)
        if ip:
            # The address on a line of its own, so terminals make it clickable.
            ctx.ui.say("You can do these pages in your browser instead, which makes pasting your Home "
                       "Assistant address and token easy. On the display, you can scan a QR code of the "
                       f"token with its camera. Either way works. In a browser:\n  http://{ip}:2324")
        ctx.ui.alert("NOT DONE YET! Kiosk Satellite starts up after you press FINISH on page 5. "
                     "COME BACK HERE AND PRESS ENTER: this tool still has steps to do.")
        while True:
            if choose(ctx.ui, "Press Enter here once you've pressed Finish on the display, "
                              "or type stop: ", "stop"):
                raise KioskError("Stopped before Kiosk Satellite's setup was finished. Finish it on the "
                                 "display, then run the same command again.")
            xml = _prefs(ctx)
            if _password(xml) and _signed_in(xml):
                break
            ctx.ui.say("Kiosk Satellite isn't signed in to Home Assistant yet. Finish its setup on the "
                       "display first.")
        adb(ctx, "forward", f"tcp:{LOCAL_PORT}", "tcp:2324")
        base = f"http://127.0.0.1:{LOCAL_PORT}"
        http = _http(ctx)
        login = http.post(f"{base}/api/login", json={"password": _password(_prefs(ctx))}, timeout=30)
        if login.status_code != 200:
            raise KioskError("Couldn't sign in to Kiosk Satellite's remote admin.")
        token = login.json().get("token") or login.json().get("access_token")
        r = http.patch(f"{base}/api/settings", json=dict(SETTINGS),
                       headers={"Authorization": f"Bearer {token}"}, timeout=30)
        r.raise_for_status()
        rejected = r.json().get("rejected") or []
        if rejected:
            raise KioskError(f"Kiosk Satellite rejected settings: {', '.join(rejected)}")
        if not self.done(ctx):
            raise KioskError("Kiosk Satellite accepted the settings but they didn't stick.")
        ctx.ui.say("Kiosk Satellite settings applied.")
