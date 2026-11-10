import io

import pytest

from lhk import cli, plan
from lhk.steps import Context, Paths, run_steps
from tests.fakes import FakeRunner, FakeUI


def test_step_order_matches_design():
    assert [s.name for s in plan.setup_steps()] == [
        "prerequisites", "downloads", "backup", "unlock", "flash", "root", "tzdata",
        "things-settings", "degoogle", "mixer", "kiosk-install", "kiosk-grants",
        "kiosk-settings", "bootfix", "verify",
    ]


def test_dry_run_prints_commands_runs_none(tmp_path):
    runner = FakeRunner()
    ui = FakeUI()
    ctx = Context(runner=runner, ui=ui, paths=Paths(tmp_path), dry_run=True,
                  state={"progress_id": "display"})
    run_steps(plan.setup_steps(), ctx)
    assert runner.calls == []
    assert len([l for l in ui.lines if l.startswith("[dry run]")]) == len(plan.setup_steps())


def test_restore_command_requires_backup_dir(capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["restore"])
    assert e.value.code != 0


def test_restore_command_refuses_missing_folder(tmp_path, capsys):
    code = cli.main(["restore", str(tmp_path / "nope"), "--workdir", str(tmp_path)])
    assert code != 0
    assert "backup" in capsys.readouterr().err.lower()


