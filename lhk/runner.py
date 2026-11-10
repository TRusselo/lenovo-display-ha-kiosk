"""Every external command goes through a Runner, so tests can use a fake."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Result:
    code: int
    out: str


class CommandFailed(Exception):
    def __init__(self, args, result: Result):
        self.args_ = [str(a) for a in args]
        self.result = result
        super().__init__(f"command failed ({result.code}): {' '.join(self.args_)}\n{result.out.strip()}")


class RealRunner:
    """Runs commands and writes each one, with its exit code and output, to the
    run log (redacted). log_output=False keeps a command's output out of the log,
    for reads that return secrets."""

    def __init__(self, logger=None):
        self.logger = logger

    def run(self, args, *, check=True, timeout=60, env=None, log_output=True) -> Result:
        argv = [str(a) for a in args]
        if self.logger:
            self.logger.info("$ %s", " ".join(argv))
        p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           stdin=subprocess.DEVNULL, timeout=timeout, env=env)
        result = Result(p.returncode, p.stdout.decode("utf-8", "replace"))
        if self.logger:
            shown = result.out.strip()[-4000:] if log_output else "(output not logged)"
            self.logger.info("exit %d\n%s", result.code, shown)
        if check and result.code != 0:
            raise CommandFailed(args, result)
        return result


def platform_id() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "darwin"
    return "linux"


def platform_arch() -> str:
    """e.g. linux-x86_64, darwin-arm64, windows-x86_64 (Windows on ARM runs x86_64 builds)."""
    import platform
    m = platform.machine().lower()
    if m in ("amd64", "x86_64", "x64"):
        arch = "x86_64"
    elif m in ("arm64", "aarch64"):
        arch = "arm64" if platform_id() == "darwin" else "aarch64"
    else:
        arch = m
    if platform_id() == "windows":
        arch = "x86_64"
    return f"{platform_id()}-{arch}"


@dataclass
class Tools:
    adb: Path
    fastboot: Path

    @classmethod
    def locate(cls, cache: Path) -> "Tools":
        """Google's platform-tools, as downloads.fetch('platform-tools-<os>') unpacks them."""
        d = Path(cache) / f"platform-tools-{platform_id()}" / "platform-tools"
        exe = ".exe" if platform_id() == "windows" else ""
        return cls(adb=d / f"adb{exe}", fastboot=d / f"fastboot{exe}")
