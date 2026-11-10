import hashlib
import io
import json
import os
import threading
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from lhk import downloads
from lhk.downloads import DiskTooFull, HashMismatch, fetch, load_manifest, require_free_space
from lhk.steps import Context, Paths
from tests.fakes import FakeUI


class RangeHandler(SimpleHTTPRequestHandler):
    """Serves files with HTTP Range support; counts bytes sent."""
    sent = 0

    def log_message(self, *a):
        pass

    def do_GET(self):
        path = self.translate_path(self.path)
        data = open(path, "rb").read()
        rng = self.headers.get("Range")
        start = 0
        if rng:
            start = int(rng.split("=")[1].split("-")[0])
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
        else:
            self.send_response(200)
        body = data[start:]
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        RangeHandler.sent += len(body)


@pytest.fixture
def server(tmp_path):
    root = tmp_path / "srv"
    root.mkdir()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(RangeHandler, directory=str(root)))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    RangeHandler.sent = 0
    yield root, f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def make_zip(path, files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    path.write_bytes(buf.getvalue())
    return hashlib.sha256(buf.getvalue()).hexdigest(), len(buf.getvalue())


def ctx_for(root, manifest):
    c = Context(runner=None, ui=FakeUI(), paths=Paths(root))
    c.state["manifest"] = manifest
    return c


def test_verifies_and_caches(tmp_path, server):
    srv, url = server
    sha, size = make_zip(srv / "a.zip", {"a/hello.txt": "hi"})
    manifest = {"x": {"id": "x", "url": f"{url}/a.zip", "sha256": sha, "size": size,
                      "unpack": "zip", "platform": None}}
    c = ctx_for(tmp_path / "work", manifest)
    out = fetch("x", c)
    assert (out / "a" / "hello.txt").read_text() == "hi"
    sent = RangeHandler.sent
    assert fetch("x", c) == out          # second call uses the cache
    assert RangeHandler.sent == sent


def test_hash_mismatch_deletes_and_raises(tmp_path, server):
    srv, url = server
    _, size = make_zip(srv / "a.zip", {"f": "data"})
    manifest = {"x": {"id": "x", "url": f"{url}/a.zip", "sha256": "0" * 64, "size": size,
                      "unpack": "zip", "platform": None}}
    c = ctx_for(tmp_path / "work", manifest)
    with pytest.raises(HashMismatch):
        fetch("x", c)
    assert not any(c.paths.cache.rglob("a.zip*"))


def test_resume_after_partial_download(tmp_path, server):
    srv, url = server
    sha, size = make_zip(srv / "big.zip", {"blob": "z" * 50000})
    manifest = {"x": {"id": "x", "url": f"{url}/big.zip", "sha256": sha, "size": size,
                      "unpack": None, "platform": None}}
    c = ctx_for(tmp_path / "work", manifest)
    part = c.paths.cache / "downloads" / "big.zip.part"
    part.parent.mkdir(parents=True)
    part.write_bytes((srv / "big.zip").read_bytes()[:1000])
    out = fetch("x", c)
    assert out.read_bytes() == (srv / "big.zip").read_bytes()
    assert RangeHandler.sent == size - 1000


def test_refuses_when_disk_low(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads.shutil, "disk_usage",
                        lambda p: type("U", (), {"free": 5 * 1024 ** 3})())
    with pytest.raises(DiskTooFull):
        require_free_space(tmp_path)


def test_cache_path_with_spaces(tmp_path, server):
    srv, url = server
    sha, size = make_zip(srv / "a.zip", {"x.txt": "ok"})
    manifest = {"x": {"id": "x", "url": f"{url}/a.zip", "sha256": sha, "size": size,
                      "unpack": "zip", "platform": None}}
    c = ctx_for(tmp_path / "José Smith" / "my files", manifest)
    assert (fetch("x", c) / "x.txt").read_text() == "ok"


def test_repo_manifest_is_complete():
    m = load_manifest()
    for id_ in ("platform-tools-windows", "platform-tools-darwin", "platform-tools-linux",
                "oimk-userdebug-frw", "avb-unlock", "firehose", "edl"):
        e = m[id_]
        assert len(e["sha256"]) == 64 and e["size"] > 0 and e["url"].startswith("https://")


def test_unpacks_tar_gz(tmp_path, server):
    import tarfile
    srv, url = server
    src = tmp_path / "pkg"
    (src / "uv-x").mkdir(parents=True)
    (src / "uv-x" / "uv").write_text("bin")
    with tarfile.open(srv / "uv.tar.gz", "w:gz") as t:
        t.add(src / "uv-x", arcname="uv-x")
    data = (srv / "uv.tar.gz").read_bytes()
    manifest = {"x": {"id": "x", "url": f"{url}/uv.tar.gz", "sha256": hashlib.sha256(data).hexdigest(),
                      "size": len(data), "unpack": "tar.gz", "platform": None}}
    out = fetch("x", ctx_for(tmp_path / "work", manifest))
    assert (out / "uv-x" / "uv").read_text() == "bin"


def test_entry_for_this_platform():
    from lhk.downloads import platform_entry
    m = {"uv-linux-x86_64": {}, "uv-windows-x86_64": {}, "uv-darwin-arm64": {}}
    assert platform_entry("uv", m, "linux-x86_64") == "uv-linux-x86_64"
    with pytest.raises(KeyError):
        platform_entry("uv", m, "linux-riscv64")


@pytest.mark.skipif(os.name == "nt", reason="no executable bit on Windows")
def test_zip_unpack_keeps_executable_bit(tmp_path):
    # Google's platform-tools zip stores adb and fastboot as 0755. Python's
    # extractall drops that, and a fastboot that can't run looked like "no device".
    import zipfile
    from lhk import downloads
    archive = tmp_path / "pt.zip"
    with zipfile.ZipFile(archive, "w") as z:
        tool = zipfile.ZipInfo("platform-tools/fastboot")
        tool.external_attr = 0o100755 << 16
        z.writestr(tool, "#!/bin/sh\n")
        z.writestr("platform-tools/NOTICE.txt", "text")
    out = tmp_path / "out"
    downloads._unpack("zip", archive, out)
    assert os.access(out / "platform-tools" / "fastboot", os.X_OK)
    assert not os.access(out / "platform-tools" / "NOTICE.txt", os.X_OK)


def test_download_and_unpack_show_progress(tmp_path, server):
    import tarfile
    srv, url = server
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "f").write_text("x")
    with tarfile.open(srv / "p.tar.gz", "w:gz") as t:
        t.add(src / "f", arcname="f")
    data = (srv / "p.tar.gz").read_bytes()
    manifest = {"x": {"id": "x", "url": f"{url}/p.tar.gz", "sha256": hashlib.sha256(data).hexdigest(),
                      "size": len(data), "unpack": "tar.gz", "platform": None}}
    ctx = ctx_for(tmp_path / "work", manifest)
    fetch("x", ctx)
    assert any(l.startswith("[busy] Downloading p.tar.gz") for l in ctx.ui.lines)
    assert "[busy] Unpacking p.tar.gz" in ctx.ui.lines


