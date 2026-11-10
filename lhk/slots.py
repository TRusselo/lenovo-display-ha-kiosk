"""Are both slots' firmware the same? Checked from the stock backup before flashing.

The tool flashes slot A and makes it active, whichever slot the display was
running. It never writes the per-slot firmware below. On a display that was
running from slot B, slot A could still hold older firmware from before the
update that moved it to B, and the 2021 userdebug system might then fail to
boot on it. On healthy units both slots match: confirmed on two SD-8501F
backups. So any difference stops the run instead of guessing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# The A/B partitions the tool never flashes: the bootloader chain, then the
# firmware each display keeps (its own 8" stock dsp/modem/drm/bluetooth).
SLOT_FIRMWARE = ["sbl1", "aboot", "tz", "rpm", "keymaster", "cmnlib", "devcfg",
                 "oem_bootloader", "dsp", "modem", "drm", "bluetooth"]


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def has_slot_backup(parts_dir: Path) -> bool:
    return all((Path(parts_dir) / f"{b}_{s}.bin").exists() for b in SLOT_FIRMWARE for s in "ab")


def differing_slots(parts_dir: Path) -> list[str]:
    parts = Path(parts_dir)
    return [b for b in SLOT_FIRMWARE
            if _digest(parts / f"{b}_a.bin") != _digest(parts / f"{b}_b.bin")]
