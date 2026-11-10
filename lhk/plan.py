"""The setup, in order. Each step skips itself when its work is already done."""
from __future__ import annotations

from lhk import backup, bootfix, kiosk, system, tzdata
from lhk.downloads import fetch, load_manifest, platform_entry, require_free_space
from lhk.edl import Edl
from lhk.flash import FlashStep
from lhk.identity import check_adb_identity
from lhk.modes import Mode, wait_for_mode
from lhk.runner import Tools, platform_arch, platform_id
from lhk.steps import Step
from lhk.unlock import UnlockStep

EDL_PROMPT = ("Unplug the display's power. Hold VOLUME UP and VOLUME DOWN together, plug the power back "
              "in, and let go after 3 to 5 seconds. The screen stays blank in this mode. If you see the "
              "Lenovo logo, it's starting normally: unplug the power and try again.")


class PrerequisitesStep(Step):
    name = "prerequisites"
    title = "Check free space and get Google's adb and fastboot"

    def run(self, ctx) -> None:
        require_free_space(ctx.paths.root)
        fetch(f"platform-tools-{platform_id()}", ctx)
        ctx.state["tools"] = Tools.locate(ctx.paths.cache)


class DownloadsStep(Step):
    name = "downloads"
    title = "Download and check the firmware, tools and Kiosk Satellite"

    def run(self, ctx) -> None:
        manifest = ctx.state.get("manifest") or load_manifest()
        for id_ in ("oimk-userdebug-frw", "avb-unlock", "firehose", "edl",
                    platform_entry("uv", manifest, platform_arch())):
            fetch(id_, ctx)
        # Before the display is touched, so a GitHub limit or outage can't stop
        # the run halfway through the conversion.
        with ctx.ui.busy("Setting up edl"):
            Edl(ctx).prepare()
        with ctx.ui.busy("Downloading Kiosk Satellite"):
            kiosk.fetch_apk(ctx)


class BackupStep(Step):
    name = "backup"
    title = "Back up the stock display (EDL)"

    def run(self, ctx) -> None:
        if ctx.state.get("skip_backup"):
            if backup.confirm_skip(ctx.ui):
                ctx.ui.say("Continuing without a backup.")
                return
            ctx.ui.say("OK, making the backup.")
        out = ctx.paths.backup / ctx.state.get("progress_id", "display")
        wait_for_mode(Mode.EDL, ctx, prompt=EDL_PROMPT, timeout=180)
        backup.backup(ctx, out, Edl(ctx))
        ctx.state["backup_this_run"] = True
        z = backup.pack(ctx, out)
        ctx.ui.say(f"The backup is also saved as one file: {z}. It's named after --name (display, if "
                   "you didn't give one). Copy it somewhere safe and keep it private. lhk restore takes "
                   "this file or the folder.")


class VerifyStep(Step):
    name = "verify"
    title = "Final check"

    def run(self, ctx) -> None:
        ident = check_adb_identity(ctx, system.serial(ctx))
        problems = ([] if ident.is_target_build else ["the display isn't running the userdebug build"])
        problems += bootfix.verify(ctx)
        if problems:
            raise system.SetupFailed("Final check failed: " + "; ".join(problems) + ".")
        ctx.ui.say("All done. The display is a Home Assistant kiosk.")
        z = ctx.paths.backup / f"{ctx.state.get('progress_id', 'display')}.zip"
        if z.exists():
            ctx.ui.alert(f"SAVE YOUR BACKUP: copy {z} somewhere safe, off this computer if you can, and "
                         "keep it private. It's the only way back to this display's stock software.")


def setup_steps() -> list[Step]:
    return [
        PrerequisitesStep(), DownloadsStep(), BackupStep(), UnlockStep(), FlashStep(),
        system.RootStep(), tzdata.TzdataStep(), system.OpenThingsSettingsStep(),
        system.DegoogleStep(), system.MixerStep(), kiosk.InstallStep(), kiosk.GrantsStep(),
        kiosk.SettingsStep(), bootfix.BootFixStep(), VerifyStep(),
    ]
