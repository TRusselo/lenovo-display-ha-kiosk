"""Run log. Every line passes through redact(), so secrets never reach disk."""
from __future__ import annotations

import logging
import re
from pathlib import Path

_SECRET_KEYS = r"password|passwd|token|psk|secret"
# "key": "value"  /  key=value  /  key: value
_PATTERNS = [
    re.compile(rf'("(?:[^"]*(?:{_SECRET_KEYS})[^"]*)"\s*:\s*")([^"]*)(")', re.I),
    # <string name="flutter.ks.remote.password">value</string>
    re.compile(rf'(<string name="[^"]*(?:{_SECRET_KEYS})[^"]*">)([^<]*)(</string>)', re.I),
    re.compile(r"(\bBearer\s+)(\S+)", re.I),
    re.compile(rf"(\b\w*(?:{_SECRET_KEYS})\w*\s*[=:]\s*)([^\s,;&\"'<]+)", re.I),
]


def redact(text: str) -> str:
    for p in _PATTERNS:
        text = p.sub(lambda m: m.group(1) + "***" + (m.group(3) if m.lastindex == 3 else ""), text)
    return text


class _RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def setup(path: Path) -> logging.Logger:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"lhk.{path}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setFormatter(_RedactingFormatter("%(asctime)s %(levelname)s %(message)s"))
    logger.handlers[:] = [handler]
    return logger
