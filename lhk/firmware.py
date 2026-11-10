"""Pull the flash images out of the OIMK userdebug full-eMMC dump (FRW.bin).

FRW.bin is a 10" ("blueberry") disk, so its partitions sit at different
offsets from the 8". Images are found with FRW's own partition table and
flashed by name; FRW's table itself is never written to a display.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

SECTOR = 512
CHUNK = 4 << 20

# Only these are flashed, to slot A. Slot B stays stock as a fallback.
FLASH_SET = ["boot_a", "system_a", "vendor_a", "oem_a", "vbmeta_a"]

# Never written, on either slot. dsp/modem/drm/bluetooth keep the 8"'s own
# stock versions (tested on hardware); the rest would brick or wipe the unit.
FORBIDDEN = {"partition", "devinfo", "persist", "sbl1", "aboot", "tz", "rpm",
             "dsp", "modem", "drm", "bluetooth", "keymaster", "cmnlib", "devcfg",
             "oem_bootloader", "modemst1", "modemst2", "fsg", "fsc", "sec", "DDR"}


class ForbiddenPartition(Exception):
    pass


@dataclass(frozen=True)
class Partition:
    name: str
    first_lba: int
    sectors: int


def is_forbidden(name: str) -> bool:
    base = name[:-2] if name.endswith(("_a", "_b")) else name
    return base in FORBIDDEN or name in FORBIDDEN


def read_gpt(path: Path) -> list[Partition]:
    with open(path, "rb") as f:
        head = f.read(SECTOR * 2)
        i = head.find(b"EFI PART")
        if i < 0:
            raise ValueError(f"{path}: no GPT header")
        entries_lba, n, size = struct.unpack("<QII", head[i + 72:i + 88])
        # A disk image has the entries where the header says; a table dumped
        # on its own (gpt_main0.bin) may be shorter, with them right after it.
        f.seek(entries_lba * SECTOR)
        table = f.read(n * size)
        if len(table) < n * size:
            f.seek(i + SECTOR)
            table = f.read(n * size)
    parts = []
    for k in range(n):
        e = table[k * size:(k + 1) * size]
        if len(e) < 128 or e[:16] == bytes(16):
            continue
        first, last = struct.unpack("<QQ", e[32:48])
        parts.append(Partition(e[56:128].decode("utf-16le").rstrip("\0"), first, last - first + 1))
    return parts


def gpt_signature(path: Path) -> tuple:
    """What identifies a display's disk: its unique disk GUID plus each
    partition's name, start and size. Leaves out the attribute bits (A/B slot
    state) and CRCs, which the bootloader rewrites on every boot."""
    with open(path, "rb") as f:
        head = f.read(SECTOR * 2)
    i = head.find(b"EFI PART")
    if i < 0:
        raise ValueError(f"{path}: no GPT header")
    disk_guid = head[i + 56:i + 72]
    return disk_guid, tuple((p.name, p.first_lba, p.sectors) for p in read_gpt(path))


def extract(frw: Path, names: list[str], out: Path) -> dict[str, Path]:
    for n in names:
        if is_forbidden(n):
            raise ForbiddenPartition(f"{n} must never be flashed")
    table = {p.name: p for p in read_gpt(frw)}
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    result = {}
    with open(frw, "rb") as src:
        for n in names:
            p = table[n]                      # KeyError: not in this dump
            dest = out / f"{n}.img"
            src.seek(p.first_lba * SECTOR)
            left = p.sectors * SECTOR
            with open(dest, "wb") as d:
                while left:
                    chunk = src.read(min(left, CHUNK))
                    if not chunk:
                        raise ValueError(f"{frw} ends inside {n}")
                    d.write(chunk)
                    left -= len(chunk)
            result[n] = dest
    return result
