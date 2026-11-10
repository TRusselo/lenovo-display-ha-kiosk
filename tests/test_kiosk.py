import hashlib
import io
import logging
import json
from pathlib import Path

import pytest

from lhk import kiosk
from lhk.apkcert import ApkRefused
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI

DATA = Path(__file__).parent / "data"
TEST_CERT = "62367c18df59bde881a227f995078c76cd5c387ea21d2dc2ed8c28a28a43840e"
PREFS = "/data/data/me.jxl.kiosk_satellite/shared_prefs/FlutterSharedPreferences.xml"
SECRET = "S3cr3t-Pw!"


def prefs_xml(nav="true", gain="15", mode="default", password=SECRET, signed_in=True, home="false"):
    token = '    <string name="flutter.ks.ha.token">ha-secret</string>\n' if signed_in else ""
    return f"""<?xml version='1.0' encoding='utf-8' standalone='yes' ?>
<map>
{token}    <string name="flutter.ks.audio.mic_capture_mode">{mode}</string>
    <string name="flutter.ks.remote.password">{password}</string>
    <boolean name="flutter.ks.screen.hide_navigation_bar" value="{nav}" />
    <long name="flutter.ks.audio.mic_gain_db" value="{gain}" />
    <boolean name="flutter.ks.home.enabled" value="{home}" />
</map>
"""


@pytest.fixture(autouse=True)
def no_root_dance(monkeypatch):
    # Root/remount are tested in test_review_fixes; here the device is already rooted.
    monkeypatch.setattr(kiosk, "ensure_root_rw", lambda ctx: None)


def make_ctx(tmp_path, runner, **state):
    c = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1")
    c.state.update(state)
    return c


def test_cert_pin_is_the_verified_one():
    assert kiosk.KS_CERT_SHA256 == "2a77134ce11f65ba9d08bed669fdcb742a25633c5665a6135aeca30040b068fc"


def test_cert_pin_mismatch_refuses(tmp_path):
    apk = DATA / "test-signed.apk"
    with pytest.raises(ApkRefused):
        kiosk.verify_apk(apk, hashlib.sha256(apk.read_bytes()).hexdigest(), kiosk.KS_CERT_SHA256)
    kiosk.verify_apk(apk, hashlib.sha256(apk.read_bytes()).hexdigest(), TEST_CERT)


def test_sha_mismatch_refuses(tmp_path):
    with pytest.raises(kiosk.KioskError):
        kiosk.verify_apk(DATA / "test-signed.apk", "0" * 64, TEST_CERT)


class FakeHttp:
    def __init__(self, release):
        self.release = release

    def get(self, url, **kw):
        assert url.endswith("/repos/jxlarrea/kiosk-satellite/releases/latest")
        r = type("R", (), {})()
        r.json = lambda: self.release
        r.raise_for_status = lambda: None
        return r


def test_latest_release_picks_armeabi_v7a():
    rel = {"tag_name": "2026.11.13", "assets": [
        {"name": "kiosk-satellite-2026.11.13.universal.apk", "browser_download_url": "u1",
         "digest": "sha256:" + "a" * 64},
        {"name": "kiosk-satellite-2026.11.13.armeabi-v7a.apk", "browser_download_url": "u2",
         "digest": "sha256:" + "b" * 64}]}
    assert kiosk.latest_release(FakeHttp(rel)) == ("u2", "b" * 64, "kiosk-satellite-2026.11.13.armeabi-v7a.apk")


