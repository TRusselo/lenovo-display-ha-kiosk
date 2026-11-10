import json

import pytest

from lhk import log
from lhk.steps import Context, Paths, Step, run_steps


class Recorder(Step):
    def __init__(self, name, ran, *, already=False, fail=False):
        self.name = name
        self.title = name
        self.ran = ran
        self.already = already
        self.fail = fail

    def done(self, ctx):
        return self.already

    def run(self, ctx):
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        self.ran.append(self.name)


def make_ctx(root):
    return Context(runner=None, ui=None, paths=Paths(root), state={"serial": "TEST01"})


def progress(ctx):
    return json.loads((ctx.paths.progress / "TEST01.json").read_text(encoding="utf-8"))


def test_skips_steps_marked_done(tmp_path):
    ctx = make_ctx(tmp_path)
    ran = []
    run_steps([Recorder("a", ran), Recorder("b", ran)], ctx)
    ran.clear()
    run_steps([Recorder("a", ran), Recorder("b", ran), Recorder("c", ran)], ctx)
    assert ran == ["c"]


def test_skips_when_step_done_returns_true(tmp_path):
    ctx = make_ctx(tmp_path)
    ran = []
    run_steps([Recorder("unlock", ran, already=True), Recorder("flash", ran)], ctx)
    assert ran == ["flash"]
    assert progress(ctx)["done"] == ["unlock", "flash"]


def test_start_from_marks_earlier_steps_done(tmp_path):
    ctx = make_ctx(tmp_path)
    ran = []
    run_steps([Recorder("a", ran), Recorder("b", ran), Recorder("c", ran)], ctx, start_from="c")
    assert ran == ["c"]
    assert progress(ctx)["done"] == ["a", "b", "c"]


def test_start_from_unknown_step_raises(tmp_path):
    with pytest.raises(ValueError):
        run_steps([Recorder("a", [])], make_ctx(tmp_path), start_from="nope")


def test_restart_clears_progress(tmp_path):
    ctx = make_ctx(tmp_path)
    ran = []
    run_steps([Recorder("a", ran)], ctx)
    ran.clear()
    run_steps([Recorder("a", ran)], ctx, restart=True)
    assert ran == ["a"]


def test_failure_keeps_earlier_progress(tmp_path):
    ctx = make_ctx(tmp_path)
    ran = []
    with pytest.raises(RuntimeError):
        run_steps([Recorder("a", ran), Recorder("b", ran, fail=True), Recorder("c", ran)], ctx)
    assert progress(ctx)["done"] == ["a"]
    ran.clear()
    run_steps([Recorder("a", ran), Recorder("b", ran), Recorder("c", ran)], ctx)
    assert ran == ["b", "c"]


def test_dry_run_runs_nothing_and_saves_nothing(tmp_path):
    ctx = make_ctx(tmp_path)
    ctx.dry_run = True
    ran = []
    run_steps([Recorder("a", ran)], ctx)
    assert ran == []
    assert not (ctx.paths.progress / "TEST01.json").exists()


def test_paths_with_spaces_and_unicode(tmp_path):
    ctx = make_ctx(tmp_path / "José Smith" / "x y")
    ran = []
    run_steps([Recorder("a", ran)], ctx)
    assert ran == ["a"]
    assert progress(ctx)["done"] == ["a"]
    for p in (ctx.paths.cache, ctx.paths.backup, ctx.paths.logs, ctx.paths.progress):
        assert str(p).startswith(str(tmp_path / "José Smith" / "x y"))


def test_redact_masks_passwords():
    text = '{"password": "hunter2", "token": "abc.def", "user": "ok"} psk=secret1'
    out = log.redact(text)
    for secret in ("hunter2", "abc.def", "secret1"):
        assert secret not in out
    assert '"user": "ok"' in out


def test_log_setup_writes_redacted_file(tmp_path):
    logger = log.setup(tmp_path / "logs" / "run.log")
    logger.info('login {"password": "hunter2"}')
    for h in logger.handlers:
        h.flush()
    text = (tmp_path / "logs" / "run.log").read_text(encoding="utf-8")
    assert "login" in text and "hunter2" not in text


def test_resume_says_where_it_picks_up(tmp_path):
    # Run 3: a rerun went straight to "Installing Kiosk Satellite" with no word why.
    from tests.fakes import FakeUI
    ctx = make_ctx(tmp_path)
    ran = []
    with pytest.raises(RuntimeError):
        run_steps([Recorder("a", ran), Recorder("b", ran, fail=True)], ctx)
    ctx.ui = FakeUI()
    run_steps([Recorder("a", ran), Recorder("b", ran)], ctx)
    assert ctx.ui.lines[0] == "Picking up where the last run stopped, at: b (1 of 2 steps done)."


def test_first_run_says_nothing_about_resuming(tmp_path):
    from tests.fakes import FakeUI
    ctx = make_ctx(tmp_path)
    ctx.ui = FakeUI()
    run_steps([Recorder("a", []), Recorder("b", [])], ctx)
    assert not any("Picking up" in l for l in ctx.ui.lines)


def test_step_already_on_the_display_is_named(tmp_path):
    from tests.fakes import FakeUI
    ctx = make_ctx(tmp_path)
    ctx.ui = FakeUI()
    run_steps([Recorder("a", [], already=True)], ctx)
    assert "Already done on the display: a." in ctx.ui.lines
