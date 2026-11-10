from pathlib import Path

from lhk import edl as edl_mod
from lhk.downloads import load_manifest
from lhk.runner import Result, platform_arch
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI


def test_runs_edl_through_uv_with_its_own_requirements(tmp_path, monkeypatch):
    uv_dir = tmp_path / "uv"
    (uv_dir / "uv-x").mkdir(parents=True)
    uv = uv_dir / "uv-x" / ("uv.exe" if platform_arch().startswith("windows") else "uv")
    uv.write_text("")
    edl_dir = tmp_path / "edl"
    (edl_dir / "edl-abc").mkdir(parents=True)
    (edl_dir / "edl-abc" / "edl.py").write_text("")
    (edl_dir / "edl-abc" / "requirements.txt").write_text("")
    fw = tmp_path / "fw"
    fw.mkdir()
    dirs = {"edl": edl_dir, "firehose": fw}
    monkeypatch.setattr(edl_mod, "fetch", lambda id_, ctx: dirs[id_])
    monkeypatch.setattr(edl_mod, "uv_path", lambda ctx: uv)
    runner = FakeRunner()
    ctx = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    edl_mod.Edl(ctx).read(["boot_a"], tmp_path / "out")
    cmd = runner.calls[0]
    assert cmd[:8] == [str(uv), "run", "--no-project", "--python", "3.12", "--with-requirements",
                       str(edl_dir / "edl-abc" / "requirements.txt"), "python"]
    assert cmd[8:11] == [str(edl_dir / "edl-abc" / "edl.py"), "r", "boot_a"]
    assert cmd[-2:] == ["--memory=eMMC", f"--loader={fw / edl_mod.LOADER}"]


def test_manifest_has_uv_for_supported_platforms():
    m = load_manifest()
    for plat in ("windows-x86_64", "darwin-arm64", "darwin-x86_64", "linux-x86_64", "linux-aarch64"):
        assert f"uv-{plat}" in m


def test_platform_arch_shape():
    os_, arch = platform_arch().split("-")
    assert os_ in ("windows", "darwin", "linux") and arch


def test_dump_gpt_reads_the_first_34_sectors(tmp_path, monkeypatch):
    # edl's own "gpt" command (pinned 1cda1a6) prints "Dumped GPT ... to" but
    # never writes the file, so the table is read as raw sectors instead:
    # protective MBR, GPT header and 128 x 128-byte entries = 34 x 512 bytes.
    (tmp_path / "edl" / "edl-abc").mkdir(parents=True)
    (tmp_path / "fw").mkdir()
    dirs = {"edl": tmp_path / "edl", "firehose": tmp_path / "fw"}
    monkeypatch.setattr(edl_mod, "fetch", lambda id_, ctx: dirs[id_])
    monkeypatch.setattr(edl_mod, "uv_path", lambda ctx: tmp_path / "uv")
    runner = FakeRunner()
    ctx = Context(runner=runner, ui=FakeUI(), paths=Paths(tmp_path))
    out = tmp_path / "out"
    edl_mod.Edl(ctx).dump_gpt(out)
    cmd = runner.calls[0]
    i = cmd.index(str(tmp_path / "edl" / "edl-abc" / "edl.py"))
    assert cmd[i + 1:i + 5] == ["rs", "0", "34", str(out / "gpt_main0.bin")]
    assert out.is_dir()


def test_prepare_sets_up_edls_python_without_touching_the_display():
    # uv fetches edl's packages (and maybe a Python) on first use; that must
    # happen before the display waits in EDL.
    from lhk import edl as edl_mod
    from tests.fakes import FakeRunner
    e = edl_mod.Edl.__new__(edl_mod.Edl)
    e.ctx = type("C", (), {"runner": FakeRunner()})()
    e.uv, e.requirements, e.script, e.loader = "uv", "req.txt", "edl.py", "loader"
    e.prepare()
    call = e.ctx.runner.calls[0]
    assert call[-2:] == ["-c", "pass"] and "req.txt" in call and "edl.py" not in call
