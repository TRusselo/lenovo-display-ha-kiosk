"""What the user sees and types. Plain words; physical steps stand out."""
from __future__ import annotations

import contextlib
import os
import sys
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
          "spin": "\u280b\u2819\u2839\u2838\u283c\u2834\u2826\u2827\u2807\u280f", "arrow": "\u25b6"}
_PLAIN = {"ok": "[x]", "todo": "[ ]", "fail": "[!]", "full": "#", "empty": "-", "spin": "|/-\\",
          "arrow": ">"}

_BOLD, _GREEN, _YELLOW, _RED, _CYAN, _DIM, _RESET = (
    "\x1b[1m", "\x1b[32m", "\x1b[1;33m", "\x1b[31m", "\x1b[1;36m", "\x1b[2m", "\x1b[0m")


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

    def _symbols(self) -> dict:
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

    def say(self, text: str) -> None:
        self._end_status()
        self.stdout.write(f"{text}\n")
        self.stdout.flush()

    def physical(self, text: str) -> None:
        self._end_status()
        bar = "=" * 72
        if self._colour():
            head = self._paint(_YELLOW, f"{self._symbols()['arrow']} DO THIS ON THE DISPLAY:")
            self.stdout.write(f"\n{self._paint(_YELLOW, bar)}\n  {head}\n  {text}\n"
                              f"{self._paint(_YELLOW, bar)}\n")
        else:
            self.stdout.write(f"\n{bar}\n  DO THIS ON THE DISPLAY:\n  {text}\n{bar}\n")
        self.stdout.flush()

    def overview(self, steps) -> None:
        """Every step, with the finished ones marked. steps: (title, done) pairs."""
        self._end_status()
        sym = self._symbols()
        self.stdout.write("\nThe steps:\n")
        for i, (title, done) in enumerate(steps, 1):
            mark = self._paint(_GREEN, sym["ok"]) if done else sym["todo"]
            self.stdout.write(f"  {mark} {i:>2}. {title}\n")
        self.stdout.flush()

    def header(self, index: int, total: int, title: str) -> None:
        """The start of a step: a progress bar and its number, matching the manual's headings."""
        self._end_status()
        sym = self._symbols()
        width = 20
        filled = round(width * (index - 1) / total) if total else 0
        bar = f"[{sym['full'] * filled}{sym['empty'] * (width - filled)}]"
        self.stdout.write(f"\n{self._paint(_CYAN, bar)} {self._paint(_BOLD, f'Step {index} of {total}: {title}')}\n")
        self.stdout.flush()

    def ok(self, text: str) -> None:
        """A finished step."""
        self._end_status()
        self.stdout.write(f"  {self._paint(_GREEN, self._symbols()['ok'])} {text}\n")
        self.stdout.flush()

    def section(self, title: str, lines) -> None:
        """A heading with indented lines under it, e.g. what to do next."""
        self._end_status()
        self.stdout.write(f"\n{self._paint(_BOLD, title)}\n")
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
        if self._colour():
            self.stdout.write(f"\n\x1b[1;33m{text}\x1b[0m\n")
        else:
            self.stdout.write(f"\n{text}\n")
        self.stdout.flush()

    def status(self, mode: str) -> None:
        self.stdout.write(f"\r  Display mode: {mode:<10}")
        self.stdout.flush()
        self._status_shown = True

    @contextlib.contextmanager
    def busy(self, text: str, interval: float = 3.0):
        """Show that slow work is running. On a terminal: a spinner and the time so far.
        Otherwise: the text, a dot every few seconds, then done."""
        self._end_status()
        if not self._colour():
            with self._dots(text, interval):
                yield
            return
        sym = self._symbols()
        start = time.monotonic()
        stop = threading.Event()

        def spin():
            i = 0
            while True:
                took = time.monotonic() - start
                extra = f"  {self._paint(_DIM, _elapsed(took))}" if took >= 3 else ""
                self.stdout.write(f"\r\x1b[K  {self._paint(_CYAN, sym['spin'][i % len(sym['spin'])])} {text}{extra}")
                self.stdout.flush()
                i += 1
                if stop.wait(0.1):
                    return
        t = threading.Thread(target=spin, daemon=True)
        t.start()
        ok = False
        try:
            yield
            ok = True
        finally:
            stop.set()
            t.join()
            took = _elapsed(time.monotonic() - start)
            if ok:
                self.stdout.write(f"\r\x1b[K  {self._paint(_GREEN, sym['ok'])} {text} ({took})\n")
            else:
                self.stdout.write(f"\r\x1b[K  {self._paint(_RED, sym['fail'])} {text}: stopped ({took})\n")
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
        self.stdout.write(text)
        self.stdout.flush()
        line = self.stdin.readline()
        return line.rstrip("\r\n")


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