def test_grants_commands_exact(tmp_path):
    runner = FakeRunner({("-s", "S1", "shell", "dumpsys", "device_policy"): Result(0, "")})
    kiosk.GrantsStep().run(make_ctx(tmp_path, runner))
    shells = [c[4:] for c in runner.calls if c[3] == "shell" and c[4:6] != ["dumpsys", "device_policy"]]
    assert shells == [
        ["appops", "set", "me.jxl.kiosk_satellite", "REQUEST_INSTALL_PACKAGES", "allow"],
        ["appops", "set", "me.jxl.kiosk_satellite", "WRITE_SETTINGS", "allow"],
        ["appops", "set", "me.jxl.kiosk_satellite", "SYSTEM_ALERT_WINDOW", "allow"],
        ["appops", "set", "me.jxl.kiosk_satellite", "GET_USAGE_STATS", "allow"],
        ["dumpsys", "deviceidle", "whitelist", "+me.jxl.kiosk_satellite"],
        ["cmd", "notification", "allow_listener", "me.jxl.kiosk_satellite/.MediaSessionListener"],
        ["dpm", "set-active-admin", "me.jxl.kiosk_satellite/.KioskAdminReceiver"],
        ["dpm", "set-device-owner", "me.jxl.kiosk_satellite/.KioskAdminReceiver"],
    ]


def test_device_owner_skipped_if_already_set(tmp_path):
    owner = "Device Owner: \n    admin=ComponentInfo{me.jxl.kiosk_satellite/me.jxl.kiosk_satellite.KioskAdminReceiver}\n"
    runner = FakeRunner({("-s", "S1", "shell", "dumpsys", "device_policy"): Result(0, owner)})
    kiosk.GrantsStep().run(make_ctx(tmp_path, runner))
    assert not any("set-device-owner" in c for c in runner.calls for c in c)


class FakeAdmin:
    """Kiosk Satellite's remote admin API."""

    def __init__(self, runner):
        self.runner = runner
        self.logins = []
        self.patches = []

    def post(self, url, json=None, **kw):
        assert url.endswith("/api/login")
        self.logins.append(json)
        r = type("R", (), {})()
        r.status_code = 200 if json.get("password") == SECRET else 401
        r.json = lambda: {"token": "tok123"}
        r.raise_for_status = lambda: None
        return r

    def patch(self, url, json=None, headers=None, **kw):
        assert url.endswith("/api/settings") and headers["Authorization"] == "Bearer tok123"
        self.patches.append(json)
        self.runner.responses[("-s", "S1", "shell", "cat", PREFS)] = Result(
            0, prefs_xml(nav="false", gain="24", mode="voice_communication", home="true"))
        r = type("R", (), {})()
        r.json = lambda: {"ok": True, "rejected": [], "errors": {}}
        r.raise_for_status = lambda: None
        return r


def test_settings_applied_and_verified(tmp_path):
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(0, prefs_xml())})
    admin = FakeAdmin(runner)
    ctx = make_ctx(tmp_path, runner, http=admin)
    step = kiosk.SettingsStep()
    assert not step.done(ctx)
    step.run(ctx)
    assert admin.patches == [{"screen.hide_navigation_bar": False, "audio.mic_gain_db": 24, "home.enabled": True,
                              "audio.mic_capture_mode": "voice_communication"}]
    assert step.done(ctx)


def test_settings_password_never_logged(tmp_path, caplog):
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(0, prefs_xml())})
    ctx = make_ctx(tmp_path, runner, http=FakeAdmin(runner))
    with caplog.at_level(logging.DEBUG):
        kiosk.SettingsStep().run(ctx)
    assert SECRET not in caplog.text
    assert not any(SECRET in line for line in ctx.ui.lines)
    assert not any(SECRET in arg for call in runner.calls for arg in call)


def test_settings_waits_for_wizard(tmp_path, monkeypatch):
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): [Result(0, "<map></map>"), Result(0, prefs_xml())]})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, runner, http=FakeAdmin(runner))
    kiosk.SettingsStep().run(ctx)
    assert any("setup" in l.lower() for l in ctx.ui.lines)


def test_settings_opens_kiosk_satellite_before_waiting_for_its_wizard(tmp_path, monkeypatch):
    # On the Master Bedroom run the display stayed on the Android Things
    # settings: nothing opened Kiosk Satellite, so its wizard never appeared.
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): [Result(0, "<map></map>"), Result(0, prefs_xml())]})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    kiosk.SettingsStep().run(make_ctx(tmp_path, runner, http=FakeAdmin(runner)))
    launch = [i for i, c in enumerate(runner.calls)
              if "monkey" in c and kiosk.PKG in c and "android.intent.category.LAUNCHER" in c]
    first_wait = next(i for i, c in enumerate(runner.calls) if PREFS in c)
    assert launch and launch[0] < first_wait


