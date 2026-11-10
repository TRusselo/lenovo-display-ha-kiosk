from pathlib import Path
import os

import pytest

from lhk.modes import Mode, ModeTimeout, MultipleDevices, detect, wait_for_mode
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI

TOOLS = Tools(adb=Path("adb"), fastboot=Path("fastboot"))


def test_detects_fastboot_serial():
    runner = FakeRunner({("devices",): Result(0, "")})
    runner.responses[("devices",)] = Result(0, "")
    fb = FakeRunner({("devices",): Result(0, "HUA05TEST\tfastboot\n")})

    class Both:
        calls = []

        def run(self, args, **kw):
            return (fb if "fastboot" in str(args[0]) else runner).run(args, **kw)

    found = detect(Both(), TOOLS, usb_scan=lambda: [])
    assert found == [(Mode.FASTBOOT, "HUA05TEST")]


def test_detects_adb_device_and_ignores_unauthorized_header():
    runner = FakeRunner({("devices",): Result(0, "List of devices attached\nHUA05TEST\tdevice\n\n")})
    found = detect(runner, Tools(adb=Path("adb"), fastboot=Path("nofastboot")), usb_scan=lambda: [])
    assert (Mode.ADB, "HUA05TEST") in found


def test_detects_edl_by_usb_id():
    runner = FakeRunner({("devices",): Result(0, "")})
    found = detect(runner, TOOLS, usb_scan=lambda: ["usb:1-7"])
    assert found == [(Mode.EDL, "usb:1-7")]


def scripted(sequence):
    """detect_fn returning each list in turn, then the last one forever."""
    seq = list(sequence)

    def fn():
        return seq.pop(0) if len(seq) > 1 else seq[0]
    return fn


def ctx_with(ui):
    return Context(runner=None, ui=ui, paths=Paths("."))


def test_returns_serial_and_says_found_it():
    ui = FakeUI()
    serial = wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="Hold volume down",
                           timeout=5, detect_fn=scripted([[], [(Mode.FASTBOOT, "S1")]]),
                           sleep=lambda s: None)
    assert serial == "S1"
    assert "[physical] Hold volume down" in ui.lines
    assert any(line.startswith("Found it") for line in ui.lines)


def test_multiple_devices_raises():
    ui = FakeUI()
    with pytest.raises(MultipleDevices):
        wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=5,
                      detect_fn=scripted([[(Mode.FASTBOOT, "S1"), (Mode.ADB, "PHONE")]]),
                      sleep=lambda s: None)


def test_wrong_mode_reprompts():
    ui = FakeUI()
    serial = wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="Hold volume down",
                           timeout=5,
                           detect_fn=scripted([[], [(Mode.EDL, "usb")], [], [(Mode.FASTBOOT, "S1")]]),
                           sleep=lambda s: None)
    assert serial == "S1"
    assert any("EDL" in line and "not" in line.lower() for line in ui.lines)
    assert ui.lines.count("[physical] Hold volume down") == 2


def test_dropout_then_return_succeeds():
    # The display drops off USB mid-wait (cable knocked, button held too long) and comes back.
    ui = FakeUI()
    serial = wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=5,
                           detect_fn=scripted([[(Mode.EDL, "usb")], [], [], [(Mode.FASTBOOT, "S1")]]),
                           sleep=lambda s: None)
    assert serial == "S1"
    assert "none" in ui.statuses


def test_times_out_when_the_user_types_stop():
    ui = FakeUI(answers=["stop"])
    t = iter(range(0, 1000, 1))
    with pytest.raises(ModeTimeout):
        wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=3,
                      detect_fn=lambda: [], sleep=lambda s: None, clock=lambda: next(t))


def test_readout_shows_mode_names():
    ui = FakeUI()
    wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=5,
                  detect_fn=scripted([[], [(Mode.FASTBOOT, "S1")]]), sleep=lambda s: None)
    assert "none" in ui.statuses and "FASTBOOT" in ui.statuses


def test_real_runner_reports_failure():
    from lhk.runner import CommandFailed, RealRunner
    import sys
    r = RealRunner()
    assert r.run([sys.executable, "-c", "print('hi')"]).out.strip() == "hi"
    with pytest.raises(CommandFailed):
        r.run([sys.executable, "-c", "import sys; sys.exit(3)"])
    assert r.run([sys.executable, "-c", "import sys; sys.exit(3)"], check=False).code == 3


def test_tools_locate(tmp_path):
    from lhk.runner import platform_id
    d = tmp_path / f"platform-tools-{platform_id()}" / "platform-tools"
    d.mkdir(parents=True)
    t = Tools.locate(tmp_path)
    assert t.adb.parent == d and t.fastboot.parent == d


