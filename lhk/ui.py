"""What the user sees and types. Plain words; physical steps stand out."""
from __future__ import annotations

import contextlib
import os
import shutil
import sys
import textwrap
import threading
import time


def _windows_vt_on() -> bool:
    """Windows consoles show colour codes only with virtual-terminal mode on."""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not k.GetConsoleMode(h, ctypes.byref(mode)):
            return False
        return bool(k.SetConsoleMode(h, mode.value | 0x0004))
    except Exception:
        return False


# Symbols, with plain-ASCII stand-ins for consoles that can't show them
# (Windows with output piped or redirected uses cp1252).
_FANCY = {"ok": "\u2713", "todo": "\u00b7", "fail": "\u2717", "full": "\u2588", "empty": "\u2591",
          "spin": "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f", "arrow": "\u25b6",
          "now": "\u25b8", "to": "\u2192"}
_PLAIN = {"ok": "[x]", "todo": "[ ]", "fail": "[!]", "full": "#", "empty": "-", "spin": "|/-\\",
          "arrow": ">", "now": ">", "to": "->"}

# Purple and cyan for the screen itself, yellow for anything the user has to do,
# red only for errors. Purple and cyan come from the fixed 256-colour palette:
# colour schemes remap the basic magenta, and some draw it red.
_BOLD, _PURPLE, _TITLE, _YELLOW, _RED, _CYAN, _NOW, _DIM, _RESET = (
    "\x1b[1m", "\x1b[38;5;141m", "\x1b[1;38;5;141m", "\x1b[1;33m", "\x1b[31m", "\x1b[38;5;80m",
    "\x1b[1;38;5;80m", "\x1b[2m", "\x1b[0m")
CLEAR = "\x1b[H\x1b[2J"
TITLE = "Lenovo Smart Display 8 {to} Home Assistant"


def _old_windows_console() -> bool:
    """Windows' classic console window, whose fonts lack these symbols. Windows Terminal sets WT_SESSION."""
    return os.name == "nt" and not os.environ.get("WT_SESSION")


def _elapsed(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60}m {s % 60:02d}s" if s >= 60 else f"{s}s"


