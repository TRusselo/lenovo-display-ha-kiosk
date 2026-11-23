"""Refuse anything that isn't a Lenovo Smart Display 8 (SD-8501F, "amber").

fastboot's product name (msm8x53) is shared with the 10", so the 8" is told
apart by the AVB permanent-attribute hash in fastboot, and by its 800x1280
screen once Android runs. Both were read from two real SD-8501F displays.
A display that reports no hash is checked by its screen instead (RootStep).
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

SUPPORTED = {
    "amber": {
        "name": "Lenovo Smart Display 8 (SD-8501F)",
        "product": "msm8x53",
        "perm_attr_hash": "802e273eca8ccaaa69b1623f96cd7e11",
        "screen": "800x1280",
    },
}
TARGET_FINGERPRINT = "OIMK.211005.001/7795499:userdebug"


class UnsupportedDevice(Exception):
    pass


@dataclass
class Identity:
    model: str
    product: str = ""
    current_slot: str = ""
    slot_a_successful: bool = False
    avb_locked: bool | None = None
    max_download_size: int = 0
    perm_attr_hash: str = ""
    fingerprint: str = ""
    build_type: str = ""
    screen: str = ""

    @property
    def is_target_build(self) -> bool:
        return TARGET_FINGERPRINT in self.fingerprint


def _getvar(ctx, serial, name) -> str:
    try:
        return ctx.runner.run([ctx.state["tools"].fastboot, "-s", serial, "getvar", name],
                              check=False, timeout=20).out
    except subprocess.TimeoutExpired:
        return ""       # at-vboot-state can hang on the original 2018 bootloader (GitHub issue 7)


def _value(out, key) -> str:
    m = re.search(rf"^(?:\(bootloader\)\s*)?{re.escape(key)}[:=]\s*(\S*)", out, re.M)
    return m.group(1) if m else ""


def _model_for(field, value):
    for model, spec in SUPPORTED.items():
        if value and spec[field] == value:
            return model
    return None


def _unsupported(ctx, message):
    if ctx.state.get("force_model"):
        ctx.ui.say(f"WARNING: {message} Continuing because --force-model was given. "
                   "This model is untested: it may not work, and could be bricked.")
        return "unknown"
    raise UnsupportedDevice(f"{message} Only the {SUPPORTED['amber']['name']} is supported.")


def check_fastboot_identity(ctx, serial) -> Identity:
    vboot = _getvar(ctx, serial, "at-vboot-state")
    ident = Identity(
        model="",
        product=_value(_getvar(ctx, serial, "product"), "product"),
        current_slot=_value(_getvar(ctx, serial, "current-slot"), "current-slot"),
        slot_a_successful=_value(_getvar(ctx, serial, "slot-successful:a"), "slot-successful:a") == "yes",
        max_download_size=int(_value(_getvar(ctx, serial, "max-download-size"),
                                     "max-download-size") or "0", 0),
        perm_attr_hash=_value(vboot, "at-perm-attr-hash"),
    )
    locked = _value(vboot, "avb-locked")
    if locked == "":
        # Lenovo's original 2018 bootloader can leave out avb-locked (GitHub issue 7). Then
        # "unlocked: yes" counts as unlocked; anything else stays unknown, never "locked":
        # relock must not take it as proof it has locked.
        unlocked = _value(_getvar(ctx, serial, "unlocked"), "unlocked")
        ident.avb_locked = False if unlocked == "yes" else None
    else:
        ident.avb_locked = locked == "1"
    if not ident.perm_attr_hash and ident.product == SUPPORTED["amber"]["product"]:
        # Some SD-8501Fs report no hardware ID at all (GitHub issue 6). The
        # flash is the same for either size, so let the screen size decide
        # once the new system starts, before anything 8"-specific is changed.
        if not ctx.state.get("confirm_screen"):
            ctx.ui.say("Note: this display doesn't report its hardware ID, so the model is checked by its "
                       "screen size once the new system starts.")
        ctx.state["confirm_screen"] = True
        ident.model = "unconfirmed"
        return ident
    ident.model = _model_for("perm_attr_hash", ident.perm_attr_hash) or _unsupported(
        ctx, f"This device's hardware ID ({ident.perm_attr_hash or 'none'}) isn't a known model.")
    return ident


def _prop(ctx, serial, name) -> str:
    return ctx.runner.run([ctx.state["tools"].adb, "-s", serial, "shell", "getprop", name],
                          check=False, timeout=20).out.strip()


def check_adb_identity(ctx, serial) -> Identity:
    size_out = ctx.runner.run([ctx.state["tools"].adb, "-s", serial, "shell", "wm", "size"],
                              check=False, timeout=20).out
    m = re.search(r"Physical size:\s*(\d+x\d+)", size_out)
    ident = Identity(
        model="",
        fingerprint=_prop(ctx, serial, "ro.build.fingerprint"),
        build_type=_prop(ctx, serial, "ro.build.type"),
        product=_prop(ctx, serial, "ro.product.device"),
        screen=m.group(1) if m else "",
    )
    ident.model = _model_for("screen", ident.screen) or _unsupported(
        ctx, f"This device's screen ({ident.screen or 'unknown'}) doesn't match a known model.")
    return ident
