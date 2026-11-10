"""uv, downloaded at run time (pinned, hash-checked), runs the third-party
Python scripts this tool needs: edl and at_auth_unlock.py. uv fetches a Python
and each script's packages into its own cache, so they work the same from the
standalone programs (which have no pip) and from source, and none of their
code or packages ends up inside this tool."""
from __future__ import annotations

from pathlib import Path

from lhk.downloads import fetch, load_manifest, platform_entry
from lhk.runner import platform_arch

PYTHON = "3.12"


def uv_path(ctx) -> Path:
    manifest = ctx.state.get("manifest") or load_manifest()
    root = fetch(platform_entry("uv", manifest, platform_arch()), ctx)
    name = "uv.exe" if platform_arch().startswith("windows") else "uv"
    found = sorted(Path(root).rglob(name))
    if not found:
        raise FileNotFoundError(f"{name} not found in {root}")
    return found[0]


def uv_python(uv: Path, *with_args: str) -> list:
    """The command prefix: uv run … python, with packages from with_args."""
    return [uv, "run", "--no-project", "--python", PYTHON, *with_args, "python"]