class UI:
    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self._status_shown = False
        self._sym = None
        self._col = None
        self._listed = False
        self._intro = []

    def _symbols(self) -> dict:
        if self._sym is None and _old_windows_console():
            self._sym = _PLAIN
        if self._sym is None:
            enc = getattr(self.stdout, "encoding", None) or "utf-8"
            try:
                "".join(_FANCY.values()).encode(enc)
                self._sym = _FANCY
            except (UnicodeEncodeError, LookupError):
                self._sym = _PLAIN
        return self._sym

    def _paint(self, code: str, text: str) -> str:
        return f"{code}{text}{_RESET}" if self._colour() else text

    def _end_status(self):
        if self._status_shown:
            self.stdout.write("\n")
            self._status_shown = False

    def _wrap(self, text: str, indent: str = "  ") -> str:
        """Indented to line up with the screen; long lines wrapped. Lines already laid out
        (starting with a space, such as a numbered list or an address) only get the indent."""
        width = max(min(shutil.get_terminal_size((80, 24)).columns, 100) - len(indent), 20)
        out = []
        for line in text.split("\n"):
            if line.startswith(" ") or not line:
                out.append(indent + line)
            else:
                out += [indent + l for l in textwrap.wrap(line, width)]
        return "\n".join(out)

    def say(self, text: str) -> None:
        self._end_status()
        if self._live():
            text = self._wrap(text)
        self.stdout.write(f"{text}\n")
        self.stdout.flush()

    def physical(self, text: str) -> None:
        """Something to do with your hands, at the display."""
        self._end_status()
        if self._colour():
            head = self._paint(_YELLOW, f"{self._symbols()['arrow']} On the display")
            width = min(shutil.get_terminal_size((80, 24)).columns, 100) - 4
            body = "\n".join("    " + l for l in textwrap.wrap(text, max(width, 20)))
            self.stdout.write(f"\n  {head}\n{body}\n")
        else:
            bar = "=" * 72
            self.stdout.write(f"\n{bar}\n  DO THIS ON THE DISPLAY:\n  {text}\n{bar}\n")
        self.stdout.flush()

    def intro(self, text: str) -> None:
        """Words for the top of the next screen. Without a terminal: shown now."""
        if self._live():
            self._intro.append(text)
        else:
            self.say(text)

    def _live(self) -> bool:
        """The redrawn screen: a terminal that takes colour, and isn't Windows' classic console."""
        return self._colour() and not _old_windows_console()

    def screen(self, titles, current: int, done) -> None:
        """The setup screen at the start of step `current` (1-based; past the end: all done).
        On a terminal: cleared and redrawn. Otherwise: the list once, then a line per step."""
        self._end_status()
        total = len(titles)
        if not self._live():
            if not self._listed:
                self.overview([(t, i in done) for i, t in enumerate(titles, 1)])
                self._listed = True
            if current <= total:
                self.stdout.write(f"\nStep {current} of {total}: {titles[current - 1]}\n")
                self.stdout.flush()
            return
        sym = self._symbols()
        width = 32
        count = len(done)
        filled = width if current > total else round(width * count / total) if total else 0
        out = [CLEAR, "\n  " + self._paint(_TITLE, TITLE.format(to=sym["to"])) + "\n\n",
               "  " + self._paint(_PURPLE, sym["full"] * filled) + self._paint(_DIM, sym["empty"] * (width - filled))
               + "  " + self._paint(_DIM, f"{count}/{total}") + "\n\n"]
        for i, t in enumerate(titles, 1):
            if i == current:
                out.append("  " + self._paint(_NOW, f"{sym['now']} {t}") + "\n")
            elif i in done:
                out.append(f"  {self._paint(_CYAN, sym['ok'])} {self._paint(_DIM, t)}\n")
            else:
                out.append("  " + self._paint(_DIM, f"{sym['todo']} {t}") + "\n")
        out.append("\n")
        width = min(shutil.get_terminal_size((80, 24)).columns, 100) - 2
        for text in self._intro:
            out.append("\n".join("  " + l for l in textwrap.wrap(text, max(width, 20))) + "\n\n")
        self._intro = []
        self.stdout.write("".join(out))
        self.stdout.flush()

    def overview(self, steps) -> None:
        """Every step, with the finished ones marked. steps: (title, done) pairs."""
        self._end_status()
        sym = self._symbols()
        self.stdout.write("\nThe steps:\n")
        for i, (title, done) in enumerate(steps, 1):
            mark = self._paint(_CYAN, sym["ok"]) if done else sym["todo"]
            self.stdout.write(f"  {mark} {i:>2}. {title}\n")
        self.stdout.flush()

    def header(self, index: int, total: int, title: str) -> None:
        """The start of a step: a progress bar and its number, matching the manual's headings."""
        self._end_status()
        sym = self._symbols()
        width = 20
        filled = round(width * (index - 1) / total) if total else 0
        bar = f"[{sym['full'] * filled}{sym['empty'] * (width - filled)}]"
        self.stdout.write(f"\n{self._paint(_PURPLE, bar)} {self._paint(_BOLD, f'Step {index} of {total}: {title}')}\n")
        self.stdout.flush()

    def ok(self, text: str) -> None:
        """A finished step."""
        self._end_status()
        self.stdout.write(f"  {self._paint(_CYAN, self._symbols()['ok'])} {text}\n")
        self.stdout.flush()

    def section(self, title: str, lines) -> None:
        """A heading with indented lines under it, e.g. what to do next."""
        self._end_status()
        if self._live():
            self.stdout.write(f"\n  {self._paint(_TITLE, title)}\n")
            for line in lines:
                self.stdout.write(self._wrap(line, "    ").replace("    ", f"  {self._paint(_PURPLE, self._symbols()['todo'])} ", 1) + "\n")
            self.stdout.flush()
            return
        self.stdout.write(f"\n{self._paint(_TITLE, title)}\n")
        for line in lines:
            self.stdout.write(f"  - {line}\n")
        self.stdout.flush()

    def _colour(self) -> bool:
        if self._col is None:
            if os.environ.get("NO_COLOR") or not getattr(self.stdout, "isatty", lambda: False)():
                self._col = False
            else:
                self._col = _windows_vt_on() if os.name == "nt" else True
        return self._col

    def alert(self, text: str) -> None:
        """Something easy to miss that matters: bold yellow on a terminal.
        Callers write it in capitals, so it stands out without colour too."""
        self._end_status()
        if self._live():
            self.stdout.write(f"\n{self._paint(_YELLOW, self._wrap(text))}\n")
        elif self._colour():
            self.stdout.write(f"\n\x1b[1;33m{text}\x1b[0m\n")
        else:
            self.stdout.write(f"\n{text}\n")
        self.stdout.flush()

    def status(self, mode: str) -> None:
        if self._live():
            self.stdout.write(f"\r\x1b[K  {self._paint(_DIM, 'Display mode:')} {self._paint(_CYAN, mode)}")
            self.stdout.flush()
            self._status_shown = True
            return
        self.stdout.write(f"\r  Display mode: {mode:<10}")
        self.stdout.flush()
        self._status_shown = True

    @contextlib.contextmanager
    def busy(self, text: str, interval: float = 3.0):
        """Show that slow work is running, on one line. Yields a Job: job.note() adds a detail
        (how far along), job.done() sets the words for the finished line.
        On a terminal: a spinner and the time so far. Otherwise: the text, a dot every few seconds."""
        self._end_status()
        job = Job(text)
        if not self._colour():
            with self._dots(text, interval):
                yield job
            return
        sym = self._symbols()
        start = time.monotonic()
        stop = threading.Event()

        def spin():
            i = 0
            while True:
                took = time.monotonic() - start
                time_text = f"  {_elapsed(took)}" if took >= 3 else ""
                note = f"  {job.detail}" if job.detail else ""
                # Stay inside one row: a wrapped line can't be redrawn with \r.
                room = shutil.get_terminal_size((80, 24)).columns - 1 - 4 - len(time_text)
                label = text + note
                label = label if len(label) <= room else label[:max(room - 3, 0)] + "..."
                shown = label[:len(text)] + self._paint(_DIM, label[len(text):]) if len(label) > len(text) else label
                extra = f"  {self._paint(_DIM, time_text.strip())}" if time_text else ""
                self.stdout.write(f"\r\x1b[K  {self._paint(_PURPLE, sym['spin'][i % len(sym['spin'])])} "
                                  f"{shown}{extra}")
                self.stdout.flush()
                i += 1
                if stop.wait(0.1):
                    return
        t = threading.Thread(target=spin, daemon=True)
        t.start()
        ok = False
        try:
            yield job
            ok = True
        finally:
            stop.set()
            t.join()
            took = _elapsed(time.monotonic() - start)
            if ok and job.paused:
                self.stdout.write(f"\r\x1b[K  {self._paint(_YELLOW, '! ' + job.final)}\n")
            elif ok:
                self.stdout.write(f"\r\x1b[K  {self._paint(_CYAN, sym['ok'])} {job.final or text} "
                                  f"{self._paint(_DIM, f'({took})')}\n")
            else:
                stopped_at = f" ({job.detail})" if job.detail else ""
                self.stdout.write(f"\r\x1b[K  {self._paint(_RED, sym['fail'] + ' ' + text + stopped_at)}: "
                                  f"stopped ({took})\n")
            self.stdout.flush()

    @contextlib.contextmanager
    def _dots(self, text: str, interval: float):
        self.stdout.write(text)
        self.stdout.flush()
        stop = threading.Event()

        def dots():
            while not stop.wait(interval):
                self.stdout.write(".")
                self.stdout.flush()
        t = threading.Thread(target=dots, daemon=True)
        t.start()
        ok = False
        try:
            yield
            ok = True
        finally:
            stop.set()
            t.join()
            self.stdout.write(" done\n" if ok else " stopped\n")
            self.stdout.flush()

    def ask(self, text: str) -> str:
        self._end_status()
        if self._live():
            # Your turn: yellow, like the boxes.
            text = self._paint(_YELLOW, "  " + text.rstrip(" ")) + " "
        self.stdout.write(text)
        self.stdout.flush()
        line = self.stdin.readline()
        return line.rstrip("\r\n")


class Job:
    """One line of slow work: what it's doing now, and what to say when it's finished."""

    def __init__(self, text: str):
        self.text = text
        self.detail = ""
        self.final = None
        self.paused = False

    def note(self, detail: str) -> None:
        self.detail = detail

    def done(self, final: str) -> None:
        self.final = final

    def pause(self, final: str) -> None:
        """Ends the line as waiting on the user, not as done or failed."""
        self.final = final
        self.paused = True


def choose(ui, prompt: str, word: str) -> bool:
    """A prompt with two answers: type `word` (True) or press Enter (False).
    Anything else is a typo, and asks again rather than counting as either."""
    while True:
        answer = ui.ask(prompt).strip().lower()
        if answer == word:
            return True
        if not answer:
            return False
        ui.say(f'"{answer}" isn\'t an answer here. Type {word}, or just press Enter.')
