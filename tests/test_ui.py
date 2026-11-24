import io
import re
import os
import time

import pytest

from lhk.ui import UI


def test_busy_prints_dots_while_working_then_done():
    out = io.StringIO()
    with UI(stdout=out).busy("Writing boot_a (1 of 5)", interval=0.01):
        time.sleep(0.1)
    text = out.getvalue()
    assert text.startswith("Writing boot_a (1 of 5)")
    assert ".." in text
    assert text.endswith(" done\n")


def test_busy_says_stopped_when_the_work_fails():
    out = io.StringIO()
    with pytest.raises(ValueError):
        with UI(stdout=out).busy("Writing boot_a", interval=10):
            raise ValueError("lost the display")
    assert out.getvalue().endswith(" stopped\n")


class _Tty(io.StringIO):
    def isatty(self):
        return True


def test_alert_is_coloured_on_a_terminal(monkeypatch):
    # CI's Windows runner has no real console to switch to colour mode.
    import lhk.ui
    monkeypatch.setattr(lhk.ui, "_windows_vt_on", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = _Tty()
    UI(stdout=out).alert("NOT DONE YET")
    assert "\x1b[" in out.getvalue() and "NOT DONE YET" in out.getvalue()


def test_alert_is_plain_when_not_a_terminal_or_no_color(monkeypatch):
    out = io.StringIO()
    UI(stdout=out).alert("NOT DONE YET")
    assert out.getvalue() == "\nNOT DONE YET\n"
    monkeypatch.setenv("NO_COLOR", "1")
    tty = _Tty()
    UI(stdout=tty).alert("NOT DONE YET")
    assert "\x1b[" not in tty.getvalue()


# Run 6: a mistyped word ("lcok") must ask again, never count as an answer.
from lhk.ui import choose
from tests.fakes import FakeUI


def test_choose_word_or_enter():
    assert choose(FakeUI(["lock"]), "Type lock: ", "lock") is True
    assert choose(FakeUI([" LOCK "]), "Type lock: ", "lock") is True
    assert choose(FakeUI([""]), "Type lock: ", "lock") is False


def test_choose_asks_again_after_a_typo():
    ui = FakeUI(["lcok", "lokc", "lock"])
    assert choose(ui, "Type lock: ", "lock") is True
    assert sum(l.startswith("[ask]") for l in ui.lines) == 3
    assert any('"lcok"' in l and "isn't an answer" in l for l in ui.lines)


def test_every_yes_no_prompt_goes_through_choose():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "lhk"
    for f in root.glob("*.py"):
        if f.name == "ui.py":
            continue
        for m in re.finditer(r"ui\.ask\(", f.read_text()):
            line = f.read_text()[:m.start()].count("\n") + 1
            # Free-text questions only (Wi-Fi names, addresses): yes/no ones go through choose().
            assert f.name in ("system.py", "wifi.py", "staticip.py"), f"{f.name}:{line} asks without choose()"


# Setup output polish (2026-11-12): step header, spinner, result marks, boxes.
# On a terminal it uses colour and symbols; piped or redirected, it stays plain,
# and nothing may crash on a console that can't encode the symbols.

def _cp1252():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")


def _text(stream):
    stream.flush()
    return stream.buffer.getvalue().decode("cp1252")


class _Cp1252Tty(io.TextIOWrapper):
    def isatty(self):
        return True


def _vt_on(monkeypatch):
    import lhk.ui
    monkeypatch.setattr(lhk.ui, "_windows_vt_on", lambda: True)
    monkeypatch.delenv("NO_COLOR", raising=False)


def test_new_output_never_crashes_on_a_cp1252_console(monkeypatch):
    # Windows with output piped or redirected: ✓, █ and the spinner aren't in cp1252.
    _vt_on(monkeypatch)
    for out in (_cp1252(), _Cp1252Tty(io.BytesIO(), encoding="cp1252", newline="")):
        ui = UI(stdout=out)
        ui.overview([("Back up the display", True), ("Unlock", False)])
        ui.header(4, 15, "Unlock")
        ui.ok("Unlock")
        ui.physical("Hold the volume-down button.")
        ui.section("What's next", ["Read docs/SCREEN.md"])
        with ui.busy("Flashing boot_a", interval=0.01):
            time.sleep(0.05)
        text = _text(out)
        assert "Unlock" in text and "Flashing boot_a" in text


def test_header_numbers_the_step_and_draws_a_bar():
    out = io.StringIO()
    UI(stdout=out).header(5, 15, "Flash the userdebug build")
    text = out.getvalue()
    assert "Step 5 of 15: Flash the userdebug build" in text
    assert "[" in text and "]" in text


def test_overview_lists_every_step_and_marks_the_done_ones():
    out = io.StringIO()
    UI(stdout=out).overview([("Back up the display", True), ("Unlock", False)])
    lines = out.getvalue().splitlines()
    done = next(l for l in lines if "Back up the display" in l)
    todo = next(l for l in lines if "Unlock" in l)
    assert done != todo.replace("Unlock", "Back up the display")  # different marks


def test_ok_marks_a_finished_step():
    out = io.StringIO()
    UI(stdout=out).ok("Unlock")
    assert out.getvalue().strip().endswith("Unlock")
    assert out.getvalue().strip() != "Unlock"


def test_busy_on_a_terminal_spins_and_says_how_long_it_took(monkeypatch):
    _vt_on(monkeypatch)
    out = _Tty()
    with UI(stdout=out).busy("Flashing boot_a", interval=0.01):
        time.sleep(0.1)
    text = out.getvalue()
    assert "\r" in text and "Flashing boot_a" in text
    assert re.sub(r"\x1b\[[0-9;]*m", "", text).endswith("s)\n")          # "... (0s)"
    assert "\x1b[" in text


def test_busy_on_a_terminal_marks_a_failure(monkeypatch):
    _vt_on(monkeypatch)
    out = _Tty()
    with pytest.raises(ValueError):
        with UI(stdout=out).busy("Flashing boot_a", interval=10):
            raise ValueError("lost the display")
    assert "stopped" in out.getvalue()


def test_physical_box_keeps_its_words_and_is_coloured_on_a_terminal(monkeypatch):
    _vt_on(monkeypatch)
    out = _Tty()
    UI(stdout=out).physical("Hold the volume-down button.")
    assert "On the display" in out.getvalue() and "\x1b[" in out.getvalue()
    plain = io.StringIO()
    UI(stdout=plain).physical("Hold the volume-down button.")
    assert "\x1b[" not in plain.getvalue() and "DO THIS ON THE DISPLAY:" in plain.getvalue()


def test_section_prints_a_title_and_its_lines():
    out = io.StringIO()
    UI(stdout=out).section("What's next", ["one", "two"])
    text = out.getvalue()
    assert "What's next" in text and "one" in text and "two" in text
    assert text.index("What's next") < text.index("one") < text.index("two")


def test_spinner_line_fits_a_narrow_terminal(monkeypatch):
    # A wrapped line can't be redrawn with \r: every tick would leave a new line behind.
    import re
    import shutil
    _vt_on(monkeypatch)
    monkeypatch.setattr(shutil, "get_terminal_size", lambda fallback=(80, 24): os.terminal_size((40, 24)))
    out = _Tty()
    label = "Downloading " + "x" * 100 + ".zip (704 MB)"
    with UI(stdout=out).busy(label, interval=0.01):
        time.sleep(0.05)
    frames = out.getvalue().split("\r")[1:-1]          # the spinner frames, not the final line
    assert frames
    for f in frames:
        assert len(re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", f)) <= 39


def test_old_windows_console_gets_plain_symbols(monkeypatch):
    # Windows 10's console fonts have no Braille, check marks or arrows; Windows Terminal does.
    import lhk.ui
    monkeypatch.setattr(lhk.ui, "_old_windows_console", lambda: True)
    out = io.StringIO()
    UI(stdout=out).ok("Unlock")
    assert "[x] Unlock" in out.getvalue()
    monkeypatch.setattr(lhk.ui, "_old_windows_console", lambda: False)
    out = io.StringIO()
    UI(stdout=out).ok("Unlock")
    assert "✓ Unlock" in out.getvalue()


# Links and addresses stand out (from the clock tool): cyan and underlined, so people see they can click them.
LINK = "\x1b[4;38;5:80m".replace(":", ";")


def test_links_in_whats_next_are_coloured(monkeypatch):
    import lhk.ui
    monkeypatch.setattr(lhk.ui, "_windows_vt_on", lambda: True)     # CI's Windows runner has no real console
    monkeypatch.setattr(lhk.ui, "_old_windows_console", lambda: False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = _Tty()
    UI(stdout=out).section("What's next", ["Change Kiosk Satellite's settings from a browser: http://10.1.1.40:2324",
                                           "Fit more on the screen: docs/SIZE.md (in the download, or "
                                           "https://github.com/TRusselo/lenovo-display-ha-kiosk/blob/main/docs/SIZE.md)"])
    text = out.getvalue()
    assert f"{LINK}http://10.1.1.40:2324\x1b[0m" in text
    assert f"{LINK}https://github.com/TRusselo/lenovo-display-ha-kiosk/blob/main/docs/SIZE.md\x1b[0m" in text


def test_the_browser_address_for_kiosk_satellites_setup_is_coloured(monkeypatch):
    import lhk.ui
    monkeypatch.setattr(lhk.ui, "_windows_vt_on", lambda: True)     # CI's Windows runner has no real console
    monkeypatch.setattr(lhk.ui, "_old_windows_console", lambda: False)
    monkeypatch.delenv("NO_COLOR", raising=False)
    out = _Tty()
    UI(stdout=out).say("Easier in a browser, for pasting your address and token:\n  http://10.1.1.40:2324")
    assert f"{LINK}http://10.1.1.40:2324\x1b[0m" in out.getvalue()


def test_links_stay_plain_without_a_terminal():
    out = io.StringIO()
    UI(stdout=out).section("What's next", ["Settings: http://10.1.1.40:2324"])
    assert "\x1b" not in out.getvalue() and "http://10.1.1.40:2324" in out.getvalue()