def test_settings_wait_for_the_home_assistant_sign_in_not_just_the_admin_password(tmp_path, monkeypatch):
    # Kiosk Satellite creates its admin password before the user signs in to
    # Home Assistant. On the Master Bedroom run the tool went ahead (and
    # restarted the display) in the middle of the user's sign-in.
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): [
        Result(0, prefs_xml(signed_in=False)), Result(0, prefs_xml(signed_in=False)), Result(0, prefs_xml())]})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    admin = FakeAdmin(runner)
    reads_at_login = []
    post = admin.post
    admin.post = lambda url, **kw: (reads_at_login.append(
        sum(PREFS in c for c in runner.calls)), post(url, **kw))[1]
    kiosk.SettingsStep().run(make_ctx(tmp_path, runner, http=admin))
    assert reads_at_login and reads_at_login[0] >= 3
    assert "ha-secret" not in str(runner.calls)


def test_settings_not_done_until_signed_in_to_home_assistant(tmp_path):
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(
        0, prefs_xml(nav="false", gain="24", mode="voice_communication", home="true", signed_in=False))})
    assert not kiosk.SettingsStep().done(make_ctx(tmp_path, runner))


def test_settings_describes_the_wizard_pages(tmp_path, monkeypatch):
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(0, prefs_xml())})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, runner, http=FakeAdmin(runner))
    kiosk.SettingsStep().run(ctx)
    text = " ".join(ctx.ui.lines)
    for words in ("admin password", "Home Assistant address", "dashboard", "Finish"):
        assert words in text


def test_settings_wait_for_enter_after_finish(tmp_path, monkeypatch):
    # Run 2: Kiosk Satellite saves the Home Assistant sign-in on page 2 of 5,
    # so the tool still went ahead mid-setup. Only the user knows when they
    # pressed Finish.
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(0, prefs_xml())})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    admin = FakeAdmin(runner)
    ctx = make_ctx(tmp_path, runner, http=admin)
    order = []
    ask = ctx.ui.ask
    ctx.ui.ask = lambda text: (order.append("ask"), ask(text))[1]
    post = admin.post
    admin.post = lambda url, **kw: (order.append("login"), post(url, **kw))[1]
    kiosk.SettingsStep().run(ctx)
    assert order[:2] == ["ask", "login"]
    assert any(l.startswith("[ask]") and "Finish" in l and "Enter" in l for l in ctx.ui.lines)


def test_settings_enter_too_early_asks_again(tmp_path, monkeypatch):
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): [
        Result(0, prefs_xml(signed_in=False)), Result(0, prefs_xml())]})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, runner, http=FakeAdmin(runner))
    kiosk.SettingsStep().run(ctx)
    assert sum(l.startswith("[ask]") for l in ctx.ui.lines) == 2
    assert any("isn't signed in" in l for l in ctx.ui.lines)


def test_settings_warns_in_caps_that_setup_is_not_done_after_finish(tmp_path, monkeypatch):
    # Run 3: after Finish, Kiosk Satellite starts up, which looks like the end.
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(0, prefs_xml())})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, runner, http=FakeAdmin(runner))
    kiosk.SettingsStep().run(ctx)
    first_ask = next(i for i, l in enumerate(ctx.ui.lines) if l.startswith("[ask]"))
    alerts = [l for l in ctx.ui.lines[:first_ask] if l.startswith("[alert]")]
    assert alerts and "NOT DONE" in alerts[-1] and "FINISH" in alerts[-1]


