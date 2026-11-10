"""Spike: build Android's bionic/libcore `tzdata` file from an IANA release.

Usage: python3 build_tzdata.py tzdataYYYYx.tar.gz OUT_FILE
Needs `zic` on PATH. Compiles "fat" TZif files (Android 8's libcore reads the
32-bit section, which slim files leave empty), then packs them in the format
of AOSP's ZoneCompactor:

  "tzdata" + version + NUL      12 bytes
  index_offset, data_offset, zonetab_offset    big-endian int32
  index: per zone, sorted: name[40], start, length, unused(0)
  data:  the TZif files back to back
  zone.tab
"""
import io
import os
import struct
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

SOURCES = ["africa", "antarctica", "asia", "australasia", "europe", "northamerica",
           "southamerica", "etcetera", "backward"]


def build(tarball: Path, out: Path) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        src, zones = Path(tmp) / "src", Path(tmp) / "zones"
        with tarfile.open(tarball) as t:
            t.extractall(src, filter="data")
        version = (src / "version").read_text().strip()
        subprocess.run(["zic", "-b", "fat", "-d", str(zones), *[str(src / s) for s in SOURCES]],
                       check=True)
        names = sorted(str(p.relative_to(zones)) for p in zones.rglob("*") if p.is_file())
        data = io.BytesIO()
        index = io.BytesIO()
        for name in names:
            blob = (zones / name).read_bytes()
            if not blob.startswith(b"TZif"):
                continue
            enc = name.encode("ascii")
            if len(enc) > 39:
                raise ValueError(f"zone name too long: {name}")
            index.write(enc.ljust(40, b"\0") + struct.pack(">iii", data.tell(), len(blob), 0))
            data.write(blob)
        # Android keeps zone.tab's data lines only, without the comments.
        zonetab = b"".join(l for l in (src / "zone.tab").read_bytes().splitlines(keepends=True)
                           if l.strip() and not l.startswith(b"#"))
        header_len = 12 + 12
        index_offset = header_len
        data_offset = index_offset + len(index.getvalue())
        zonetab_offset = data_offset + len(data.getvalue())
        head = f"tzdata{version}".encode("ascii").ljust(12, b"\0")[:12]
        out.write_bytes(head + struct.pack(">iii", index_offset, data_offset, zonetab_offset)
                        + index.getvalue() + data.getvalue() + zonetab)
        return version


if __name__ == "__main__":
    v = build(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"built tzdata{v}: {os.path.getsize(sys.argv[2])} bytes")
