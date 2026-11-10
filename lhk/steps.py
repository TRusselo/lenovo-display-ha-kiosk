"""Ordered, resumable steps.

Progress is saved after every step to progress/<serial>.json, so a run that
stops (Ctrl-C, a dropped cable, an error) starts again where it left off.
Each step can also check the device itself (Step.done) and is skipped when its
work is already there, so a rerun never repeats an unlock, flash or wipe.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lhk import __version__


@dataclass
class Paths:
    root: Path

    def __post_init__(self):
        self.root = Path(self.root)

    @property
    def cache(self) -> Path:
        return self.root / "cache"

    @property
    def backup(self) -> Path:
        return self.root / "backup"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def progress(self) -> Path:
        return self.root / "progress"


@dataclass
class Context:
    runner: Any
    ui: Any
    paths: Paths
    dry_run: bool = False
    state: dict = field(default_factory=dict)

    @property
    def serial(self) -> str:
        return self.state.get("serial") or "unknown"


class Step:
    name = "step"
    title = "Step"

    def done(self, ctx: Context) -> bool:
        """True when the device already has this step's result."""
        return False

    def run(self, ctx: Context) -> None:
        raise NotImplementedError


def _progress_file(ctx: Context) -> Path:
    # A fixed id per display (the CLI's --name), not the serial: the first
    # steps run before the serial is known.
    return ctx.paths.progress / f"{ctx.state.get('progress_id') or ctx.serial}.json"


def _load(ctx: Context) -> list[str]:
    f = _progress_file(ctx)
    if not f.exists():
        return []
    data = json.loads(f.read_text(encoding="utf-8"))
    if data.get("serial"):
        # Later steps refuse a different display than the one this progress is for.
        ctx.state["bound_serial"] = data["serial"]
    return data.get("done", [])


def _save(ctx: Context, done: list[str]) -> None:
    f = _progress_file(ctx)
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    serial = ctx.state.get("serial") or ctx.state.get("bound_serial")
    tmp.write_text(json.dumps({"done": done, "serial": serial, "version": __version__}, indent=1),
                   encoding="utf-8")
    os.replace(tmp, f)


def run_steps(steps: list[Step], ctx: Context, *, start_from: str | None = None,
              restart: bool = False) -> None:
    names = [s.name for s in steps]
    if start_from is not None and start_from not in names:
        raise ValueError(f"no step named {start_from!r}; steps are: {', '.join(names)}")
    done = [] if restart else _load(ctx)
    if start_from is not None:
        for name in names[:names.index(start_from)]:
            if name not in done:
                done.append(name)
    if all(n in done for n in names) and not ctx.dry_run and ctx.ui is not None:
        ctx.ui.say("Every step is already done for this display. Use --restart to run them again, "
                   "or --name to start a different display.")
        return
    finished = [n for n in names if n in done]
    if finished and not ctx.dry_run and ctx.ui is not None and start_from is None:
        nxt = next(s for s in steps if s.name not in done)
        ctx.ui.say(f"Picking up where the last run stopped, at: {nxt.title} "
                   f"({len(finished)} of {len(names)} steps done).")
    for step in steps:
        if step.name in done:
            continue
        if ctx.dry_run:
            if ctx.ui is not None:
                ctx.ui.say(f"[dry run] {step.title}")
            continue
        if step.done(ctx):
            if ctx.ui is not None:
                ctx.ui.say(f"Already done on the display: {step.title}.")
        else:
            step.run(ctx)
        done.append(step.name)
        _save(ctx, done)
