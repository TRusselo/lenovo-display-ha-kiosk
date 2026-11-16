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


# --- run 8 requests: a clean start, readable notes, a bar on the live line -------------

CLEAR_ALL = "\x1b[3J"


def test_screen_clears_the_scrollback_too(tty):
    # The terminal's own banner (system info) shouldn't sit above the setup screen.
    UI(stdout=tty).screen(TITLES, 1, set())
    assert CLEAR_ALL in tty.getvalue()


def test_title_screen_clears_and_names_the_job(tty):
    UI(stdout=tty).title("Restore the stock software")
    text = tty.getvalue()
    assert text.startswith(CLEAR) and CLEAR_ALL in text
    assert "Restore the stock software" in plain(text) and "Lenovo Smart Display 8" in plain(text)


def test_title_without_a_terminal_clears_nothing():
    out = io.StringIO()
    UI(stdout=out).title("Restore the stock software")
    assert "\x1b[" not in out.getvalue()


def test_notes_and_waiting_steps_arent_the_dim_style(tty):
    # The terminal's dim style is dark grey: hard to read on black.
    ui = UI(stdout=tty)
    ui.screen(TITLES, 1, set())
    with ui.busy("Writing the backup to the display", interval=0.01) as job:
        job.note("34 of 55: oem_a", 34, 55)
        time.sleep(0.15)
    assert "\x1b[2m" not in tty.getvalue()


def test_a_counted_job_draws_a_bar(tty):
    with UI(stdout=tty).busy("Writing the backup to the display", interval=0.01) as job:
        job.note("27 of 54: oem_a", 27, 54)
        time.sleep(0.15)
    frame = plain(tty.getvalue()).split("\r")[-2]
    assert "█" in frame and "░" in frame and "27 of 54: oem_a" in frame


def test_restore_starts_with_a_title_screen(tmp_path, monkeypatch):
    from lhk import cli
    ui = FakeUI()
    ui.title = lambda text: ui.lines.append(f"[title] {text}")
    monkeypatch.setattr(cli, "_context", lambda args: Context(runner=FakeRunner(), ui=ui, paths=Paths(tmp_path)))
    (tmp_path / "bk").mkdir()
    monkeypatch.setattr(cli.backup, "verify_backup", lambda d: ["stop here"])
    cli.main(["restore", str(tmp_path / "bk"), "--workdir", str(tmp_path)])
    assert ui.lines[0].startswith("[title] ")


# --- run 8 findings ----------------------------------------------------------------

def test_wrapping_never_splits_a_path_or_link(tty, monkeypatch):
    import os
    import shutil
    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((60, 24)))
    ui = UI(stdout=tty)
    ui.screen(TITLES, 1, set())
    path = "/home/someone/git/lenovo-smart-display-assist/amber/e2e-run8-ux/backup/kiosk2.zip"
    url = "https://github.com/TRusselo/lenovo-display-ha-kiosk/blob/main/docs/SIZE.md"
    ui.alert(f"SAVE YOUR BACKUP: copy {path} somewhere safe.")
    ui.section("What's next", [f"Fit more on the screen: {url}"])
    shown = plain(tty.getvalue())
    assert path in shown and url in shown


def test_a_kept_message_survives_the_next_redraw(tty):
    ui = UI(stdout=tty)
    ui.screen(TITLES, 1, set())
    ui.keep("Time zone set to America/Edmonton. Don't pick a zone in the list again.")
    ui.screen(TITLES, 2, {1})
    after = plain(tty.getvalue().split("\x1b[3J")[-1])
    assert "Don't pick a zone in the list again" in after


def test_the_opening_note_stays_until_the_user_is_needed(tty):
    ui = UI(stdout=tty)
    ui.intro("Setup takes 20 to 30 minutes and needs 12 GB free.")
    ui.screen(TITLES, 1, set())
    ui.screen(TITLES, 2, {1})
    assert "12 GB" in plain(tty.getvalue().split("\x1b[3J")[-1])
    ui.physical("Hold VOLUME DOWN.")
    ui.screen(TITLES, 3, {1, 2})
    assert "12 GB" not in plain(tty.getvalue().split("\x1b[3J")[-1])


def test_buttons_to_press_are_bold(tty):
    UI(stdout=tty).physical("Hold VOLUME UP and VOLUME DOWN together, then press Enter.")
    text = tty.getvalue()
    assert re.search(r"\x1b\[[0-9;]*1[0-9;]*mVOLUME UP", text)
    assert re.search(r"\x1b\[[0-9;]*1[0-9;]*mVOLUME DOWN", text)
    assert re.search(r"\x1b\[[0-9;]*1[0-9;]*mEnter", text)


def test_a_long_question_wraps(tty, monkeypatch):
    import os
    import shutil
    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((50, 24)))
    tty.readline = lambda: "\n"
    ui = UI(stdin=tty, stdout=tty)
    ui.ask("The display's time zone is GMT. If your zone wasn't in the list, type its name "
           "(for example America/Edmonton), or press Enter to keep it: ")
    for line in plain(tty.getvalue()).splitlines():
        assert len(line) <= 50


def test_restore_title_doesnt_say_home_assistant(tty):
    UI(stdout=tty).title("Restore the stock software")
    assert "Home Assistant" not in plain(tty.getvalue())


def test_the_two_waits_have_different_names(tmp_path, monkeypatch):
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    runner = FakeRunner({BOOTED: [Result(1, ""), Result(1, ""), Result(0, "1\n")], WAIT: Result(0, "")})
    ctx = sys_ctx(tmp_path, runner, [])
    system.wait_booted(ctx, why="the new system's first start")
    waits = [l for l in ctx.ui.lines if l.startswith("[busy]")]
    assert len(waits) == len(set(waits)) == 2


def test_wifi_and_time_zone_instructions_are_a_display_box(tmp_path, monkeypatch):
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    runner = FakeRunner({("-s", "S1", "shell", "ip", "-4", "addr", "show", "wlan0"):
                         Result(0, "    inet 10.0.0.5/24 brd 10.0.0.255 scope global wlan0\n")})
    ctx = sys_ctx(tmp_path, runner, [""])
    system.OpenThingsSettingsStep().run(ctx)
    box = next(l for l in ctx.ui.lines if l.startswith("[physical]"))
    assert "Date & time" in box and "Networks" in box


def test_volume_buttons_are_asked_for_in_display_boxes(tmp_path, monkeypatch):
    from lhk import bootfix
    vols = iter([0, 5, 5, 0])
    monkeypatch.setattr(bootfix, "_volume", lambda ctx: next(vols))
    monkeypatch.setattr(bootfix.time, "sleep", lambda s: None)
    ctx = sys_ctx(tmp_path, FakeRunner(), [])
    bootfix.check_buttons(ctx)
    boxes = [l for l in ctx.ui.lines if l.startswith("[physical]")]
    assert any("VOLUME UP" in b for b in boxes) and any("VOLUME DOWN" in b for b in boxes)


def test_second_replug_suggests_a_usb_a_port_and_cable(tmp_path, monkeypatch):
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    t = subprocess.TimeoutExpired("adb", 300)
    runner = FakeRunner({BOOTED: [Result(1, ""), Result(0, "1\n")], WAIT: [t, t, Result(0, "")]})
    ctx = sys_ctx(tmp_path, runner, ["", ""])
    system.wait_booted(ctx)
    boxes = [l for l in ctx.ui.lines if l.startswith("[physical]")]
    assert "USB-A" not in boxes[0] and "USB-A" in boxes[1]