class _Resp:
    def __init__(self, status=200, body=None, headers=None, content=b""):
        self.status_code = status
        self.headers = headers or {}
        self._body = body or {}
        self.content = content

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, n):
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_rate_limit_says_when_to_try_again_without_tokens():
    # Run 3: GitHub allows 60 lookups an hour per internet connection.
    import datetime
    reset = 1794284680
    http = type("H", (), {"get": lambda self, url, **kw: _Resp(
        403, {"message": "API rate limit exceeded"},
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(reset)})})()
    with pytest.raises(kiosk.KioskError) as e:
        kiosk.latest_release(http)
    msg = str(e.value)
    assert datetime.datetime.fromtimestamp(reset).strftime("%H:%M") in msg
    assert "token" not in msg.lower()


def test_apk_comes_from_the_saved_release_without_asking_github(tmp_path, monkeypatch):
    apk = b"apk-bytes"
    sha = hashlib.sha256(apk).hexdigest()
    d = tmp_path / "cache" / "kiosk"
    d.mkdir(parents=True)
    (d / "ks.apk").write_bytes(apk)
    (d / "release.json").write_text(json.dumps({"url": "u", "sha256": sha, "name": "ks.apk"}))
    monkeypatch.setattr(kiosk, "check_cert", lambda path, cert: None)

    class NoNetwork:
        def get(self, *a, **kw):
            raise AssertionError("asked GitHub again")
    ctx = make_ctx(tmp_path, FakeRunner(), http=NoNetwork())
    assert kiosk.fetch_apk(ctx) == d / "ks.apk"


def test_apk_lookup_and_download_are_saved(tmp_path, monkeypatch):
    apk = b"apk-bytes"
    sha = hashlib.sha256(apk).hexdigest()
    rel = {"assets": [{"name": "ks.armeabi-v7a.apk", "browser_download_url": "https://x/ks.apk",
                       "digest": "sha256:" + sha}]}
    monkeypatch.setattr(kiosk, "check_cert", lambda path, cert: None)
    http = type("H", (), {"get": lambda self, url, **kw: _Resp(body=rel) if "api.github" in url
                          else _Resp(content=apk)})()
    ctx = make_ctx(tmp_path, FakeRunner(), http=http)
    p = kiosk.fetch_apk(ctx)
    assert p.read_bytes() == apk
    assert json.loads((p.parent / "release.json").read_text())["sha256"] == sha


def test_downloads_step_fetches_kiosk_satellite_before_the_display_is_touched(tmp_path, monkeypatch):
    from lhk import plan
    got = []
    monkeypatch.setattr(plan, "fetch", lambda id_, ctx: got.append(id_))
    monkeypatch.setattr(plan.kiosk, "fetch_apk", lambda ctx: got.append("kiosk-satellite"))
    monkeypatch.setattr(plan, "Edl", lambda ctx: type("E", (), {"prepare": lambda self: got.append("edl-env")})())
    plan.DownloadsStep().run(make_ctx(tmp_path, FakeRunner()))
    assert "kiosk-satellite" in got and "edl-env" in got


def test_wizard_offers_the_browser_setup_link_above_the_warning(tmp_path, monkeypatch):
    # The wizard can be done from a browser at the display's address, port 2324,
    # which makes pasting the Home Assistant address and token easy.
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(0, prefs_xml()),
                         ("-s", "S1", "shell", "ip", "-4", "addr", "show", "wlan0"):
                             Result(0, "    inet 10.0.0.5/24 brd 10.0.0.255 scope global wlan0\n")})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, runner, http=FakeAdmin(runner))
    kiosk.SettingsStep().run(ctx)
    link = next(i for i, l in enumerate(ctx.ui.lines) if "http://10.0.0.5:2324" in l)
    warn = next(i for i, l in enumerate(ctx.ui.lines) if l.startswith("[alert] NOT DONE YET"))
    assert link < warn and "QR" in ctx.ui.lines[link]


def test_wizard_skips_the_link_without_an_address(tmp_path, monkeypatch):
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(0, prefs_xml())})
    monkeypatch.setattr(kiosk.time, "sleep", lambda s: None)
    ctx = make_ctx(tmp_path, runner, http=FakeAdmin(runner))
    kiosk.SettingsStep().run(ctx)
    assert not any(":2324" in l for l in ctx.ui.lines)
