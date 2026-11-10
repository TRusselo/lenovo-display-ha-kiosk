"""What the user sees and types. Plain words; physical steps stand out."""
from __future__ import annotations

import contextlib
import os
import sys
import threading


class UI:
    def __init__(self, stdin=None, stdout=None):
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self._status_shown = False

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
        self.stdout.write(f"\n{bar}\n  DO THIS ON THE DISPLAY:\n  {text}\n{bar}\n")
        self.stdout.flush()

    def _colour(self) -> bool:
        if os.environ.get("NO_COLOR") or not getattr(self.stdout, "isatty", lambda: False)():
            return False
        if os.name == "nt":
            try:  # Windows consoles show colour codes only with virtual-terminal mode on.
                import ctypes
                k = ctypes.windll.kernel32
                h = k.GetStdHandle(-11)
                mode = ctypes.c_uint32()
                if not k.GetConsoleMode(h, ctypes.byref(mode)):
                    return False
                return bool(k.SetConsoleMode(h, mode.value | 0x0004))
            except Exception:
                return False
        return True

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
        """Show that slow work is running: the text, a dot every few seconds, then done."""
        self._end_status()
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
