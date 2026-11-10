"""Fetch what the tool needs from its original sources, and verify it.

Nothing in manifest.json is hosted by this repo. Downloads resume after an
interruption, every file is checked against its pinned SHA-256, and a file
that doesn't match is deleted and stops the run.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
import contextlib
from pathlib import Path

import requests

NEEDED_FREE_BYTES = 12 * 1024 ** 3
CHUNK = 1 << 20


class HashMismatch(Exception):
    pass


class DiskTooFull(Exception):
    pass


def _repo_file(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / name


def load_manifest(path: Path | None = None) -> dict:
    data = json.loads(Path(path or _repo_file("manifest.json")).read_text(encoding="utf-8"))
    return {e["id"]: e for e in data["entries"]}


def platform_entry(prefix: str, manifest: dict, plat: str) -> str:
    """The manifest id of `prefix` built for this OS and CPU, e.g. uv-linux-x86_64."""
    key = f"{prefix}-{plat}"
    if key not in manifest:
        raise KeyError(f"{prefix} isn't available for {plat}; supported: "
                       + ", ".join(k[len(prefix) + 1:] for k in manifest if k.startswith(prefix + "-")))
    return key


def require_free_space(path: Path, needed: int = NEEDED_FREE_BYTES) -> None:
    p = Path(path)
    while not p.exists():
        p = p.parent
    free = shutil.disk_usage(p).free
    if free < needed:
        raise DiskTooFull(f"Only {free / 1024 ** 3:.1f} GB free at {p}; "
                          f"this needs {needed / 1024 ** 3:.0f} GB. Free some space and run again.")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, part: Path, ui=None) -> None:
    part.parent.mkdir(parents=True, exist_ok=True)
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with requests.get(url, headers=headers, stream=True, timeout=60) as r:
        if have and r.status_code == 200:      # server ignored the range: start over
            have = 0
        elif r.status_code == 416:             # already complete
            return
        r.raise_for_status()
        with open(part, "ab" if have else "wb") as f:
            for chunk in r.iter_content(CHUNK):
                f.write(chunk)


def _unpack(kind: str, archive: Path, out: Path) -> None:
    tmp = out.with_name(out.name + ".unpacking")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    if kind == "zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(tmp)
            # extractall drops Unix permissions, so adb and fastboot couldn't run.
            for info in z.infolist():
                mode = (info.external_attr >> 16) & 0o777
                if mode & 0o111 and not info.is_dir():
                    (tmp / info.filename).chmod(mode)
    elif kind == "7z":
        import py7zr
        with py7zr.SevenZipFile(archive) as z:
            z.extractall(tmp)
    elif kind == "tar.gz":
        import tarfile
        with tarfile.open(archive, "r:gz") as t:
            t.extractall(tmp, filter="data")
    else:
        raise ValueError(f"unknown archive type {kind}")
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)


def _busy(ctx, text):
    return ctx.ui.busy(text) if ctx.ui is not None else contextlib.nullcontext()


def fetch(entry_id: str, ctx) -> Path:
    manifest = ctx.state.get("manifest") or load_manifest()
    e = manifest[entry_id]
    downloads = ctx.paths.cache / "downloads"
    file = downloads / e["url"].rsplit("/", 1)[-1]
    verified = file.with_name(file.name + ".verified")
    out = ctx.paths.cache / entry_id
    done_marker = out / ".lhk-unpacked"

    if e["unpack"] and done_marker.exists() and done_marker.read_text() == e["sha256"]:
        return out
    if not (file.exists() and verified.exists() and verified.read_text() == e["sha256"]):
        part = file.with_name(file.name + ".part")
        with _busy(ctx, f"Downloading {file.name} ({e['size'] / 1024 ** 2:.0f} MB)"):
            _download(e["url"], part, ctx.ui)
            got = _sha256(part)
        if got != e["sha256"]:
            part.unlink(missing_ok=True)
            raise HashMismatch(f"{file.name} doesn't match its pinned checksum (got {got}). "
                               "It was deleted. Run again to re-download; if it keeps failing, "
                               "the source changed and this tool needs updating.")
        part.replace(file)
        verified.write_text(e["sha256"])
    if not e["unpack"]:
        return file
    with _busy(ctx, f"Unpacking {file.name}"):
        _unpack(e["unpack"], file, out)
    done_marker.write_text(e["sha256"])
    return out
