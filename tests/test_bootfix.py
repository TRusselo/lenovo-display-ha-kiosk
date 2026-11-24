from pathlib import Path

import pytest

from lhk import bootfix
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI

@pytest.fixture(autouse=True)
def no_root_dance(monkeypatch):
    # The device in these tests is already rooted; ensure_root_rw has its own tests.
    monkeypatch.setattr(bootfix, "ensure_root_rw", lambda ctx: None)
    monkeypatch.setattr(bootfix, "reboot_and_wait", lambda ctx, timeout=300, **kw: None)


PS_OK = "  1843 u:r:dumpstate:s0               app_process /system/bin ks.VolKeys\n"
SENSORS_OK = "15:05:55 + 0x00000002 pid= 1930 uid=10036 package=me.jxl.kiosk_satellite.LightSensor$attach$l$1\n"


def make_ctx(tmp_path, runner):
    jar = tmp_path / "ks-volkeys.jar"
    jar.write_bytes(b"PK")
    c = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1", volkeys_jar=jar)
    return c


def healthy_runner():
    return FakeRunner({
        ("-s", "S1", "shell", "getprop", "init.svc.ks_volume_keys"): Result(0, "running\n"),
        ("-s", "S1", "shell", "getprop", "sys.boot_completed"): Result(0, "1\n"),
        ("-s", "S1", "shell", "ps", "-A", "-o", "LABEL,ARGS"): Result(0, PS_OK),
        ("-s", "S1", "shell", "dumpsys", "sensorservice"): Result(0, SENSORS_OK),
        ("-s", "S1", "shell", "dumpsys", "input"): Result(0, "Window #1 HomeAlias\n"),
        ("-s", "S1", "shell", "cmd", "package", "resolve-activity"): Result(
            0, "priority=0 preferredOrder=0\nme.jxl.kiosk_satellite/.HomeAlias\n"),
    })


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(bootfix.time, "sleep", lambda s: None)
    monkeypatch.setattr(bootfix, "wait_booted", lambda ctx, timeout=300, **kw: None)
    monkeypatch.setattr(bootfix, "check_buttons", lambda ctx: None)


def test_bootfix_push_and_labels_exact(tmp_path, monkeypatch):
    rebooted = []
    monkeypatch.setattr(bootfix, "reboot_and_wait", lambda ctx, timeout=300, **kw: rebooted.append(True))
    runner = healthy_runner()
    ctx = make_ctx(tmp_path, runner)
    bootfix.BootFixStep().run(ctx)
    pushes = [(Path(c[4]).name, c[5]) for c in runner.calls if c[3] == "push"]
    assert pushes == [
        ("ks-boot-fix.sh", "/system/bin/ks-boot-fix.sh"),
        ("ks-volume-keys.sh", "/system/bin/ks-volume-keys.sh"),
        ("ks-volkeys.jar", "/system/framework/ks-volkeys.jar"),
        ("ks-boot-fix.rc", "/system/etc/init/ks-boot-fix.rc"),
    ]
    shells = [c[4:] for c in runner.calls if c[3] == "shell"]
    assert ["chmod", "755", "/system/bin/ks-boot-fix.sh"] in shells
    assert ["chmod", "755", "/system/bin/ks-volume-keys.sh"] in shells
    assert ["chmod", "644", "/system/framework/ks-volkeys.jar"] in shells
    assert ["chmod", "644", "/system/etc/init/ks-boot-fix.rc"] in shells
    assert ["chcon", "u:object_r:dumpstate_exec:s0", "/system/bin/ks-boot-fix.sh"] in shells
    assert ["chcon", "u:object_r:dumpstate_exec:s0", "/system/bin/ks-volume-keys.sh"] in shells
    assert ["restorecon", "/system/framework/ks-volkeys.jar"] in shells
    assert ["restorecon", "/system/etc/init/ks-boot-fix.rc"] in shells
    assert rebooted == [True]


def test_bootfix_never_touches_init_rc(tmp_path):
    runner = healthy_runner()
    bootfix.BootFixStep().run(make_ctx(tmp_path, runner))
    assert not any(a == "/init.rc" or a.endswith(" /init.rc") for c in runner.calls for a in c)
    assert all(remote != "/init.rc" for _, remote, _, _ in bootfix.FILES)


def test_verify_healthy(tmp_path):
    assert bootfix.verify(make_ctx(tmp_path, healthy_runner())) == []


