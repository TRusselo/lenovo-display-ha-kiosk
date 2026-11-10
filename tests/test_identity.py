from pathlib import Path

import pytest

from lhk.identity import (SUPPORTED, UnsupportedDevice, check_adb_identity,
                          check_fastboot_identity)
from lhk.runner import Result, Tools
from lhk.steps import Context, Paths
from tests.fakes import FakeRunner, FakeUI

AMBER_VBOOT = """(bootloader) bootloader-locked=1
(bootloader) avb-perm-attr-set=1
(bootloader) avb-locked=0
(bootloader) avb-unlock-disabled=0
(bootloader) at-perm-attr-hash=802e273eca8ccaaa69b1623f96cd7e11
at-vboot-state:
Finished. Total time: 0.012s
"""


def fastboot_runner(vboot=AMBER_VBOOT, product="msm8x53"):
    return FakeRunner({
        ("-s", "S1", "getvar", "product"): Result(0, f"product: {product}\nFinished.\n"),
        ("-s", "S1", "getvar", "current-slot"): Result(0, "current-slot: a\nFinished.\n"),
        ("-s", "S1", "getvar", "max-download-size"): Result(0, "max-download-size: 0x1fe00000\n"),
        ("-s", "S1", "getvar", "at-vboot-state"): Result(0, vboot),
    })


def ctx(runner, **state):
    s = {"tools": Tools(adb=Path("adb"), fastboot=Path("fastboot"))}
    s.update(state)
    return Context(runner=runner, ui=FakeUI(), paths=Paths("."), state=s)


def test_amber_accepted():
    ident = check_fastboot_identity(ctx(fastboot_runner()), "S1")
    assert ident.model == "amber"
    assert ident.current_slot == "a"
    assert ident.max_download_size == 0x1FE00000


def test_parses_avb_locked_flag():
    assert check_fastboot_identity(ctx(fastboot_runner()), "S1").avb_locked is False
    locked = AMBER_VBOOT.replace("avb-locked=0", "avb-locked=1")
    assert check_fastboot_identity(ctx(fastboot_runner(locked)), "S1").avb_locked is True


def test_other_product_refused():
    other = AMBER_VBOOT.replace("802e273eca8ccaaa69b1623f96cd7e11", "00000000000000000000000000000000")
    with pytest.raises(UnsupportedDevice):
        check_fastboot_identity(ctx(fastboot_runner(other)), "S1")


def test_generic_product_name_alone_is_not_enough():
    # The 10" also reports msm8x53; only the permanent-attribute hash tells them apart.
    no_hash = "\n".join(l for l in AMBER_VBOOT.splitlines() if "perm-attr-hash" not in l)
    with pytest.raises(UnsupportedDevice):
        check_fastboot_identity(ctx(fastboot_runner(no_hash)), "S1")


def test_force_model_allows_with_warning():
    other = AMBER_VBOOT.replace("802e273eca8ccaaa69b1623f96cd7e11", "1" * 32)
    c = ctx(fastboot_runner(other), force_model=True)
    ident = check_fastboot_identity(c, "S1")
    assert ident.model == "unknown"
    assert any("untested" in line.lower() for line in c.ui.lines)


def adb_runner(size="800x1280", btype="userdebug"):
    return FakeRunner({
        ("-s", "S1", "shell", "getprop", "ro.build.fingerprint"):
            Result(0, f"Things/iot_msm8x53_som/msm8x53_som:8.1.0/OIMK.211005.001/7795499:{btype}/dev-keys\n"),
        ("-s", "S1", "shell", "getprop", "ro.product.device"): Result(0, "msm8x53_som\n"),
        ("-s", "S1", "shell", "getprop", "ro.build.type"): Result(0, f"{btype}\n"),
        ("-s", "S1", "shell", "wm", "size"): Result(0, f"Physical size: {size}\n"),
    })


def test_adb_identity_amber_userdebug():
    ident = check_adb_identity(ctx(adb_runner()), "S1")
    assert ident.model == "amber"
    assert ident.build_type == "userdebug"
    assert ident.is_target_build


def test_adb_identity_ten_inch_refused():
    with pytest.raises(UnsupportedDevice):
        check_adb_identity(ctx(adb_runner(size="1200x1920")), "S1")


def test_supported_table_has_verified_values():
    assert SUPPORTED["amber"]["perm_attr_hash"] == "802e273eca8ccaaa69b1623f96cd7e11"
    assert SUPPORTED["amber"]["screen"] == "800x1280"
