import re
from pathlib import Path

from lhk import plan

ROOT = Path(__file__).parent.parent


def test_manual_lists_every_setup_step():
    manual = (ROOT / "devices" / "amber" / "README.md").read_text(encoding="utf-8")
    headings = [l for l in manual.splitlines() if l.startswith("#")]
    for step in plan.setup_steps():
        assert any(f"`{step.name}`" in h for h in headings), f"no heading for {step.name}"


def test_manual_steps_in_tool_order():
    manual = (ROOT / "devices" / "amber" / "README.md").read_text(encoding="utf-8")
    found = re.findall(r"^#+ .*?`([a-z-]+)`", manual, re.M)
    names = [s.name for s in plan.setup_steps()]
    assert [n for n in found if n in names] == names


# Personal words to keep out of the repo (Wi-Fi names, passwords, domains) go
# one per line in this git-ignored file, so the check itself never publishes them.
PRIVATE_WORDS = ROOT / ".private-words"


def _private_pattern():
    words = [r"192\.168\.", r"HUA05[A-Z0-9]{3}\b(?<!HUA05TEST)"]
    if PRIVATE_WORDS.exists():
        words += [re.escape(w.strip()) for w in PRIVATE_WORDS.read_text(encoding="utf-8").splitlines()
                  if w.strip()]
    return re.compile("|".join(words))


def test_repo_has_no_private_data():
    pattern = _private_pattern()
    skip = {".git", ".venv", ".superpowers", "cache", "backup", "logs", "progress", "build", "dist"}
    for f in ROOT.rglob("*"):
        if (not f.is_file() or f == PRIVATE_WORDS or skip & set(f.relative_to(ROOT).parts)
                or f.suffix in {".bin", ".jar", ".zip"}):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        m = pattern.search(text)
        assert not m, f"{f.relative_to(ROOT)}: {m.group(0)!r}"
