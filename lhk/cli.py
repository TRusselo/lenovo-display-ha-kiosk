"""lhk: turn a stock Lenovo Smart Display 8 into a degoogled Home Assistant kiosk."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lhk import __version__, backup, log, plan, relock
from lhk.downloads import fetch
from lhk.edl import Edl
from lhk.modes import Mode, wait_for_mode
from lhk.runner import RealRunner, Tools, platform_id
from lhk.steps import Context, Paths, run_steps


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="lhk", description=__doc__)
    p.add_argument("--version", action="version", version=f"lhk {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp):
        sp.add_argument("--workdir", type=Path, default=Path.cwd(),
                        help="folder for downloads, backups, logs and progress (default: here)")
        sp.add_argument("--name", default="display",
                        help="a name for this display, so several can be done one after another")

    s = sub.add_parser("setup", help="convert a display, from stock to working kiosk")
    common(s)
    s.add_argument("--dry-run", action="store_true", help="list the steps, change nothing")
    s.add_argument("--from", dest="start_from", metavar="STEP", help="start at STEP")
    s.add_argument("--restart", action="store_true", help="forget saved progress")
    s.add_argument("--skip-backup", action="store_true", help="skip the stock backup (asks first)")
    s.add_argument("--force-model", action="store_true", help="allow an untested model (dangerous)")

    r = sub.add_parser("restore", help="put a stock backup back on the display it came from")
    common(r)
    r.add_argument("backup_dir", type=Path)

    lk = sub.add_parser("lock", help="lock verified boot on a restored stock display left unlocked")
    common(lk)

    st = sub.add_parser("status", help="show which setup steps are done")
    common(st)
    return p


def _context(args) -> Context:
    from lhk.ui import UI
    paths = Paths(args.workdir)
    logger = log.setup(paths.logs / f"{args.name}.log")
    ctx = Context(runner=RealRunner(logger=logger), ui=UI(), paths=paths,
                  state={"progress_id": args.name, "log": logger})
    ctx.state["tools"] = Tools.locate(paths.cache)
    return ctx


def _status(args) -> int:
    f = Paths(args.workdir).progress / f"{args.name}.json"
    done = json.loads(f.read_text(encoding="utf-8")).get("done", []) if f.exists() else []
    for s in plan.setup_steps():
        print(f"  [{'x' if s.name in done else ' '}] {s.name:16} {s.title}")
    return 0


def _tools_and_edl(ctx) -> Edl:
    # Every tool first, so nothing downloads while the display waits in EDL.
    fetch(f"platform-tools-{platform_id()}", ctx)
    ctx.state["tools"] = Tools.locate(ctx.paths.cache)
    edl = Edl(ctx)
    with ctx.ui.busy("Setting up edl"):
        edl.prepare()
    return edl


def _lock(args) -> int:
    ctx = _context(args)
    ctx.ui.say("This locks verified boot on a display restored to stock and left unlocked. It reads the "
               "display's boot images in EDL mode first, and locks only if they're stock. You'll type "
               "lock to confirm.")
    return 0 if relock.lock_only(ctx, _tools_and_edl(ctx)) else 1


def _restore(args) -> int:
    folder = args.backup_dir
    if not folder.exists():
        print(f"Can't restore this backup: no backup at {folder}", file=sys.stderr)
        return 2
    ctx = _context(args)
    ctx.ui.say("This puts the display back on its stock software, with Google services. It takes "
               "about 10 minutes: the display goes into EDL mode for writing, then fastboot mode to "
               "lock verified boot again. You'll type restore, then lock, to confirm.")
    if folder.is_file() and folder.suffix.lower() == ".zip":
        try:
            folder = backup.unpack(ctx, folder, ctx.paths.root / "restore")
        except Exception as e:
            print(f"Can't restore this backup: {e}", file=sys.stderr)
            return 2
    with ctx.ui.busy("Checking the backup"):
        problems = backup.verify_backup(folder) if folder.exists() else [f"no backup at {folder}"]
    if problems:
        print("Can't restore this backup: " + "; ".join(problems), file=sys.stderr)
        return 2
    edl = _tools_and_edl(ctx)
    problems = relock.stock_problems(folder)
    if problems:
        ctx.ui.say("Note: this backup isn't plain stock (" + "; ".join(problems) + "), so the display will "
                   "be left unlocked at the end. " + relock.UNLOCKED_NOTE)
    wait_for_mode(Mode.EDL, ctx, prompt=plan.EDL_PROMPT, timeout=180)
    backup.restore(ctx, folder, edl)
    return 0 if relock.relock(ctx, folder) else 1


def _setup(args) -> int:
    ctx = _context(args)
    ctx.dry_run = args.dry_run
    ctx.state["skip_backup"] = args.skip_backup
    ctx.state["force_model"] = args.force_model
    fresh = args.restart or not (ctx.paths.progress / f"{ctx.state.get('progress_id')}.json").exists()
    if fresh and not args.dry_run and args.start_from is None:
        ctx.ui.say("Setup takes 20 to 30 minutes, including about 1 GB of downloads the first time. "
                   "The tool tells you each time it needs you at the display.")
    run_steps(plan.setup_steps(), ctx, start_from=args.start_from, restart=args.restart)
    return 0


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    try:
        return {"setup": _setup, "restore": _restore, "lock": _lock, "status": _status}[args.command](args)
    except KeyboardInterrupt:
        print("\nStopped. Run the same command again to continue where you left off.", file=sys.stderr)
        return 130
    except Exception as e:  # every failure ends in plain words, not a traceback
        print(f"\nStopped: {e}\nRun the same command again to retry this step. "
              f"Details are in the log folder.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
