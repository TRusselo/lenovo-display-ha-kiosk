"""Full stock backup over EDL, and restoring it.

Reads every partition except userdata (about 2.5 GB). Device-specific
partitions come first, so even a cut-short run keeps the irreplaceable ones.
A rerun keeps every file already read in full. The backup holds unit-specific
data (persist, modemst, devinfo, keymaster) and must never be shared.

A backup restores only to the display it came from: restore compares the
device's partition table, including its unique disk GUID, byte for byte.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from lhk.ui import choose
from lhk.firmware import gpt_signature, read_gpt

SECTOR = 512
SKIP_WARNING = ("If anything goes wrong, you may not be able to restore this display "
                "unless you can find its firmware elsewhere.")
PRIORITY = ["vbmeta_a", "vbmeta_b", "devinfo", "factory", "factory_bootloader", "keystore",
            "config", "oem_bootloader_a", "oem_bootloader_b", "keymaster_a", "keymaster_b",
            "cmnlib_a", "cmnlib_b", "limits", "dip", "syscfg", "mcfg", "apdp", "msadp", "dpo",
            "dsp_a", "dsp_b"]
SKIP = {"userdata"}
GPT_FILE = "gpt_main0.bin"


class BackupMismatch(Exception):
    pass


def _expected(parts_dir: Path) -> dict[str, int]:
    return {p.name: p.sectors * SECTOR for p in read_gpt(parts_dir / GPT_FILE) if p.name not in SKIP}


def missing(parts_dir: Path) -> list[str]:
    exp = _expected(parts_dir)
    todo = [n for n, size in exp.items()
            if not (parts_dir / f"{n}.bin").exists() or (parts_dir / f"{n}.bin").stat().st_size != size]
    return sorted(todo, key=lambda n: (PRIORITY.index(n) if n in PRIORITY else len(PRIORITY), list(exp).index(n)))


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def backup(ctx, out: Path, edl) -> None:
    parts = Path(out) / "partitions"
    parts.mkdir(parents=True, exist_ok=True)
    if not (parts / GPT_FILE).exists():
        edl.dump_gpt(parts)
    else:
        _require_same_display(edl, parts, "This backup folder belongs to a different display. "
                                          "Use --name to give this display its own folder.")
    todo = missing(parts)
    if todo:
        ctx.ui.say(f"Backing up {len(todo)} partitions.")
        for i, name in enumerate(todo, 1):
            with ctx.ui.busy(f"Backing up {name} ({i} of {len(todo)})"):
                edl.read([name], parts)
    left = missing(parts)
    if left:
        raise BackupMismatch(f"Backup incomplete, still missing: {', '.join(left)}. Run again to continue.")
    lines = [f"{_sha(f)}  {f.name}" for f in sorted(parts.glob("*.bin"))]
    (Path(out) / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ctx.ui.say(f"Backup complete: {out}. Keep it private: it holds data unique to this display.")


def _require_same_display(edl, parts: Path, message: str) -> None:
    """The display's disk GUID and partition layout must match the backup's.
    A/B slot bits and CRCs are ignored: they change on every boot and slot switch."""
    with tempfile.TemporaryDirectory() as tmp:
        edl.dump_gpt(tmp)
        if gpt_signature(Path(tmp) / GPT_FILE) != gpt_signature(parts / GPT_FILE):
            raise BackupMismatch(message)


def verify_backup(out: Path) -> list[str]:
    out = Path(out)
    parts = out / "partitions"
    sums = out / "SHA256SUMS"
    if not (parts / GPT_FILE).exists():
        return [f"no {GPT_FILE} in {parts}"]
    if not sums.exists():
        return ["no SHA256SUMS: the backup never finished"]
    problems = [f"{n} is missing or the wrong size" for n in missing(parts)]
    for line in sums.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split(None, 1)
        f = parts / name.strip()
        if f.exists() and _sha(f) != digest:
            problems.append(f"{f.stem} doesn't match its checksum")
    return problems


def restore(ctx, out: Path, edl) -> None:
    problems = verify_backup(out)
    if problems:
        raise BackupMismatch("This backup can't be restored: " + "; ".join(problems))
    parts = Path(out) / "partitions"
    _require_same_display(edl, parts, "This backup is from a different display. Each backup only "
                                      "restores to its own display.")
    ctx.ui.say("WARNING: this overwrites everything on the display with the backup, and erases its "
               "user data. The display goes back to its stock software, with Google services.")
    if not choose(ctx.ui, "Type restore to continue, or press Enter to stop: ", "restore"):
        raise BackupMismatch("Restore cancelled. Nothing was changed.")
    todo = [p.name for p in read_gpt(parts / GPT_FILE) if p.name not in SKIP]
    for i, name in enumerate(todo, 1):
        with ctx.ui.busy(f"Writing {name} ({i} of {len(todo)})"):
            edl.write(name, parts / f"{name}.bin")
    # The converted system's user data would make stock fail to start or ask for a reset.
    with ctx.ui.busy("Erasing user data"):
        edl.erase("userdata")
    ctx.ui.say("Every partition is written. The display stays in EDL mode until you unplug its power.")


def pack(ctx, out: Path) -> Path:
    """The whole backup as one zip next to its folder: one file to copy
    somewhere safe. Empty partition space compresses to almost nothing."""
    out = Path(out)
    dest = out.with_name(out.name + ".zip")
    part = dest.with_name(dest.name + ".part")
    with ctx.ui.busy(f"Packing the backup into one file, {dest.name}"):
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in sorted(out.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(out).as_posix())
        os.replace(part, dest)
    return dest


def unpack(ctx, archive: Path, dest_root: Path) -> Path:
    """Unpack a packed backup into dest_root/<name>, unless it's already there."""
    archive = Path(archive)
    dest = Path(dest_root) / archive.stem
    if dest.exists() and not verify_backup(dest):
        return dest
    with zipfile.ZipFile(archive) as z:
        names = z.infolist()
        for i in names:
            p = Path(i.filename)
            if p.is_absolute() or ".." in p.parts:
                raise BackupMismatch(f"This backup file holds a path outside its folder ({i.filename}).")
        need = sum(i.file_size for i in names)
        Path(dest_root).mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(dest_root).free
        if free < need + (1 << 30):
            raise BackupMismatch(f"Not enough free space to unpack the backup: it needs "
                                 f"{(need >> 30) + 2} GB, and {free >> 30} GB is free.")
        if dest.exists():
            shutil.rmtree(dest)
        with ctx.ui.busy(f"Unpacking {archive.name}"):
            z.extractall(dest)
    return dest


def confirm_skip(ui) -> bool:
    ui.say("WARNING: skipping the backup. " + SKIP_WARNING)
    return choose(ui, "Type skip to continue without a backup, or press Enter to make one: ", "skip")