def test_prompts_say_let_go_after_3_to_5_seconds_and_name_the_logo():
    from lhk.plan import EDL_PROMPT
    from lhk.unlock import FASTBOOT_PROMPT
    for prompt in (EDL_PROMPT, FASTBOOT_PROMPT):
        assert "3 to 5 seconds" in prompt
        assert "Lenovo logo" in prompt
        assert "Keep holding" not in prompt


def test_hints_once_after_20_seconds_of_nothing():
    ui = FakeUI()
    t = iter(range(0, 1000))
    seen = iter([[]] * 30 + [[(Mode.FASTBOOT, "S1")]])
    serial = wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=180,
                           detect_fn=lambda: next(seen), sleep=lambda s: None, clock=lambda: next(t))
    assert serial == "S1"
    hints = [line for line in ui.lines if "Lenovo logo" in line]
    assert len(hints) == 1 and "starting normally" in hints[0]


def test_no_hint_before_20_seconds():
    ui = FakeUI()
    t = iter(range(0, 1000))
    seen = iter([[]] * 5 + [[(Mode.FASTBOOT, "S1")]])
    wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=180,
                  detect_fn=lambda: next(seen), sleep=lambda s: None, clock=lambda: next(t))
    assert not any("Lenovo logo" in line for line in ui.lines)


def test_timeout_asks_to_try_again_and_keeps_waiting():
    ui = FakeUI(answers=[""])
    t = iter(range(0, 1000))
    seen = iter([[]] * 8 + [[(Mode.FASTBOOT, "S1")]])
    serial = wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=5,
                           detect_fn=lambda: next(seen), sleep=lambda s: None, clock=lambda: next(t))
    assert serial == "S1"
    assert any(line.startswith("[ask]") and "try again" in line for line in ui.lines)
    assert ui.lines.count("[physical] p") == 2


def test_a_tool_that_cannot_run_is_reported_not_shown_as_no_device(tmp_path):
    from lhk.modes import ToolBroken
    from lhk.runner import RealRunner
    import logging
    tool = tmp_path / "fastboot"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o644)
    with pytest.raises(ToolBroken, match="fastboot"):
        detect(RealRunner(logger=logging.getLogger("t")), Tools(adb=tmp_path / "adb", fastboot=tool),
               usb_scan=lambda: [])


def test_a_tool_not_downloaded_yet_counts_as_no_device(tmp_path):
    from lhk.runner import RealRunner
    import logging
    found = detect(RealRunner(logger=logging.getLogger("t")),
                   Tools(adb=tmp_path / "adb", fastboot=tmp_path / "fastboot"), usb_scan=lambda: [])
    assert found == []


def test_already_in_the_mode_skips_the_button_prompt():
    ui = FakeUI()
    serial = wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="Hold volume down", timeout=5,
                           detect_fn=lambda: [(Mode.FASTBOOT, "S1")], sleep=lambda s: None)
    assert serial == "S1"
    assert not any(line.startswith("[physical]") for line in ui.lines)
    assert any("already in FASTBOOT" in line for line in ui.lines)


def test_timeout_after_the_wrong_mode_doesnt_say_nothing():
    ui = FakeUI(answers=["stop"])
    t = iter(range(0, 1000))
    with pytest.raises(ModeTimeout):
        wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=3,
                      detect_fn=lambda: [(Mode.EDL, "usb")], sleep=lambda s: None, clock=lambda: next(t))
    asks = [line for line in ui.lines if line.startswith("[ask]")]
    assert asks and "still isn't in FASTBOOT" in asks[0] and "nothing" not in asks[0].lower()


def test_the_mode_it_starts_in_is_not_a_wrong_attempt():
    # Run 4: right after the backup or restore the display is still in EDL;
    # the user hasn't unplugged it yet, so that's not a mistake.
    ui = FakeUI()
    serial = wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=5,
                           detect_fn=scripted([[(Mode.EDL, "usb")], [(Mode.EDL, "usb")], [],
                                               [(Mode.FASTBOOT, "S1")]]),
                           sleep=lambda s: None)
    assert serial == "S1"
    assert not any("not FASTBOOT" in l for l in ui.lines)
    assert ui.lines.count("[physical] p") == 1


def test_coming_back_in_the_starting_mode_after_unplugging_is_reported():
    ui = FakeUI()
    wait_for_mode(Mode.FASTBOOT, ctx_with(ui), prompt="p", timeout=5,
                  detect_fn=scripted([[(Mode.EDL, "usb")], [], [(Mode.EDL, "usb")], [(Mode.FASTBOOT, "S1")]]),
                  sleep=lambda s: None)
    assert any("not FASTBOOT" in l for l in ui.lines)
