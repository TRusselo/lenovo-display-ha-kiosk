"""Are both slots' firmware the same? Checked from the stock backup before flashing.

The tool flashes slot A and makes it active, whichever slot the display was
running. It never writes the per-slot firmware below. On a display that was
running from slot B, slot A could still hold older firmware from before the
update that moved it to B, and the 2021 userdebug system might then fail to
boot on it. On healthy units both slots match: confirmed on two SD-8501F
backups.

What stops the run (GitHub issues 1 and 5, both converted fine after working
around the old check):
- Running slot A: nothing. Slot A's own firmware is what's starting it now.
- Running slot B: a different bootloader chain stops the run. Different radio
  firmware alone (dsp, modem, drm, bluetooth) is only a note: one SD-8 running
  slot B with older radio firmware in A started and worked after flashing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

# The A/B partitions the tool never flashes: the bootloader chain, then the
# firmware each display keeps (its own 8" stock dsp/modem/drm/bluetooth).
BOOT_CHAIN = ["sbl1", "aboot", "tz", "rpm", "keymaster", "cmnlib", "devcfg", "oem_bootloader"]
RADIO = ["dsp", "modem", "drm", "bluetooth"]
SLOT_FIRMWARE = BOOT_CHAIN + RADIO


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
