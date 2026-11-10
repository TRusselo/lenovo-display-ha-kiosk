"""bkerler/edl, downloaded at run time (GPL-3.0, never bundled), driven with
the Amber/Blueberry firehose loader. It runs through uv (lhk/uvrun.py) with
its own requirements, so nothing of edl's ends up inside this tool."""
from __future__ import annotations

from pathlib import Path

from lhk.downloads import fetch
from lhk.uvrun import uv_path, uv_python

LOADER = "amber_bluebbery_prog_emmc_firehose_8953_ddr.mbn"
GPT_SECTORS = 34


class Edl:
    def __init__(self, ctx):
        self.ctx = ctx
        root = next(Path(fetch("edl", ctx)).glob("edl-*"))
        self.script = root / "edl.py"
        self.requirements = root / "requirements.txt"
        self.loader = fetch("firehose", ctx) / LOADER
        self.uv = uv_path(ctx)

    def _run(self, *args, timeout=1800):
        return self.ctx.runner.run(
            [*uv_python(self.uv, "--with-requirements", str(self.requirements)), self.script, *args,
             "--memory=eMMC", f"--loader={self.loader}"], timeout=timeout)

    def prepare(self) -> None:
        """Let uv fetch edl's packages now, before the display waits in EDL."""
        self.ctx.runner.run([*uv_python(self.uv, "--with-requirements", str(self.requirements)),
                             "-c", "pass"], timeout=1800)

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