def test_verify_reports_missing_light_sensor(tmp_path):
    runner = healthy_runner()
    runner.responses[("-s", "S1", "shell", "dumpsys", "sensorservice")] = Result(0, "no registrations\n")
    problems = bootfix.verify(make_ctx(tmp_path, runner), wait=0)
    assert any("light sensor" in p for p in problems)


def test_verify_reports_touch_eating_layer(tmp_path):
    runner = healthy_runner()
    runner.responses[("-s", "S1", "shell", "dumpsys", "input")] = Result(0, "0: name='nav_input_consumer'\n")
    assert any("navigation" in p for p in bootfix.verify(make_ctx(tmp_path, runner)))


def test_verify_reports_volume_helper_not_running(tmp_path):
    runner = healthy_runner()
    runner.responses[("-s", "S1", "shell", "ps", "-A", "-o", "LABEL,ARGS")] = Result(0, "")
    assert any("volume" in p for p in bootfix.verify(make_ctx(tmp_path, runner), wait=0))


def test_verify_waits_for_the_volume_helper_to_start(tmp_path):
    # init starts it on sys.boot_completed=1, the same moment the tool sees the
    # display as booted, so the first look can come before it's running.
    runner = healthy_runner()
    runner.responses[("-s", "S1", "shell", "getprop", "init.svc.ks_volume_keys")] = [
        Result(0, "\n"), Result(0, "running\n")]
    runner.responses[("-s", "S1", "shell", "ps", "-A", "-o", "LABEL,ARGS")] = [Result(0, ""), Result(0, PS_OK)]
    assert bootfix.verify(make_ctx(tmp_path, runner)) == []


def test_bootfix_says_before_restarting_the_display(tmp_path, monkeypatch):
    order = []
    ctx = make_ctx(tmp_path, healthy_runner())
    say = ctx.ui.say
    ctx.ui.say = lambda text: (order.append(("say", text)), say(text))
    monkeypatch.setattr(bootfix, "reboot_and_wait", lambda ctx, **kw: order.append(("reboot", "")))
    monkeypatch.setattr(bootfix, "_jar", lambda ctx: tmp_path / "x.jar")
    bootfix.BootFixStep().run(ctx)
    reboot = order.index(("reboot", ""))
    assert any(kind == "say" and "restart" in text.lower() for kind, text in order[:reboot])


def test_verify_reports_kiosk_satellite_not_being_the_home_screen(tmp_path):
    # Run 2: with Kiosk Satellite's home.enabled off, every restart landed on
    # Google Assistant's home screen, stuck on its loading dots.
    runner = healthy_runner()
    runner.responses[("-s", "S1", "shell", "cmd", "package", "resolve-activity")] = Result(
        0, "com.google.assistant.gallium.client.androidthingshost/.app.GalliumActivity\n")
    assert any("home screen" in p for p in bootfix.verify(make_ctx(tmp_path, runner), wait=0))


def _volume_runner(values):
    r = healthy_runner()
    r.responses[("-s", "S1", "shell", "settings", "get", "system", "volume_music_speaker")] = [
        Result(0, f"{v}\n") for v in values]
    return r


