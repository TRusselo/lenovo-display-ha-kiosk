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
