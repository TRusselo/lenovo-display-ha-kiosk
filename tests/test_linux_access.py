"""Linux USB access: the rule must cover every mode the tool uses, and a
permissions problem must say what to do instead of looking like no device."""
from pathlib import Path

import pytest

from lhk import modes
from lhk.modes import Mode, UsbNoPermission, detect
from lhk.runner import Result, Tools
from tests.fakes import FakeRunner

ROOT = Path(__file__).resolve().parent.parent
RULES = ROOT / "assets" / "linux" / "51-lhk.rules"
TOOLS = Tools(adb=Path("adb"), fastboot=Path("fastboot"))


def test_rule_covers_edl_fastboot_and_adb_for_the_user_and_plugdev():
    rules = [l for l in RULES.read_text().splitlines() if l and not l.startswith("#")]
    for vid, pid in (("05c6", "9008"), ("18d1", "d00d"), ("18d1", "4ee7")):
        line = next(l for l in rules if f'"{vid}"' in l and f'"{pid}"' in l)
        assert 'TAG+="uaccess"' in line and 'GROUP="plugdev"' in line and 'MODE="0660"' in line


def test_linux_steps_cover_the_group_fallback_and_replugging():
    doc = (ROOT / "docs" / "LINUX.md").read_text()
    assert "51-lhk.rules" in doc and "udevadm trigger" in doc
    assert "usermod -aG plugdev" in doc and "log out" in doc.lower() and "plug it back in" in doc


@pytest.mark.parametrize("tool,out", [
    ("adb", "List of devices attached\nHUA05TEST\tno permissions (missing udev rules?); see [http://developer.android.com/tools/device.html]\n"),
    ("fastboot", "no permissions (missing udev rules?)\tfastboot\n"),
])
def test_no_permissions_is_reported_not_shown_as_no_device(tool, out):
    other = "fastboot" if tool == "adb" else "adb"
    runner = FakeRunner({("devices",): Result(0, "")})

    class Pick:
        def run(self, args, **kw):
            return Result(0, out) if Path(args[0]).name == tool else runner.run(args, **kw)

    with pytest.raises(UsbNoPermission, match="LINUX.md"):
        detect(Pick(), TOOLS, usb_scan=lambda: [])


def test_edl_wait_reports_a_device_this_user_cannot_open():
    runner = FakeRunner({("devices",): Result(0, "")})
    with pytest.raises(UsbNoPermission):
        detect(runner, TOOLS, usb_scan=lambda: ["usb:1-7"], strict_usb=True, usb_access=lambda d: False)


def test_other_waits_ignore_edl_access():
    # Right after a backup the display is still in EDL while the tool waits for fastboot.
    runner = FakeRunner({("devices",): Result(0, "")})
    found = detect(runner, TOOLS, usb_scan=lambda: ["usb:1-7"], usb_access=lambda d: False)
    assert found == [(Mode.EDL, "usb:1-7")]


def test_usb_node_path_on_linux(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(modes.sys, "platform", "linux")
    monkeypatch.setattr(modes.os, "access", lambda p, m: seen.append(p) or True)
    assert modes.usb_access("usb:1-7") is True
    assert seen == ["/dev/bus/usb/001/007"]


def test_permission_message_names_the_usb_step_of_the_linux_guide():
    import re
    doc = (ROOT / "docs" / "LINUX.md").read_text()
    step = re.search(r"^## (\d+)\. Allow USB access", doc, re.M).group(1)
    assert f"docs/LINUX.md, step {step}" in modes.NO_PERMISSION
