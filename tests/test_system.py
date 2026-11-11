from pathlib import Path

import pytest

from lhk import system
from lhk.mixer import MixerPatchError, patch_mixer
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI

@pytest.fixture(autouse=True)
def no_root_dance(monkeypatch):
    # The device in these tests is already rooted; ensure_root_rw has its own tests.
    monkeypatch.setattr(system, "ensure_root_rw", lambda ctx: None)


MIXER = """<?xml version="1.0" encoding="ISO-8859-1"?>
<mixer>
    <!-- These are the initial mixer settings -->
    <ctl name="ADC1 Volume" value="4" />
    <ctl name="ADC2 Volume" value="4" />
    <ctl name="ADC3 Volume" value="4" />
    <ctl name="DEC1 Volume" value="84" />
    <ctl name="DEC2 Volume" value="84" />
    <ctl name="RX1 Digital Volume" value="84" />

    <path name="adc1">
        <ctl name="ADC1 Volume" value="6" />
        <ctl name="DEC1 MUX" value="ADC1" />
    </path>

    <path name="adc2">
        <ctl name="ADC2 Volume" value="6" />
    </path>

    <path name="adc3">
        <ctl name="ADC3 Volume" value="6" />
    </path>

    <path name="handset-mic">
        <ctl name="ADC3 Volume" value="6" />
        <ctl name="DEC2 Volume" value="84" />
    </path>
</mixer>
"""


def test_patch_mixer_changes_only_the_six_proven_lines():
    out = patch_mixer(MIXER)
    before, after = MIXER.splitlines(), out.splitlines()
    assert len(before) == len(after)
    changed = [(b.strip(), a.strip()) for b, a in zip(before, after) if b != a]
    assert changed == [
        ('<ctl name="DEC1 Volume" value="84" />', '<ctl name="DEC1 Volume" value="96" />'),
        ('<ctl name="DEC2 Volume" value="84" />', '<ctl name="DEC2 Volume" value="96" />'),
        ('<ctl name="ADC1 Volume" value="6" />', '<ctl name="ADC1 Volume" value="12" />'),
        ('<ctl name="ADC2 Volume" value="6" />', '<ctl name="ADC2 Volume" value="12" />'),
        ('<ctl name="ADC3 Volume" value="6" />', '<ctl name="ADC3 Volume" value="12" />'),
        ('<ctl name="ADC3 Volume" value="6" />', '<ctl name="ADC3 Volume" value="12" />'),
    ]


def test_patch_mixer_leaves_top_level_adc_defaults():
    out = patch_mixer(MIXER)
    assert out.count('<ctl name="ADC1 Volume" value="4" />') == 1


def test_patch_mixer_is_idempotent():
    once = patch_mixer(MIXER)
    assert patch_mixer(once) == once


def test_patch_mixer_refuses_unexpected_file():
    with pytest.raises(MixerPatchError):
        patch_mixer("<mixer>\n</mixer>\n")


def make_ctx(tmp_path, runner):
    c = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1")
    return c


def test_degoogle_list_is_exactly_the_proven_four():
    assert system.degoogle_packages() == [
        "com.google.assistant.gallium.dragonglass.platform.androidthings.system",
        "com.google.android.apps.mediashell",
        "com.google.android.things.checkin",
        "com.google.android.things.customcheckin",
    ]


def test_degoogle_never_touches_sensor_host(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "degoogle_packages",
                        lambda: ["com.google.android.things.sparrow.oem"])
    with pytest.raises(system.UnsafePackage):
        system.DegoogleStep().run(make_ctx(tmp_path, FakeRunner()))


def test_degoogle_idempotent(tmp_path):
    disabled = "\n".join(f"package:{p}" for p in system.degoogle_packages())
    runner = FakeRunner({("-s", "S1", "shell", "pm", "list", "packages", "-d"): Result(0, disabled)})
    ctx = make_ctx(tmp_path, runner)
    step = system.DegoogleStep()
    assert step.done(ctx)
    step.run(ctx)
    assert not any("disable" in c for call in runner.calls for c in call if c != "-d")


def test_degoogle_disables_missing_ones(tmp_path):
    runner = FakeRunner({("-s", "S1", "shell", "pm", "list", "packages", "-d"):
                         Result(0, "package:com.google.android.apps.mediashell\n")})
    system.DegoogleStep().run(make_ctx(tmp_path, runner))
    disabled = [c[-1] for c in runner.calls if c[4:6] == ["pm", "disable"]]
    assert disabled == [p for p in system.degoogle_packages() if p != "com.google.android.apps.mediashell"]


