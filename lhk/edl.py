"""bkerler/edl, downloaded at run time (GPL-3.0, never bundled), driven with
the Amber/Blueberry firehose loader. It runs through uv (lhk/uvrun.py) with
its own requirements, so nothing of edl's ends up inside this tool."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from lhk import doc
from lhk.downloads import fetch
from lhk.modes import LIBUSB_MISSING, UsbBackendMissing
from lhk.runner import CommandFailed
from lhk.uvrun import uv_path, uv_python

LOADER = "amber_bluebbery_prog_emmc_firehose_8953_ddr.mbn"
GPT_SECTORS = 34


# edl runs in its own Python and loads the system's libusb, never the copy this
# tool brings. On a Mac that means Homebrew's.
MAC_LIBUSB = ("/opt/homebrew/lib/libusb-1.0.dylib", "/usr/local/lib/libusb-1.0.dylib")


def check_libusb(platform=None, exists=os.path.exists) -> None:
    """Stop before the display is put in EDL mode, not after."""
    if (platform or sys.platform) == "darwin" and not any(exists(p) for p in MAC_LIBUSB):
        raise UsbBackendMissing(LIBUSB_MISSING)


# edl draws its progress bar with block characters. Windows' console encoding (cp1252)
# can't print them, and edl crashed at 0% of the first read (GitHub issues 1, 3, 5).
UTF8 = {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
# What edl prints on Windows when the display has no WinUSB driver yet (issue 5).
NO_DRIVER = ("Please first install libusb_win32 driver from Zadig", "NotImplementedError: Operation not supported")
ZADIG = ("Windows can't talk to the display in EDL mode yet: it needs the WinUSB driver, installed once with "
         "Zadig. Follow " + doc("docs/drivers.md") + ", then run the same command again. The display can stay "
         "in EDL mode while you do.")


def _env() -> dict:
    return {**os.environ, **UTF8}


class Edl:
    def __init__(self, ctx):
        check_libusb()
        self.ctx = ctx
        root = next(Path(fetch("edl", ctx)).glob("edl-*"))
        self.script = root / "edl.py"
        self.requirements = root / "requirements.txt"
        self.loader = fetch("firehose", ctx) / LOADER
        self.uv = uv_path(ctx)

    def _run(self, *args, timeout=1800):
        try:
            return self.ctx.runner.run(
                [*uv_python(self.uv, "--with-requirements", str(self.requirements)), self.script, *args,
                 "--memory=eMMC", f"--loader={self.loader}"], timeout=timeout, env=_env())
        except CommandFailed as e:
            if any(m in e.result.out for m in NO_DRIVER):
                raise UsbBackendMissing(ZADIG) from e
            raise

    def prepare(self) -> None:
        """Let uv fetch edl's packages now, before the display waits in EDL."""
        self.ctx.runner.run([*uv_python(self.uv, "--with-requirements", str(self.requirements)),
                             "-c", "pass"], timeout=1800, env=_env())

    def dump_gpt(self, dest_dir) -> None:
        # edl's own "gpt" command prints "Dumped GPT" but never writes the file
        # (its write is commented out), so read the raw sectors instead:
        # protective MBR, GPT header and 128 x 128-byte entries = 34 sectors.
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        self._run("rs", "0", str(GPT_SECTORS), str(Path(dest_dir) / "gpt_main0.bin"))

    def read(self, names, dest_dir) -> None:
        # One call per partition: edl takes comma-separated lists, which a
        # comma in the folder path would split.
        for n in names:
            self._run("r", n, str(Path(dest_dir) / f"{n}.bin"))

    def write(self, name, file) -> None:
        self._run("w", name, str(file))

    def erase(self, name) -> None:
        self._run("e", name)
