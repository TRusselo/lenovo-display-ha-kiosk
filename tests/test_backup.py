import hashlib
import shutil
import struct
from pathlib import Path

import pytest

from lhk import backup as bk
from lhk.steps import Context, Paths
from tests.fakes import FakeUI

GPT = Path(__file__).parent / "data" / "gpt_amber.bin"


class FakeEdl:
    """Pretends to be a display in EDL mode with the real 8" partition table.
    Partition contents are tiny, so sizes are scaled: 1 byte per sector."""

    def __init__(self, gpt_bytes=None, drop_after_reads=None):
        self.gpt_bytes = gpt_bytes or GPT.read_bytes()
        self.calls = []
        self.reads = 0
        self.drop_after_reads = drop_after_reads
        self.written = {}

    def _size(self, name):
        from lhk.firmware import read_gpt
        tmp = Path(self._tmp) / "g.bin"
        tmp.write_bytes(self.gpt_bytes)
        return {p.name: p.sectors for p in read_gpt(tmp)}[name]

    def dump_gpt(self, dest_dir):
        self.calls.append(("gpt",))
        Path(dest_dir).mkdir(parents=True, exist_ok=True)
        (Path(dest_dir) / "gpt_main0.bin").write_bytes(self.gpt_bytes)

    def read(self, names, dest_dir):
        for n in names:
            if self.drop_after_reads is not None and self.reads >= self.drop_after_reads:
                raise ConnectionError("display dropped off USB")
            self.calls.append(("r", n))
            (Path(dest_dir) / f"{n}.bin").write_bytes(n.encode()[:1] * self._size(n))
            self.reads += 1

    def write(self, name, file):
        self.calls.append(("w", name))
        self.written[name] = Path(file).read_bytes()

    def erase(self, name):
        self.calls.append(("e", name))


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    # Scale partition sizes down: 1 byte per sector instead of 512.
    monkeypatch.setattr(bk, "SECTOR", 1)
    c = Context(runner=None, ui=FakeUI(answers=["restore"] * 10), paths=Paths(tmp_path / "work"))
    return c


def make_edl(tmp_path, **kw):
    e = FakeEdl(**kw)
    e._tmp = tmp_path
    return e


def test_backup_reads_priority_partitions_first(tmp_path, ctx):
    edl = make_edl(tmp_path)
    out = tmp_path / "bk"
    bk.backup(ctx, out, edl)
    reads = [c[1] for c in edl.calls if c[0] == "r"]
    assert reads[:4] == ["vbmeta_a", "vbmeta_b", "devinfo", "factory"]
    assert "userdata" not in reads
    assert bk.verify_backup(out) == []


def test_backup_resumes_and_skips_complete_files(tmp_path, ctx):
    edl = make_edl(tmp_path, drop_after_reads=10)
    out = tmp_path / "bk"
    with pytest.raises(ConnectionError):
        bk.backup(ctx, out, edl)
    first_reads = [c[1] for c in edl.calls if c[0] == "r"]
    edl2 = make_edl(tmp_path)
    bk.backup(ctx, out, edl2)
    second_reads = [c[1] for c in edl2.calls if c[0] == "r"]
    assert not set(first_reads) & set(second_reads)
    assert bk.verify_backup(out) == []


def test_verify_backup_detects_bad_hash(tmp_path, ctx):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    f = out / "partitions" / "persist.bin"
    f.write_bytes(b"X" * f.stat().st_size)
    problems = bk.verify_backup(out)
    assert any("persist" in p for p in problems)


def test_verify_backup_detects_missing_partition(tmp_path, ctx):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    (out / "partitions" / "devinfo.bin").unlink()
    assert any("devinfo" in p for p in bk.verify_backup(out))


def test_restore_refuses_on_gpt_mismatch(tmp_path, ctx):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    other = bytearray(GPT.read_bytes())
    i = other.find(b"EFI PART")
    other[i + 56:i + 72] = b"\x22" * 16          # a different display's disk GUID
    edl = make_edl(tmp_path, gpt_bytes=bytes(other))
    with pytest.raises(bk.BackupMismatch):
        bk.restore(ctx, out, edl)
    assert not edl.written


def test_restore_refuses_bad_backup(tmp_path, ctx):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    (out / "partitions" / "boot_a.bin").write_bytes(b"corrupt")
    edl = make_edl(tmp_path)
    with pytest.raises(bk.BackupMismatch):
        bk.restore(ctx, out, edl)
    assert not edl.written


def test_restore_writes_every_partition_except_userdata_and_gpt(tmp_path, ctx):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    edl = make_edl(tmp_path)
    bk.restore(ctx, out, edl)
    assert "userdata" not in edl.written and "gpt_main0" not in edl.written
    assert {"boot_a", "system_b", "persist", "devinfo"} <= edl.written.keys()
    assert len(edl.written) == 55


def test_skip_requires_typed_confirmation():
    ui = FakeUI(answers=["yes"])
    assert bk.confirm_skip(ui) is False
    ui = FakeUI(answers=["skip"])
    assert bk.confirm_skip(ui) is True
    assert any(bk.SKIP_WARNING in line for line in ui.lines)


def test_skip_warning_text_is_exact():
    assert bk.SKIP_WARNING == ("If anything goes wrong, you may not be able to restore this "
                               "display unless you can find its firmware elsewhere.")


def test_backup_shows_progress_per_partition(tmp_path, ctx):
    bk.backup(ctx, tmp_path / "bk", make_edl(tmp_path))
    busy = [l for l in ctx.ui.lines if l.startswith("[busy] Backing up")]
    assert busy and busy[0].startswith("[busy] Backing up vbmeta_a (1 of ")


def test_restore_shows_progress_per_partition(tmp_path, ctx):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    edl = make_edl(tmp_path)
    bk.restore(ctx, out, edl)
    written = [c for c in edl.calls if c[0] == "w"]
    busy = [l for l in ctx.ui.lines if l.startswith("[busy] Writing")]
    assert len(busy) == len(written) and f"(1 of {len(written)})" in busy[0]
    assert "[busy] Erasing user data" in ctx.ui.lines


# R3-U1: one file to copy and keep safe.
def test_pack_then_unpack_gives_back_a_verified_backup(tmp_path, ctx):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    z = bk.pack(ctx, out)
    assert z.name == "bk.zip" and z.exists()
    folder = bk.unpack(ctx, z, tmp_path / "restore")
    assert bk.verify_backup(folder) == []


def test_unpack_skips_a_folder_already_unpacked(tmp_path, ctx, monkeypatch):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    z = bk.pack(ctx, out)
    bk.unpack(ctx, z, tmp_path / "restore")
    monkeypatch.setattr(bk.zipfile.ZipFile, "extractall", lambda *a, **k: pytest.fail("unpacked twice"))
    bk.unpack(ctx, z, tmp_path / "restore")


def test_unpack_refuses_paths_outside_its_folder(tmp_path, ctx):
    import zipfile
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("../outside.bin", b"x")
    with pytest.raises(bk.BackupMismatch):
        bk.unpack(ctx, z, tmp_path / "restore")
    assert not (tmp_path / "outside.bin").exists()


def test_unpack_checks_free_space_first(tmp_path, ctx, monkeypatch):
    out = tmp_path / "bk"
    bk.backup(ctx, out, make_edl(tmp_path))
    z = bk.pack(ctx, out)
    monkeypatch.setattr(bk.shutil, "disk_usage", lambda p: type("U", (), {"free": 1})())
    with pytest.raises(bk.BackupMismatch, match="space"):
        bk.unpack(ctx, z, tmp_path / "restore")
