import struct
from pathlib import Path

import pytest

from lhk.firmware import FLASH_SET, FORBIDDEN, ForbiddenPartition, extract, is_forbidden, read_gpt

DATA = Path(__file__).parent / "data"


def test_reads_56_partitions_from_amber_gpt():
    parts = {p.name: p for p in read_gpt(DATA / "gpt_amber.bin")}
    assert len(parts) == 56
    assert {"boot_a", "system_a", "vendor_a", "oem_a", "vbmeta_a", "devinfo", "persist"} <= parts.keys()
    # Known 8" layout values (from the real table)
    assert parts["devinfo"].first_lba == 7315336 and parts["devinfo"].sectors == 2048
    assert parts["oem_a"].sectors == 1024000


def test_flash_set_is_slot_a_only():
    assert FLASH_SET == ["boot_a", "system_a", "vendor_a", "oem_a", "vbmeta_a"]


@pytest.mark.parametrize("name", ["partition", "devinfo", "persist", "sbl1_a", "aboot_b", "tz_a",
                                  "rpm_b", "dsp_a", "modem_a", "drm_a", "bluetooth_a"])
def test_forbidden_names(name):
    assert is_forbidden(name)


def make_disk(path, parts):
    """A tiny GPT disk: parts is [(name, data_bytes)], 512-byte sectors."""
    entry_size, n = 128, 4
    first = 2 + (n * entry_size) // 512 + 1
    entries = bytearray(n * entry_size)
    body = bytearray()
    lba = first
    for k, (name, data) in enumerate(parts):
        sectors = (len(data) + 511) // 512
        e = bytearray(entry_size)
        e[0:16] = b"\x11" * 16
        e[32:48] = struct.pack("<QQ", lba, lba + sectors - 1)
        e[56:56 + len(name) * 2] = name.encode("utf-16le")
        entries[k * entry_size:(k + 1) * entry_size] = e
        body += data.ljust(sectors * 512, b"\0")
        lba += sectors
    header = bytearray(512)
    header[0:8] = b"EFI PART"
    header[72:88] = struct.pack("<QII", 2, n, entry_size)
    disk = bytes(512) + header + entries
    disk = disk.ljust(first * 512, b"\0") + bytes(body)
    path.write_bytes(disk)


def test_extract_sizes_match_gpt(tmp_path):
    boot = b"B" * 1024
    vbmeta = b"V" * 600
    make_disk(tmp_path / "FRW.bin", [("boot_a", boot), ("vbmeta_a", vbmeta), ("persist", b"P" * 512)])
    out = extract(tmp_path / "FRW.bin", ["boot_a", "vbmeta_a"], tmp_path / "out")
    assert out["boot_a"].read_bytes() == boot
    assert out["vbmeta_a"].read_bytes() == vbmeta.ljust(1024, b"\0")


def test_extract_rejects_forbidden_names(tmp_path):
    make_disk(tmp_path / "FRW.bin", [("persist", b"P" * 512)])
    with pytest.raises(ForbiddenPartition):
        extract(tmp_path / "FRW.bin", ["persist"], tmp_path / "out")


def test_extract_missing_partition_raises(tmp_path):
    make_disk(tmp_path / "FRW.bin", [("boot_a", b"B" * 512)])
    with pytest.raises(KeyError):
        extract(tmp_path / "FRW.bin", ["system_a"], tmp_path / "out")