def test_buttons_warn_before_asking_for_presses(tmp_path, monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(bootfix.time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, _volume_runner([40, 45, 45, 40]))
    bootfix.check_buttons(ctx)
    first_press = next(i for i, l in enumerate(ctx.ui.lines) if "Press VOLUME UP" in l)
    assert any(l.startswith("[alert]") and "NOT DONE" in l for l in ctx.ui.lines[:first_press])


def test_buttons_wait_without_asking(tmp_path, monkeypatch):
    # Run 9: the user was busy elsewhere, and each 60 s timeout held setup until
    # Enter. The check now just keeps waiting for the press.
    monkeypatch.undo()
    monkeypatch.setattr(bootfix.time, "sleep", lambda s: None)
    clock = iter(range(0, 10_000, 30))
    monkeypatch.setattr(bootfix.time, "monotonic", lambda: next(clock))
    ctx = make_ctx(tmp_path, _volume_runner([40, 40, 40, 40, 40, 45, 45, 40]))
    bootfix.check_buttons(ctx)
    assert not any(l.startswith("[ask]") for l in ctx.ui.lines)
    assert ctx.ui.lines[-1] == "Volume buttons work."


def test_buttons_reminder_says_how_to_go_on_without_the_check(tmp_path, monkeypatch):
    # A rerun skips the whole step (its files are in place), so Ctrl-C and the
    # same command again goes on without the check.
    monkeypatch.undo()
    monkeypatch.setattr(bootfix.time, "sleep", lambda s: None)
    clock = iter(range(0, 10_000, 30))
    monkeypatch.setattr(bootfix.time, "monotonic", lambda: next(clock))
    ctx = make_ctx(tmp_path, _volume_runner([40, 40, 40, 40, 40, 45, 45, 40]))
    bootfix.check_buttons(ctx)
    reminder = next(l for l in ctx.ui.lines if "Ctrl-C" in l)
    assert "same command" in reminder and "step 16" in reminder
    assert "[redraw]" in ctx.ui.lines


def test_rerun_after_a_failed_press_test_skips_the_step(tmp_path):
    # Why the timeout can't just stop: done() only checks files and services.
    runner = healthy_runner()
    runner.responses[("-s", "S1", "shell", "ls")] = Result(0, "\n".join(r for _, r, _, _ in bootfix.FILES))
    assert bootfix.BootFixStep().done(make_ctx(tmp_path, runner))


def test_done_gives_the_helpers_time_to_start_after_a_restart(tmp_path, monkeypatch):
    # The fixed-address step restarts the display just before; with no wait the helpers weren't up yet, and
    # the step ran again, restart and button presses included (e2e, 2026-11-24).
    listing = "\n".join(remote for _, remote, _, _ in bootfix.FILES)
    runner = FakeRunner({("-s", "S1", "shell", "ls"): Result(0, listing)})
    waits = []
    monkeypatch.setattr(bootfix, "verify", lambda ctx, wait=90: waits.append(wait) or [])
    assert bootfix.BootFixStep().done(make_ctx(tmp_path, runner))
    assert waits and waits[0] >= 60


def test_done_sees_missing_files_in_ls_errors_and_doesnt_wait(tmp_path, monkeypatch):
    # ls names each missing file in its error ("ls: /x: No such file or directory"), so a name in the
    # output isn't proof it's there. On a freshly flashed display done() then waited 90 s in silence for
    # helpers that weren't installed yet (e2e, 2026-11-23).
    first = bootfix.FILES[0][1]
    listing = "\n".join([f"ls: {first}: No such file or directory"]
                        + [remote for _, remote, _, _ in bootfix.FILES[1:]])
    runner = FakeRunner({("-s", "S1", "shell", "ls"): Result(1, listing)})
    waits = []
    monkeypatch.setattr(bootfix, "verify", lambda ctx, wait=90: waits.append(wait) or [])
    assert not bootfix.BootFixStep().done(make_ctx(tmp_path, runner))
    assert waits == []


def test_the_wait_in_done_says_so_on_screen(tmp_path, monkeypatch):
    # Up to 90 s with nothing on screen looked hung (e2e, 2026-11-23).
    runner = FakeRunner({("-s", "S1", "shell", "ls"): Result(0, "\n".join(r for _, r, _, _ in bootfix.FILES))})
    monkeypatch.setattr(bootfix, "verify", lambda ctx, wait=90: [])
    ctx = make_ctx(tmp_path, runner)
    bootfix.BootFixStep().done(ctx)
    assert any(l.startswith("[busy]") and "please wait" in l for l in ctx.ui.lines)


# 0.2.9 installed /system/bin/ks-amp-tune, which rewrote Lenovo's speaker tuning at boot; the assistant's
# voice sounded bad with it, and 0.2.10 took it out. A display set up with 0.2.9 still has it.
OLD_AMP_TOOL = "/system/bin/ks-amp-tune"


def test_the_step_removes_0_2_9s_speaker_tool(tmp_path):
    runner = healthy_runner()
    bootfix.BootFixStep().run(make_ctx(tmp_path, runner))
    shells = [c[4:] for c in runner.calls if c[3] == "shell"]
    assert ["rm", "-f", OLD_AMP_TOOL] in shells
    assert shells.index(["rm", "-f", OLD_AMP_TOOL]) < shells.index(
        ["restorecon", "/system/etc/init/ks-boot-fix.rc"])


def test_a_display_with_0_2_9s_speaker_tool_isnt_done(tmp_path, monkeypatch):
    listing = "\n".join([r for _, r, _, _ in bootfix.FILES] + [OLD_AMP_TOOL])
    runner = FakeRunner({("-s", "S1", "shell", "ls"): Result(0, listing)})
    monkeypatch.setattr(bootfix, "verify", lambda ctx, wait=90: [])
    assert not bootfix.BootFixStep().done(make_ctx(tmp_path, runner))
