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
from lhk.runner import CommandFailed
from lhk.steps import Step
from lhk.ui import choose
from lhk.uvrun import uv_path, uv_python

FASTBOOT_PROMPT = ("Unplug the display's power. Hold VOLUME DOWN, plug the power back in, and let go "
                   "after 3 to 5 seconds. The screen stays blank in this mode. If you see the Lenovo logo, "
                   "it's starting normally: unplug the power and try again.")


class UnlockFailed(Exception):
    pass


LEGACY = ("This display still has Lenovo's original 2018 bootloader: it never got Lenovo's final update, so "
          "it doesn't know the unlock command this tool uses (GitHub issue 7). Lenovo's own unlock tool has a "
          "\"Legacy Unlock\" option for these displays, which runs: fastboot oem at-unlock-vboot "
          "default_credential. It unlocks verified boot and changes nothing else.")


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
        try:
            ctx.runner.run([*uv_python(uv_path(ctx), "--with", "pycryptodome"),
                            tool / "at_auth_unlock.py", "-s", serial, tool / "creds"], timeout=300, env=env)
        except CommandFailed as e:
            out = e.result.out
            if "at-get-vboot-unlock-challenge" not in out or "unknown command" not in out:
                raise
            self._legacy(ctx, serial)
        if check_fastboot_identity(ctx, serial).avb_locked is not False:
            raise UnlockFailed("The unlock tool ran, but verified boot is still locked. "
                               "Nothing was changed on the display.")
        ctx.state["unlocked_now"] = True
        ctx.ui.say("Verified boot unlocked.")

    def _legacy(self, ctx, serial) -> None:
        ctx.ui.say(LEGACY)
        if not choose(ctx.ui, "Type unlock to run it, or press Enter to stop: ", "unlock"):
            raise UnlockFailed("Stopped before unlocking. Nothing was changed on the display.")
        from lhk.flash import assert_safe      # flash imports this module
        args = ["oem", "at-unlock-vboot", "default_credential"]
        assert_safe(args)
        ctx.runner.run([ctx.state["tools"].fastboot, "-s", serial, *args], timeout=60)
        ctx.state["old_bootloader"] = True
