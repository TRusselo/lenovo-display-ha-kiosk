import io
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
            assert f.name == "system.py", f"{f.name}:{line} asks without choose()"


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
    assert text.endswith("s)\n")          # "... (0s)"
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
    assert "DO THIS ON THE DISPLAY" in out.getvalue() and "\x1b[" in out.getvalue()
    plain = io.StringIO()
    UI(stdout=plain).physical("Hold the volume-down button.")
    assert "\x1b[" not in plain.getvalue() and "DO THIS ON THE DISPLAY:" in plain.getvalue()


def test_section_prints_a_title_and_its_lines():
    out = io.StringIO()
    UI(stdout=out).section("What's next", ["one", "two"])
    text = out.getvalue()
    assert "What's next" in text and "one" in text and "two" in text
    assert text.index("What's next") < text.index("one") < text.index("two")
