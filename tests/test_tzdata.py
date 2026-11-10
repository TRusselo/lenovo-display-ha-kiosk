import pytest
import struct
from pathlib import Path

from lhk import tzdata
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI

@pytest.fixture(autouse=True)
def no_root_dance(monkeypatch):
    # The device in these tests is already rooted; ensure_root_rw has its own tests.
    monkeypatch.setattr(tzdata, "ensure_root_rw", lambda ctx: None)


ASSET = Path(__file__).parent.parent / "assets" / "tzdata" / "tzdata"


def test_bundled_tzdata_layout():
    b = ASSET.read_bytes()
    assert b[:6] == b"tzdata"
    index, data, zonetab = struct.unpack(">iii", b[12:24])
    assert index == 24 and (data - index) % 52 == 0
    names = [b[index + i * 52:index + i * 52 + 40].rstrip(b"\0").decode()
             for i in range((data - index) // 52)]
    assert "America/Edmonton" in names and "America/Winnipeg" in names
    assert names == sorted(names)
    assert not b[zonetab:].startswith(b"#")
    assert tzdata.version(b) >= "2026f"


def make_ctx(tmp_path, runner):
    c = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    c.state.update(tools=Tools(adb=Path("adb"), fastboot=Path("fastboot")), serial="S1")
    return c


def test_done_when_device_has_bundled_version(tmp_path):
    v = tzdata.version(ASSET.read_bytes())
    runner = FakeRunner({("-s", "S1", "shell", "head", "-c", "12", tzdata.DEVICE_PATH): Result(0, f"tzdata{v}")})
    assert tzdata.TzdataStep().done(make_ctx(tmp_path, runner))


def test_not_done_on_old_device_data(tmp_path):
    runner = FakeRunner({("-s", "S1", "shell", "head", "-c", "12", tzdata.DEVICE_PATH): Result(0, "tzdata2020a")})
    assert not tzdata.TzdataStep().done(make_ctx(tmp_path, runner))


def test_install_pushes_and_labels(tmp_path):
    runner = FakeRunner()
    tzdata.TzdataStep().run(make_ctx(tmp_path, runner))
    assert ["push", str(ASSET), tzdata.DEVICE_PATH] in [c[3:] for c in runner.calls]
    shells = [c[4:] for c in runner.calls if c[3] == "shell"]
    assert ["chmod", "644", tzdata.DEVICE_PATH] in shells
    assert ["restorecon", tzdata.DEVICE_PATH] in shells


def test_zone_names_come_from_the_bundled_file():
    names = tzdata.zone_names()
    assert "America/Edmonton" in names and "Europe/Berlin" in names and "America/Regina" in names
    assert len(names) > 300