def test_status_lists_progress(tmp_path, capsys):
    (tmp_path / "progress").mkdir()
    (tmp_path / "progress" / "display.json").write_text('{"done": ["prerequisites", "downloads"]}')
    assert cli.main(["status", "--workdir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "downloads" in out and "backup" in out


def test_progress_id_survives_serial_change(tmp_path):
    # Steps before the unlock run before the serial is known; progress must stay in one file.
    from lhk.steps import Step

    class S(Step):
        def __init__(self, n, serial=None):
            self.name = self.title = n
            self.serial = serial

        def run(self, ctx):
            if self.serial:
                ctx.state["serial"] = self.serial

    ctx = Context(runner=None, ui=FakeUI(), paths=Paths(tmp_path), state={"progress_id": "display"})
    run_steps([S("a"), S("b", serial="HUA05X"), S("c")], ctx)
    assert (tmp_path / "progress" / "display.json").exists()
    assert not (tmp_path / "progress" / "HUA05X.json").exists()


def test_ui_confirm_typed():
    from lhk.ui import UI
    ui = UI(stdin=io.StringIO("skip\n"), stdout=io.StringIO())
    assert ui.ask("Type skip: ") == "skip"


def test_restore_gets_its_tools_before_asking_for_edl_and_locks_after(tmp_path, monkeypatch):
    # Run 3: restore never fetched adb, and left the display in EDL, unlocked.
    from lhk import backup, relock
    order = []
    monkeypatch.setattr(backup, "verify_backup", lambda d: [])
    monkeypatch.setattr(cli, "_context", lambda args: Context(runner=FakeRunner(), ui=FakeUI(),
                                                              paths=Paths(tmp_path), state={}))
    monkeypatch.setattr(cli, "fetch", lambda id_, ctx: order.append(id_.split("-")[0]))
    monkeypatch.setattr(cli.Tools, "locate", staticmethod(lambda cache: "tools"))
    monkeypatch.setattr(cli, "Edl", lambda ctx: order.append("edl") or type("E", (), {"prepare": lambda self: None})())
    monkeypatch.setattr(relock, "stock_problems", lambda d: [])
    monkeypatch.setattr(cli, "wait_for_mode", lambda mode, ctx, **kw: order.append("wait-edl"))
    monkeypatch.setattr(backup, "restore", lambda ctx, d, edl: order.append("write"))
    monkeypatch.setattr(relock, "relock", lambda ctx, d: order.append("relock") or True)
    (tmp_path / "bk").mkdir()
    assert cli.main(["restore", str(tmp_path / "bk"), "--workdir", str(tmp_path)]) == 0
    assert order == ["platform", "edl", "wait-edl", "write", "relock"]


def test_restore_accepts_the_one_file_backup(tmp_path, monkeypatch):
    from lhk import backup, relock
    seen = []
    z = tmp_path / "display.zip"
    z.write_bytes(b"PK")
    monkeypatch.setattr(cli, "_context", lambda args: Context(runner=FakeRunner(), ui=FakeUI(),
                                                              paths=Paths(tmp_path / "w"), state={}))
    (tmp_path / "u").mkdir()
    monkeypatch.setattr(backup, "unpack", lambda ctx, f, dest: seen.append(("unpack", f)) or tmp_path / "u")
    monkeypatch.setattr(backup, "verify_backup", lambda d: seen.append(("verify", d)) or [])
    monkeypatch.setattr(cli, "fetch", lambda id_, ctx: None)
    monkeypatch.setattr(cli.Tools, "locate", staticmethod(lambda cache: "tools"))
    monkeypatch.setattr(cli, "Edl", lambda ctx: type("E", (), {"prepare": lambda self: None})())
    monkeypatch.setattr(relock, "stock_problems", lambda d: [])
    monkeypatch.setattr(cli, "wait_for_mode", lambda mode, ctx, **kw: None)
    monkeypatch.setattr(backup, "restore", lambda ctx, d, edl: seen.append(("write", d)))
    monkeypatch.setattr(relock, "relock", lambda ctx, d: True)
    assert cli.main(["restore", str(z), "--workdir", str(tmp_path / "w")]) == 0
    assert seen == [("unpack", z), ("verify", tmp_path / "u"), ("write", tmp_path / "u")]


def test_backup_step_packs_one_file_and_says_where(tmp_path, monkeypatch):
    from lhk import backup
    packed = []
    monkeypatch.setattr(plan, "wait_for_mode", lambda mode, ctx, **kw: None)
    monkeypatch.setattr(plan, "Edl", lambda ctx: "EDL")
    monkeypatch.setattr(backup, "backup", lambda ctx, out, edl: None)
    monkeypatch.setattr(backup, "pack", lambda ctx, out: packed.append(out) or out.with_name("d.zip"))
    ctx = Context(runner=FakeRunner(), ui=FakeUI(), paths=Paths(tmp_path), state={"progress_id": "d"})
    plan.BackupStep().run(ctx)
    assert packed == [tmp_path / "backup" / "d"]
    assert ctx.state["backup_this_run"] is True
    assert any("d.zip" in l and "private" in l and "--name" in l for l in ctx.ui.lines)


def test_restore_intro_matches_how_long_it_takes():
    # Runs 4 and 5: 13 minutes from a folder (first downloads), under 10 from a zip.
    import inspect
    assert "about 10 minutes" in inspect.getsource(cli._restore)


def test_restore_explains_itself_before_unpacking_and_shows_the_check(tmp_path, monkeypatch):
    # Run 5: after unpacking, the checksum check ran with nothing on screen.
    from lhk import backup, relock
    ui = FakeUI()
    z = tmp_path / "display.zip"
    z.write_bytes(b"PK")
    (tmp_path / "u").mkdir()
    monkeypatch.setattr(cli, "_context", lambda args: Context(runner=FakeRunner(), ui=ui,
                                                              paths=Paths(tmp_path / "w"), state={}))
    monkeypatch.setattr(backup, "unpack", lambda ctx, f, dest: ui.lines.append("UNPACK") or tmp_path / "u")
    monkeypatch.setattr(backup, "verify_backup", lambda d: [])
    monkeypatch.setattr(cli, "fetch", lambda id_, ctx: None)
    monkeypatch.setattr(cli.Tools, "locate", staticmethod(lambda cache: "tools"))
    monkeypatch.setattr(cli, "Edl", lambda ctx: type("E", (), {"prepare": lambda self: None})())
    monkeypatch.setattr(relock, "stock_problems", lambda d: [])
    monkeypatch.setattr(cli, "wait_for_mode", lambda mode, ctx, **kw: None)
    monkeypatch.setattr(backup, "restore", lambda ctx, d, edl: None)
    monkeypatch.setattr(relock, "relock", lambda ctx, d: True)
    cli.main(["restore", str(z), "--workdir", str(tmp_path / "w")])
    intro = next(i for i, l in enumerate(ui.lines) if l.startswith("This puts the display back"))
    assert intro < ui.lines.index("UNPACK") < ui.lines.index("[busy] Checking the backup")


def test_setup_says_how_long_it_takes_on_a_fresh_start(tmp_path, monkeypatch):
    # Run 5: about 14 minutes with the backup, after the downloads.
    ui = FakeUI()
    monkeypatch.setattr(cli, "_context", lambda args: Context(runner=FakeRunner(), ui=ui,
                                                              paths=Paths(tmp_path), state={"progress_id": "d"}))
    monkeypatch.setattr(cli, "run_steps", lambda *a, **k: None)
    cli.main(["setup", "--workdir", str(tmp_path)])
    assert any("20 to 30 minutes" in l for l in ui.lines)
    (tmp_path / "progress").mkdir()
    (tmp_path / "progress" / "d.json").write_text('{"done": ["prerequisites"]}')
    ui.lines.clear()
    cli.main(["setup", "--workdir", str(tmp_path)])
    assert not any("20 to 30 minutes" in l for l in ui.lines)
