"""Every doc a message names must exist, be in the release zip, and come with
a link for people who only have the program."""
import re
from pathlib import Path

import lhk
from lhk import doc

ROOT = Path(__file__).resolve().parent.parent
DOC_PATH = re.compile(r"\b((?:docs|devices)/[\w./-]+\.md)")


def _sources():
    return {p: p.read_text(encoding="utf-8") for p in (ROOT / "lhk").rglob("*.py")}


def test_doc_gives_the_local_path_and_a_link():
    text = doc("docs/LINUX.md")
    assert "docs/LINUX.md" in text and f"{lhk.DOCS_URL}/docs/LINUX.md" in text


def test_every_doc_a_message_names_exists():
    for src, text in _sources().items():
        for path in DOC_PATH.findall(text):
            assert (ROOT / path).exists(), f"{src.name} names {path}, which doesn't exist"


def test_messages_name_docs_only_through_doc():
    # A bare path means nothing to someone who only has the program.
    for src, text in _sources().items():
        for line in text.splitlines():
            if DOC_PATH.search(line) and not line.lstrip().startswith("#") and "doc(" not in line:
                raise AssertionError(f"{src.name}: {line.strip()}")


def test_button_skip_names_the_manual_section():
    assert 'doc("devices/amber/README.md"' in (ROOT / "lhk" / "bootfix.py").read_text()


def test_release_zip_carries_the_docs():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text()
    for item in ("README.md", "docs", "devices"):
        assert item in wf.split("- name: Zip", 1)[1]
    assert "plans" in wf  # the planning notes stay out
