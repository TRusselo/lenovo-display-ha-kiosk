"""Test doubles: no hardware, no network."""
from __future__ import annotations

import contextlib

from lhk.runner import CommandFailed, Result


class FakeRunner:
    """Answers commands from a table; records every call in .calls.

    responses maps a tuple prefix of the argument list (after the tool path)
    to a Result, or to a list of Results returned one per call.
    """

    def __init__(self, responses=None, default=Result(0, "")):
        self.responses = dict(responses or {})
        self.default = default
        self.calls: list[list[str]] = []
        self.envs: list[dict | None] = []

    def run(self, args, *, check=True, timeout=60, env=None, log_output=True):
        args = [str(a) for a in args]
        self.calls.append(args)
        self.envs.append(env)
        tail = tuple(args[1:])
        best = None
        for key in self.responses:
            if tail[:len(key)] == key and (best is None or len(key) > len(best)):
                best = key
        if best is None:
            result = self.default
        else:
            value = self.responses[best]
            if isinstance(value, list):
                result = value.pop(0) if len(value) > 1 else value[0]
            else:
                result = value
        if isinstance(result, BaseException):
            raise result
        if check and result.code != 0:
            raise CommandFailed(args, result)
        return result


class FakeUI:
    def __init__(self, answers=None):
        self.lines: list[str] = []
        self.statuses: list[str] = []
        self.answers = list(answers or [])

    def say(self, text):
        self.lines.append(text)

    def physical(self, text):
        self.lines.append(f"[physical] {text}")

    def alert(self, text):
        self.lines.append(f"[alert] {text}")

    def status(self, text):
        self.statuses.append(text)

    @contextlib.contextmanager
    def busy(self, text, interval=3.0):
        self.lines.append(f"[busy] {text}")
        yield

    def ask(self, text):
        self.lines.append(f"[ask] {text}")
        return self.answers.pop(0) if self.answers else ""
