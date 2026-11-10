"""Authenticated AVB unlock, the only unlock this build allows.

`fastboot flashing unlock` is refused on the 2021 stock build. The Android
Things challenge/response unlock (at_auth_unlock.py with the Amber
credentials, from the XDA thread) gives avb-locked=0, which is what flashing
needs. bootloader-locked stays 1; that's expected.
"""
from __future__ import annotations

import os

from lhk.downloads import fetch
from lhk.identity import check_adb_identity, check_fastboot_identity
from lhk.modes import Mode, detect, wait_for_mode
from lhk.steps import Step
from lhk.uvrun import uv_path, uv_python

FASTBOOT_PROMPT = ("Unplug the display's power. Hold VOLUME DOWN, plug the power back in, and let go "
                   "after 3 to 5 seconds. The screen stays blank in this mode. If you see the Lenovo logo, "
                   "it's starting normally: unplug the power and try again.")


class UnlockFailed(Exception):
    pass


def converted_display(ctx) -> str | None:
    """The serial of the one connected display already running the userdebug
    build, or None. Two or more devices never count."""
    found = detect(ctx.runner, ctx.state["tools"])
    if len(found) != 1 or found[0][0] != Mode.ADB:
        return None
    try:
        return found[0][1] if check_adb_identity(ctx, found[0][1]).is_target_build else None
    except Exception:
        return None


def enter_fastboot(ctx) -> str:
    serial = wait_for_mode(Mode.FASTBOOT, ctx, prompt=FASTBOOT_PROMPT, timeout=180)
    bound = ctx.state.get("bound_serial")
    if bound and serial != bound:
        raise UnlockFailed(f"This is a different display ({serial}) from the one this progress is for "
                           f"({bound}). Connect that one, or use --name for a new display.")
    ctx.state["serial"] = serial
    return serial


class UnlockStep(Step):
    name = "unlock"
    title = "Unlock verified boot (AVB)"

    def done(self, ctx) -> bool:
        # A display already running the userdebug build was unlocked long ago.
        return converted_display(ctx) is not None

    def run(self, ctx) -> None:
        serial = enter_fastboot(ctx)
        if check_fastboot_identity(ctx, serial).avb_locked is False:
            ctx.ui.say("Verified boot is already unlocked.")
            return
        tool = fetch("avb-unlock", ctx)
        # at_auth_unlock.py calls plain `fastboot`: put the downloaded one first on PATH.
        env = dict(os.environ)
        env["PATH"] = os.pathsep.join([str(ctx.state["tools"].fastboot.parent), env.get("PATH", "")])
        ctx.runner.run([*uv_python(uv_path(ctx), "--with", "pycryptodome"),
                        tool / "at_auth_unlock.py", "-s", serial, tool / "creds"], timeout=300, env=env)
        if check_fastboot_identity(ctx, serial).avb_locked is not False:
            raise UnlockFailed("The unlock tool ran, but verified boot is still locked. "
                               "Nothing was changed on the display.")
        ctx.state["unlocked_now"] = True
        ctx.ui.say("Verified boot unlocked.")