def test_mixer_step_pushes_patched_file(tmp_path, monkeypatch):
    runner = FakeRunner({("-s", "S1", "shell", "cat", system.MIXER_PATH): Result(0, MIXER)})
    ctx = make_ctx(tmp_path, runner)
    pushed = {}
    monkeypatch.setattr(system, "_verify_pushed", lambda ctx, expected: pushed.setdefault("ok", expected))
    system.MixerStep().run(ctx)
    push = [c for c in runner.calls if c[3:4] == ["push"]]
    assert push and push[0][-1] == system.MIXER_PATH
    assert pushed["ok"] == patch_mixer(MIXER)


def test_things_settings_waits_for_wifi(tmp_path, monkeypatch):
    runner = FakeRunner({("-s", "S1", "shell", "ip", "-4", "addr", "show", "wlan0"):
                         [Result(0, ""), Result(0, "    inet 10.0.0.5/24 brd 10.0.0.255 scope global wlan0\n")]})
    ctx = make_ctx(tmp_path, runner)
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    system.OpenThingsSettingsStep().run(ctx)
    assert any(c[4:7] == ["monkey", "-p", "com.android.iotlauncher"] for c in runner.calls)
    text = " ".join(ctx.ui.lines)
    assert "Date & time" in text and "Check for update" in text and "Factory data reset" in text


def test_mixer_step_refuses_undecodable_file(tmp_path, monkeypatch):
    runner = FakeRunner({("-s", "S1", "shell", "cat", system.MIXER_PATH): Result(0, MIXER.replace("mixer>", "mix�er>", 1))})
    ctx = make_ctx(tmp_path, runner)
    with pytest.raises(system.SetupFailed):
        system.MixerStep().run(ctx)
    assert not [c for c in runner.calls if c[3:4] == ["push"]]


def test_serial_detected_when_missing(tmp_path, monkeypatch):
    from lhk.modes import Mode
    monkeypatch.setattr(system, "detect", lambda runner, tools: [(Mode.ADB, "HUA05X")])
    c = Context(runner=FakeRunner(), ui=FakeUI(), paths=Paths(tmp_path))
    c.state["tools"] = Tools(adb=Path("adb"), fastboot=Path("fastboot"))
    assert system.serial(c) == "HUA05X"
    assert c.state["serial"] == "HUA05X"


def test_serial_refuses_two_devices(tmp_path, monkeypatch):
    from lhk.modes import Mode, MultipleDevices
    monkeypatch.setattr(system, "detect", lambda runner, tools: [(Mode.ADB, "A"), (Mode.ADB, "B")])
    c = Context(runner=FakeRunner(), ui=FakeUI(), paths=Paths(tmp_path))
    c.state["tools"] = Tools(adb=Path("adb"), fastboot=Path("fastboot"))
    with pytest.raises(MultipleDevices):
        system.serial(c)


OWNER_DUMP = ("Device Owner: \n"
              "  admin=ComponentInfo{me.jxl.kiosk_satellite/me.jxl.kiosk_satellite.KioskAdminReceiver}\n"
              "  name=\n  package=me.jxl.kiosk_satellite\n")


def test_verify_step_runs(tmp_path, monkeypatch):
    from lhk import plan, bootfix
    runner = FakeRunner({
        ("-s", "S1", "shell", "getprop", "ro.build.fingerprint"):
            Result(0, "Things/x:8.1.0/OIMK.211005.001/7795499:userdebug/dev-keys\n"),
        ("-s", "S1", "shell", "wm", "size"): Result(0, "Physical size: 800x1280\n"),
        ("-s", "S1", "shell", "dumpsys", "device_policy"): Result(0, OWNER_DUMP),
    })
    monkeypatch.setattr(bootfix, "verify", lambda ctx, **kw: [])
    plan.VerifyStep().run(make_ctx(tmp_path, runner))


WIFI_UP = [Result(0, ""), Result(0, "    inet 10.0.0.5/24 brd 10.0.0.255 scope global wlan0\n")]


def _settings_runner():
    return FakeRunner({("-s", "S1", "shell", "ip", "-4", "addr", "show", "wlan0"): list(WIFI_UP),
                       ("-s", "S1", "shell", "getprop", "persist.sys.timezone"): Result(0, "America/Regina\n")})


def test_things_settings_asks_for_the_time_zone_before_wifi(tmp_path, monkeypatch):
    ctx = make_ctx(tmp_path, _settings_runner())
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    system.OpenThingsSettingsStep().run(ctx)
    text = " ".join(ctx.ui.lines)
    assert text.index("Date & time") < text.index("Networks")