# CI: Python 3.10 before 3.10.12 has no extractall(filter=...).
def _old_tarfile(monkeypatch):
    import tarfile
    if not hasattr(tarfile, "data_filter"):
        return  # already an old Python: nothing to fake
    monkeypatch.delattr(tarfile, "data_filter")
    real = tarfile.TarFile.extractall

    def no_filter(self, path=".", members=None, *, numeric_owner=False, **kw):
        if kw:
            raise TypeError(f"extractall() got an unexpected keyword argument {next(iter(kw))!r}")
        return real(self, path, members, numeric_owner=numeric_owner, filter="fully_trusted")
    monkeypatch.setattr(tarfile.TarFile, "extractall", no_filter)


def test_unpacks_tar_gz_on_pythons_without_extract_filters(tmp_path, server, monkeypatch):
    _old_tarfile(monkeypatch)
    test_unpacks_tar_gz(tmp_path, server)


def test_tar_paths_outside_the_folder_are_refused_without_extract_filters(tmp_path, monkeypatch):
    import io
    import tarfile
    from lhk import downloads
    _old_tarfile(monkeypatch)
    archive = tmp_path / "evil.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        info = tarfile.TarInfo("../outside")
        info.size = 1
        t.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="outside"):
        downloads._unpack("tar.gz", archive, tmp_path / "out")
    assert not (tmp_path / "outside").exists()
