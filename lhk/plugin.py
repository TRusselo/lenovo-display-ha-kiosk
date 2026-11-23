"""Casting Helper, a Kiosk Satellite plugin: cast video and music to the display from phones and computers.

From the clock tool (lenovo-clock-ha-kiosk), where it was tried on a clock. Downloaded with the other tools,
newest release each run. A download that fails, or isn't a Kiosk Satellite plugin, is silent: nothing is said,
and nothing is installed. Unlike the manifest's downloads it isn't pinned to a checksum: the address always
serves the newest release, and Kiosk Satellite checks the package itself.

Kiosk Satellite installs a plugin ZIP only through its remote API, signed in. The tool signs in as it does
for the settings (kiosk.remote_admin): over the adb tunnel, with the admin password read with root, which
never reaches a command line or the log.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import zipfile
from pathlib import Path

from lhk import kiosk
from lhk.steps import Step

URL = "https://gitlab.tiered.top/api/v4/projects/3/packages/generic/casting-helper/latest/casting-helper.zip"
ID = "casting-helper"
NAME = "Casting Helper"
MAX_BYTES = 4 * 1024 * 1024        # Kiosk Satellite's own limit for a plugin ZIP

log = logging.getLogger("lhk")


def _file(ctx) -> Path:
    return ctx.paths.cache / "downloads" / "casting-helper.zip"


def manifest_of(data: bytes) -> dict | None:
    """The plugin's manifest, or None when `data` isn't a Casting Helper package."""
    try:
        if not 0 < len(data) <= MAX_BYTES:
            return None
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if not {"kiosk-satellite-plugin.json", "plugin.jar"} <= set(z.namelist()):
                return None
            m = json.loads(z.read("kiosk-satellite-plugin.json"))
        return m if isinstance(m, dict) and m.get("id") == ID else None
    except Exception:
        return None


def cached(ctx) -> Path | None:
    """This run's download, if there is a good one."""
    f = _file(ctx)
    return f if f.is_file() and manifest_of(f.read_bytes()) else None


def fetch(ctx) -> Path | None:
    """The newest Casting Helper, or None, silently. An older copy is dropped first: a failed download
    leaves nothing, so nothing is installed."""
    f = _file(ctx)
    f.unlink(missing_ok=True)
    try:
        r = kiosk._http(ctx).get(URL, timeout=60)
        r.raise_for_status()
        if manifest_of(r.content) is None:
            log.info("Casting Helper: the download isn't a Kiosk Satellite plugin; skipped")
            return None
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(r.content)
        return f
    except Exception as e:
        log.info("Casting Helper: download failed (%s); skipped", type(e).__name__)
        return None


class PluginStep(Step):
    name = "casting-helper"
    title = "Add Casting Helper to Kiosk Satellite"

    def run(self, ctx) -> None:
        zip_path = cached(ctx) or fetch(ctx)
        if zip_path is None:
            return                     # no download: nothing to install, nothing to say
        data = zip_path.read_bytes()
        version = manifest_of(data).get("version", "")
        try:
            http, base, token = kiosk.remote_admin(ctx)
            headers = {"Authorization": f"Bearer {token}"}

            def api(name, params=None):
                r = http.post(f"{base}/api/commands/{name}", json=params or {}, headers=headers, timeout=95)
                r.raise_for_status()
                body = r.json()
                if not body.get("ok"):
                    raise RuntimeError(body.get("error") or f"{name} failed")
                return body.get("data")

            mine = [p for p in api("listPlugins") or [] if p.get("id") == ID]
            if mine and mine[0].get("version") == version and mine[0].get("enabled"):
                ctx.ui.say(f"{NAME} {version} is already in Kiosk Satellite, and on.")
                return
            with ctx.ui.busy(f"Adding {NAME} {version} to Kiosk Satellite"):
                api("setPluginsEnabled", {"enabled": True})
                api("installPlugin", {"data": base64.b64encode(data).decode(), "trusted": True})
                api("enablePlugin", {"id": ID})
        except Exception as e:
            log.info("Casting Helper: install failed (%s: %s)", type(e).__name__, e)
            why = str(e) if isinstance(e, (RuntimeError, kiosk.KioskError)) else \
                "Kiosk Satellite's remote admin didn't answer"
            ctx.ui.say(f"{NAME} wasn't added ({why}). Setup goes on without it. To add it yourself: in "
                       f"Kiosk Satellite, Plugin Manager, Install from ZIP, with {zip_path}")
            return
        ctx.ui.ok(f"{NAME} {version} is in Kiosk Satellite, and on: cast to the display from a phone or "
                  "computer on the same network.")
