"""Casting Helper (from the clock tool): downloaded with the other tools, installed into Kiosk Satellite
after its setup pages, through its remote admin over the adb tunnel. A download that fails is silent and
nothing is installed; an install that fails is one line, and setup goes on."""
from __future__ import annotations

import base64
import io
import json
import zipfile

import pytest

from lhk import plugin
from lhk.runner import Result
from tests.test_kiosk import PREFS, SECRET, make_ctx, prefs_xml
from tests.fakes import FakeRunner

MANIFEST = {"id": "casting-helper", "name": "Casting Helper", "version": "0.3.1", "entryClass": "x.Y"}


def _zip(manifest=MANIFEST, jar=True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("kiosk-satellite-plugin.json", json.dumps(manifest))
        if jar:
            z.writestr("plugin.jar", b"PK-jar")
    return buf.getvalue()


class _Resp:
    def __init__(self, status, body=None, content=None):
        self.status_code, self.body, self.content = status, body, content

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")


class _Http:
    """requests, faked: the download, and Kiosk Satellite's remote admin."""

    def __init__(self, zip_bytes=None, fail=False, installed=(), api_down=False):
        self.zip_bytes, self.fail, self.installed, self.api_down = zip_bytes, fail, list(installed), api_down
        self.calls = []

    def get(self, url, timeout=None, **kw):
        self.calls.append(("GET", url, None, None))
        if self.fail:
            raise OSError("no route to host")
        return _Resp(200, content=self.zip_bytes)

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers))
        if self.api_down:
            raise OSError("connection refused")
        if url.endswith("/api/login"):
            return _Resp(200 if json == {"password": SECRET} else 401, {"token": "tok123"})
        assert headers == {"Authorization": "Bearer tok123"}
        name = url.rsplit("/", 1)[-1]
        if name == "installPlugin":
            self.installed = [dict(MANIFEST, enabled=False)]
        if name == "enablePlugin":
            self.installed = [dict(MANIFEST, enabled=True, running=True)]
        return _Resp(200, {"ok": True, "data": self.installed})


def _ctx(tmp_path, http, prefs=None):
    runner = FakeRunner({("-s", "S1", "shell", "cat", PREFS): Result(0, prefs or prefs_xml())})
    return make_ctx(tmp_path, runner, http=http)


def _posts(http):
    return [(u.rsplit("/", 1)[-1], j) for m, u, j, h in http.calls if m == "POST"]


# --- the download ----------------------------------------------------------------

def test_the_helper_downloads_with_the_tools(tmp_path):
    http = _Http(_zip())
    c = _ctx(tmp_path, http)
    got = plugin.fetch(c)
    assert got and got.read_bytes() == _zip()
    assert http.calls[0][1] == plugin.URL


@pytest.mark.parametrize("http", [_Http(fail=True), _Http(b"<html>not found</html>"),
                                  _Http(_zip(dict(MANIFEST, id="something-else"))), _Http(_zip(jar=False))])
def test_a_download_that_fails_is_silent(tmp_path, http):
    c = _ctx(tmp_path, http)
    assert plugin.fetch(c) is None
    assert not c.ui.lines
    assert not plugin.cached(c)


def test_a_failed_download_keeps_no_older_copy_either(tmp_path):
    c = _ctx(tmp_path, _Http(_zip()))
    plugin.fetch(c)
    c.state["http"] = _Http(fail=True)
    assert plugin.fetch(c) is None and not plugin.cached(c)


def test_the_downloads_step_fetches_it_before_the_display_is_touched(tmp_path, monkeypatch):
    from lhk import plan
    got = []
    monkeypatch.setattr(plan, "fetch", lambda id_, ctx: None)
    monkeypatch.setattr(plan.kiosk, "fetch_apk", lambda ctx: None)
    monkeypatch.setattr(plan, "Edl", lambda ctx: type("E", (), {"prepare": lambda self: None})())
    monkeypatch.setattr(plan.plugin, "fetch", lambda ctx: got.append("casting-helper"))
    plan.DownloadsStep().run(_ctx(tmp_path, _Http(_zip())))
    assert got == ["casting-helper"]


# --- the install -----------------------------------------------------------------

def test_the_helper_is_installed_trusted_and_switched_on_through_the_adb_tunnel(tmp_path):
    http = _Http(_zip())
    c = _ctx(tmp_path, http)
    plugin.fetch(c)
    plugin.PluginStep().run(c)
    posts = _posts(http)
    assert [n for n, _ in posts] == ["login", "listPlugins", "setPluginsEnabled", "installPlugin", "enablePlugin"]
    install = dict(posts)["installPlugin"]
    assert install["trusted"] is True and base64.b64decode(install["data"]) == _zip()
    assert dict(posts)["enablePlugin"] == {"id": "casting-helper"}
    assert all(u.startswith("http://127.0.0.1:23240/api/") for m, u, j, h in http.calls if m == "POST")
    assert ["adb", "-s", "S1", "forward", "tcp:23240", "tcp:2324"] in c.runner.calls
    assert any(l.startswith("[ok]") and "Casting Helper 0.3.1" in l for l in c.ui.lines)
    # The admin password stays out of every command line, so out of the log.
    assert not any(SECRET in " ".join(call) for call in c.runner.calls)


def test_the_same_version_already_on_is_left_alone(tmp_path):
    http = _Http(_zip(), installed=[dict(MANIFEST, enabled=True, running=True)])
    c = _ctx(tmp_path, http)
    plugin.fetch(c)
    plugin.PluginStep().run(c)
    assert [n for n, _ in _posts(http)] == ["login", "listPlugins"]


def test_no_download_means_no_install_and_no_word(tmp_path):
    http = _Http(fail=True)
    c = _ctx(tmp_path, http)
    plugin.PluginStep().run(c)                    # tries the download once more, silently
    assert not _posts(http)
    assert not c.ui.lines


@pytest.mark.parametrize("http, prefs", [(_Http(_zip(), api_down=True), None),
                                         (_Http(_zip()), prefs_xml(password="wrong"))])
def test_an_install_that_fails_says_so_in_a_line_and_setup_goes_on(tmp_path, http, prefs):
    c = _ctx(tmp_path, http, prefs)
    plugin.fetch(c)
    plugin.PluginStep().run(c)                    # no exception: setup carries on
    said = [l for l in c.ui.lines if "Casting Helper" in l]
    assert len(said) == 1 and "Install from ZIP" in said[0] and str(plugin.cached(c)) in said[0]


def test_the_step_comes_after_kiosk_satellite_is_set_up_and_never_fails_the_final_check():
    from lhk import plan
    names = [s.name for s in plan.setup_steps()]
    assert names.index("casting-helper") == names.index("kiosk-settings") + 1
    assert names[-1] == "verify"
