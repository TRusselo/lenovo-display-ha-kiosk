"""The live setup screen (2026-11-15): on a terminal, each step clears the screen
and redraws a title, a progress bar and the step list; repeated jobs share one
live line. Without a terminal the output stays plain and scrolls. Plus the
findings from end-to-end run 7."""
import io
import re
import subprocess
import time
from pathlib import Path

import pytest

from lhk import modes, plan, steps, system
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths, Step, run_steps
from lhk.ui import UI
from tests.fakes import FakeRunner, FakeUI

CLEAR = "\x1b[H\x1b[2J"
TITLES = ["Back up the stock display", "Unlock verified boot", "Flash the userdebug build"]


class _Tty(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def tty(monkeypatch):
    import lhk.ui
    monkeypatch.setattr(lhk.ui, "_windows_vt_on", lambda: True)
    monkeypatch.setattr(lhk.ui, "_old_windows_console", lambda: False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    return _Tty()


def plain(text):
    return re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", text)


# --- the screen ----------------------------------------------------------------

def test_screen_clears_and_draws_the_title_bar_and_step_list(tty):
    UI(stdout=tty).screen(TITLES, 2, {1})
    text = tty.getvalue()
    assert text.startswith(CLEAR)
    shown = plain(text)
    assert "Lenovo Smart Display 8" in shown and "Home Assistant" in shown
    assert "1/3" in shown
    assert "✓ Back up the stock display" in shown
    assert "▸ Unlock verified boot" in shown
    assert "· Flash the userdebug build" in shown


def test_screen_uses_purple_and_cyan_not_green(tty):
    UI(stdout=tty).screen(TITLES, 2, {1})
    text = tty.getvalue()
    assert "38;5;141m" in text                             # purple, fixed: not the remappable magenta
    assert "\x1b[1;38;5;80m" in text                        # cyan: the current step
    assert "\x1b[32m" not in text and "\x1b[35m" not in text
    assert "\x1b[31m" not in text                           # red is for errors only


def test_done_screen_fills_the_bar_and_ticks_every_step(tty):
    UI(stdout=tty).screen(TITLES, 4, {1, 2, 3})
    shown = plain(tty.getvalue())
    assert "3/3" in shown and "░" not in shown
    assert shown.count("✓") == 3 and "▸" not in shown


def test_screen_without_a_terminal_scrolls_with_a_plain_step_line():
    out = io.StringIO()
    ui = UI(stdout=out)
    ui.screen(TITLES, 1, set())
    ui.screen(TITLES, 2, {1})
    text = out.getvalue()
    assert "\x1b[" not in text
    assert "Step 1 of 3: Back up the stock display" in text
    assert "Step 2 of 3: Unlock verified boot" in text
    assert text.count("Flash the userdebug build") == 1     # the list, once, at the start


def test_screen_on_an_old_windows_console_stays_plain(monkeypatch):
    import lhk.ui
    monkeypatch.setattr(lhk.ui, "_windows_vt_on", lambda: True)
    monkeypatch.setattr(lhk.ui, "_old_windows_console", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = _Tty()
    UI(stdout=out).screen(TITLES, 2, {1})
    assert CLEAR not in out.getvalue()


# --- jobs ------------------------------------------------------------------------

def test_a_job_shows_its_note_and_ends_with_its_own_summary(tty):
    with UI(stdout=tty).busy("Backing up the display", interval=0.01) as job:
        job.note("12 of 55: system_a")
        time.sleep(0.15)
        job.done("Backed up 55 partitions")
    text = plain(tty.getvalue())
    assert "12 of 55: system_a" in text
    last = text.rstrip("\n").split("\r")[-1]
    assert "✓ Backed up 55 partitions" in last


def test_a_job_without_a_terminal_still_yields_a_job():
    out = io.StringIO()
    with UI(stdout=out).busy("Backing up the display", interval=10) as job:
        job.note("1 of 2: boot_a")
        job.done("Backed up 2 partitions")
    assert "done" in out.getvalue()


# --- prompts --------------------------------------------------------------------

def test_display_box_on_a_terminal_is_yellow_with_no_bars(tty):
    UI(stdout=tty).physical("Hold the volume-down button.")
    text = tty.getvalue()
    assert "\x1b[1;33m" in text and "====" not in text
    assert "▶ On the display" in plain(text)
    assert "Hold the volume-down button." in plain(text)


def test_display_box_wraps_to_the_terminal(tty, monkeypatch):
    import os
    import shutil
    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((40, 24)))
    UI(stdout=tty).physical("word " * 30)
    for line in plain(tty.getvalue()).splitlines():
        assert len(line) <= 40


# --- the step runner ---------------------------------------------------------------

class Rec(Step):
    def __init__(self, name):
        self.name = self.title = name

    def run(self, ctx):
        pass


def make_ctx(tmp_path):
    return Context(runner=None, ui=FakeUI(), paths=Paths(tmp_path), state={"serial": "T1"})


def test_run_steps_redraws_the_screen_per_step_and_once_when_done(tmp_path):
    ctx = make_ctx(tmp_path)
    run_steps([Rec("a"), Rec("b")], ctx)
    screens = [l for l in ctx.ui.lines if l.startswith("[screen")]
    assert screens == ["[screen 1/2] a:todo b:todo", "[screen 2/2] a:done b:todo",
                       "[screen 3/2] a:done b:done"]


def test_closing_words_come_after_the_done_screen(tmp_path):
    class Last(Rec):
        def run(self, ctx):
            ctx.after.append(lambda: ctx.ui.say("All done."))
    ctx = make_ctx(tmp_path)
    run_steps([Rec("a"), Last("b")], ctx)
    assert ctx.ui.lines.index("[screen 3/2] a:done b:done") < ctx.ui.lines.index("All done.")


def test_final_check_saves_its_closing_words_for_after_the_done_screen(tmp_path, monkeypatch):
    from lhk import bootfix, kiosk
    monkeypatch.setattr(plan, "check_adb_identity",
                        lambda ctx, s: type("I", (), {"is_target_build": True})())
    monkeypatch.setattr(bootfix, "verify", lambda ctx, **kw: [])
    monkeypatch.setattr(kiosk, "is_device_owner", lambda ctx: True)
    monkeypatch.setattr(system, "serial", lambda ctx: "T1")
    monkeypatch.setattr(system, "wifi_ip", lambda ctx: "10.0.0.50")
    ctx = make_ctx(tmp_path)
    plan.VerifyStep().run(ctx)
    assert not any("What's next" in l for l in ctx.ui.lines)
    for fn in ctx.after:
        fn()
    assert any(l.startswith("[section] What's next") for l in ctx.ui.lines)


# --- findings from run 7 -------------------------------------------------------

def test_adb_over_wifi_isnt_a_second_display(tmp_path):
    # A Smart Clock on adb over Wi-Fi stopped the restore: "unplug everything".
    runner = FakeRunner({("devices",): Result(0, "List of devices attached\nHUA05TEST\tdevice\n"
                                                 "10.0.0.46:5555\tdevice\n")})
    found = modes.detect(runner, Tools(adb=Path("adb"), fastboot=Path("fastboot")), usb_scan=lambda: [])
    assert [s for m, s in found if m == modes.Mode.ADB] == ["HUA05TEST"]


@pytest.mark.parametrize("size,shown", [(704 * 1024 ** 2, "704 MB"), (300 * 1024, "300 KB"),
                                        (8 * 1024 ** 2 + 10, "8 MB")])
def test_download_sizes_never_say_zero(size, shown):
    from lhk.downloads import human_size
    assert human_size(size) == shown


def test_download_shows_how_much_has_arrived(tmp_path, monkeypatch):
    from lhk import downloads
    data = b"x" * 3 * 1024 * 1024

    def fake_download(url, part, ui=None, progress=None):
        part.parent.mkdir(parents=True, exist_ok=True)
        part.write_bytes(data)
        progress(len(data) // 2)

    monkeypatch.setattr(downloads, "_download", fake_download)
    import hashlib
    manifest = {"f": {"url": "https://example.test/f.bin", "sha256": hashlib.sha256(data).hexdigest(),
                      "size": len(data), "unpack": None, "platform": None}}
    ctx = Context(runner=None, ui=FakeUI(), paths=Paths(tmp_path), state={"manifest": manifest})
    downloads.fetch("f", ctx)
    assert "[note] 2 of 3 MB, 50%" in ctx.ui.lines


def test_setup_says_how_much_free_space_it_needs(tmp_path, monkeypatch):
    from lhk import cli
    ui = FakeUI()
    monkeypatch.setattr(cli, "_context", lambda args: Context(runner=FakeRunner(), ui=ui,
                                                              paths=Paths(tmp_path), state={"progress_id": "d"}))
    monkeypatch.setattr(cli, "run_steps", lambda *a, **kw: None)
    cli.main(["setup", "--workdir", str(tmp_path)])
    assert any("12 GB" in l for l in ui.lines)


def test_nothing_found_hint_covers_a_blank_screen():
    assert "blank" in modes.NOTHING_HINT and "Lenovo logo" in modes.NOTHING_HINT


def test_whats_next_links_the_screen_size_page(tmp_path, monkeypatch):
    from lhk import bootfix, kiosk
    monkeypatch.setattr(plan, "check_adb_identity",
                        lambda ctx, s: type("I", (), {"is_target_build": True})())
    monkeypatch.setattr(bootfix, "verify", lambda ctx, **kw: [])
    monkeypatch.setattr(kiosk, "is_device_owner", lambda ctx: True)
    monkeypatch.setattr(system, "serial", lambda ctx: "T1")
    monkeypatch.setattr(system, "wifi_ip", lambda ctx: "10.0.0.50")
    ctx = make_ctx(tmp_path)
    plan.VerifyStep().run(ctx)
    for fn in ctx.after:
        fn()
    assert any("docs/SIZE.md" in l for l in ctx.ui.lines if l.startswith("[section]"))


# --- no USB after the first start: ask for a replug, don't give up ------------------

BOOTED = ("-s", "S1", "shell", "getprop", "sys.boot_completed")
WAIT = ("-s", "S1", "wait-for-device")


def sys_ctx(tmp_path, runner, answers):
    c = Context(runner=runner, ui=FakeUI(answers=answers), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1")
    return c


def test_no_usb_asks_for_a_replug_then_carries_on(tmp_path, monkeypatch):
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    runner = FakeRunner({BOOTED: [Result(1, ""), Result(0, "1\n")],
                         WAIT: [subprocess.TimeoutExpired("adb", 300), Result(0, "")]})
    ctx = sys_ctx(tmp_path, runner, [""])
    system.wait_booted(ctx)
    replug = [l for l in ctx.ui.lines if l.startswith("[physical]")]
    assert replug and "USB cable" in replug[0] and "count to 3" in replug[0]
    assert sum(1 for c in runner.calls if c[3:4] == ["wait-for-device"]) == 2


def test_no_usb_stops_when_the_user_types_stop(tmp_path):
    runner = FakeRunner({BOOTED: Result(1, ""), WAIT: subprocess.TimeoutExpired("adb", 300)})
    ctx = sys_ctx(tmp_path, runner, ["stop"])
    with pytest.raises(system.SetupFailed, match="run the same command again"):
        system.wait_booted(ctx)
