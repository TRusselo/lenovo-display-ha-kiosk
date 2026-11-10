"""Install current IANA time zone data, so regions whose DST rules changed
after this 2021 build show the right time.

assets/tzdata/tzdata is built from the official IANA release (public domain)
by spikes/tzdata/build_tzdata.py. Tested on hardware: the C library (Kiosk
Satellite's clock), Java and Home Assistant dashboards all showed the right
time for America/Edmonton after it was installed.
"""
from __future__ import annotations

import struct

from lhk.downloads import _repo_file
from lhk.steps import Step
from lhk.system import adb, ensure_root_rw, shell

DEVICE_PATH = "/system/usr/share/zoneinfo/tzdata"


def version(data: bytes) -> str:
    return data[6:12].split(b"\0", 1)[0].decode("ascii")


def zone_names(data: bytes | None = None) -> set[str]:
    """Every zone in the file (ZoneCompactor format): a 52-byte index entry per zone."""
    data = data if data is not None else bundled().read_bytes()
    index_offset, data_offset = struct.unpack(">ii", data[12:20])
    return {data[i:i + 40].rstrip(b"\0").decode("ascii")
            for i in range(index_offset, data_offset, 52)}


def bundled():
    return _repo_file("assets/tzdata/tzdata")


class TzdataStep(Step):
    name = "tzdata"
    title = "Update the time zone data"

    def done(self, ctx) -> bool:
        head = shell(ctx, "head", "-c", "12", DEVICE_PATH, check=False).encode("ascii", "replace")
        return head.startswith(b"tzdata") and version(head) >= version(bundled().read_bytes())

    def run(self, ctx) -> None:
        ensure_root_rw(ctx)
        adb(ctx, "push", str(bundled()), DEVICE_PATH)
        shell(ctx, "chmod", "644", DEVICE_PATH)
        shell(ctx, "restorecon", DEVICE_PATH)
        ctx.ui.say(f"Time zone data updated to {version(bundled().read_bytes())}.")
