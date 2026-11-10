"""Run 3: four identical 'Waiting for the display to start' lines, one of
them for a restart that changed nothing."""
from pathlib import Path

from lhk import system
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI


def make_ctx(tmp_path, runner):
    c = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1")
    return c


BOOTED = ("-s", "S1", "shell", "getprop", "sys.boot_completed")


def test_wait_is_silent_when_the_display_is_already_up(tmp_path):
    ctx = make_ctx(tmp_path, FakeRunner({BOOTED: Result(0, "1\n")}))
    system.wait_booted(ctx)
    assert not any(l.startswith("[busy]") for l in ctx.ui.lines)


def test_wait_says_what_it_is_waiting_for(tmp_path, monkeypatch):
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, FakeRunner({BOOTED: [Result(0, "\n"), Result(0, "\n"), Result(0, "1\n")]}))
    system.wait_booted(ctx, why="the new system's first start")
    assert "[busy] Waiting for the new system's first start" in ctx.ui.lines


def _root_runner(verity_out):
    return FakeRunner({
        BOOTED: Result(0, "1\n"),
        ("-s", "S1", "disable-verity"): Result(0, verity_out),
    })


def test_root_step_skips_the_restart_when_verity_is_already_off(tmp_path, monkeypatch):
    rebooted = []
    monkeypatch.setattr(system, "reboot_and_wait", lambda ctx, **kw: rebooted.append(True))
    monkeypatch.setattr(system, "ensure_root_rw", lambda ctx: None)
    system.RootStep().run(make_ctx(tmp_path, _root_runner("Verity already disabled on /system\n")))
    assert rebooted == []


def test_root_step_restarts_when_disable_verity_changed_something(tmp_path, monkeypatch):
    rebooted = []
    monkeypatch.setattr(system, "reboot_and_wait", lambda ctx, **kw: rebooted.append(True))
    monkeypatch.setattr(system, "ensure_root_rw", lambda ctx: None)
    system.RootStep().run(make_ctx(tmp_path, _root_runner("Verity disabled on /system\nNow reboot your device for settings to take effect\n")))
    assert rebooted == [True]


def test_root_step_restarts_when_any_line_shows_a_change(tmp_path, monkeypatch):
    rebooted = []
    monkeypatch.setattr(system, "reboot_and_wait", lambda ctx, **kw: rebooted.append(True))
    monkeypatch.setattr(system, "ensure_root_rw", lambda ctx: None)
    out = "Verity already disabled on /system\nSuccessfully disabled verification on /vendor\n"
    system.RootStep().run(make_ctx(tmp_path, _root_runner(out)))
    assert rebooted == [True]