def test_things_settings_sets_a_typed_zone_the_picker_lacks(tmp_path, monkeypatch):
    # The Android Things picker has no America/Edmonton.
    runner = _settings_runner()
    ctx = make_ctx(tmp_path, runner)
    ctx.ui.answers = ["Mars/Base", "America/Edmonton"]
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    system.OpenThingsSettingsStep().run(ctx)
    assert ["-s", "S1", "shell", "setprop", "persist.sys.timezone", "America/Edmonton"] in [
        c[1:] for c in runner.calls]
    assert not any("Mars/Base" in c for c in runner.calls for c in c)
    assert any("isn't a time zone" in l for l in ctx.ui.lines)
    assert any("America/Regina" in l for l in ctx.ui.lines if l.startswith("[ask]"))


def test_things_settings_enter_keeps_the_picked_zone(tmp_path, monkeypatch):
    runner = _settings_runner()
    ctx = make_ctx(tmp_path, runner)
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    system.OpenThingsSettingsStep().run(ctx)
    assert not any("setprop" in c for c in runner.calls)


def test_things_settings_comes_back_if_assistant_takes_the_screen(tmp_path, monkeypatch):
    # Run 2: Google Assistant's screen started just after the tool opened the
    # settings and covered them, leaving four loading dots on the display.
    gallium = ("  mCurrentFocus=Window{1 u0 com.google.assistant.gallium.client.androidthingshost/"
               "com.google.assistant.gallium.client.androidthingshost.app.GalliumActivity}\n")
    things = "  mCurrentFocus=Window{2 u0 com.android.iotlauncher/x.DefaultIoTLauncher}\n"
    runner = FakeRunner({
        ("-s", "S1", "shell", "ip", "-4", "addr", "show", "wlan0"): [
            Result(0, ""), Result(0, ""), Result(0, "    inet 10.0.0.5/24 scope global wlan0\n")],
        ("-s", "S1", "shell", "dumpsys", "window"): [Result(0, gallium), Result(0, things)],
        ("-s", "S1", "shell", "getprop", "persist.sys.timezone"): Result(0, "America/Regina\n")})
    ctx = make_ctx(tmp_path, runner)
    monkeypatch.setattr(system.time, "sleep", lambda s: None)
    system.OpenThingsSettingsStep().run(ctx)
    launches = [c for c in runner.calls if c[4:7] == ["monkey", "-p", "com.android.iotlauncher"]]
    assert len(launches) == 2


def test_all_done_reminds_to_save_the_backup_by_name(tmp_path, monkeypatch):
    from lhk import plan, bootfix
    runner = FakeRunner({
        ("-s", "S1", "shell", "getprop", "ro.build.fingerprint"):
            Result(0, "Things/x:8.1.0/OIMK.211005.001/7795499:userdebug/dev-keys\n"),
        ("-s", "S1", "shell", "wm", "size"): Result(0, "Physical size: 800x1280\n"),
        ("-s", "S1", "shell", "dumpsys", "device_policy"): Result(0, OWNER_DUMP),
    })
    monkeypatch.setattr(bootfix, "verify", lambda ctx, **kw: [])
    ctx = make_ctx(tmp_path, runner)
    ctx.state["progress_id"] = "kitchen"
    z = tmp_path / "backup" / "kitchen.zip"
    z.parent.mkdir(parents=True)
    z.write_bytes(b"PK")
    plan.VerifyStep().run(ctx)
    end = " ".join(ctx.ui.lines[ctx.ui.lines.index("All done. The display is a Home Assistant kiosk."):])
    assert str(z) in end and "safe" in end


def test_final_check_fails_when_kiosk_satellite_is_not_device_owner(tmp_path, monkeypatch):
    # HA Community #19: a display without device admin or owner reached use.
    # Without it Kiosk Satellite can't update itself silently or hold home.
    from lhk import plan, bootfix
    runner = FakeRunner({
        ("-s", "S1", "shell", "getprop", "ro.build.fingerprint"):
            Result(0, "Things/x:8.1.0/OIMK.211005.001/7795499:userdebug/dev-keys\n"),
        ("-s", "S1", "shell", "wm", "size"): Result(0, "Physical size: 800x1280\n"),
        ("-s", "S1", "shell", "dumpsys", "device_policy"): Result(0, "Device Policy Management:\n"),
    })
    monkeypatch.setattr(bootfix, "verify", lambda ctx, **kw: [])
    ctx = make_ctx(tmp_path, runner)
    with pytest.raises(system.SetupFailed, match="device owner") as e:
        plan.VerifyStep().run(ctx)
    assert "--from kiosk-grants" in str(e.value)
    assert "All done. The display is a Home Assistant kiosk." not in ctx.ui.lines
