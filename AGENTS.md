# For AI agents

## Converting a display

You're probably helping someone convert a Lenovo Smart Display 8 (SD-8501F).

- **Prefer the tool.** `python -m lhk setup` checks every step. Run it, and relay its physical prompts word for
  word: the person has to hold the buttons.
- **By hand:** follow [devices/amber/README.md](devices/amber/README.md) in order. **Run each step's Check and
  read its output before going on.** If a Check fails, stop and tell the person. Don't improvise.
- **Never:**
  - flash the partition table, `sbl1`/`aboot`/`tz`/`rpm`, `devinfo`, `persist`, `dsp`, `modem`, `drm` or
    `bluetooth`
  - run `fastboot oem at-lock-vboot`, `fastboot flashing lock` or `fastboot format` yourself. `lhk restore`
    locks verified boot on its own, and only after checking the backup is stock
  - edit `/init.rc`
  - edit Kiosk Satellite's `shared_prefs` file directly
  - disable `com.google.android.things.sparrow.oem`
  - run `pm clear me.jxl.kiosk_satellite`
- **Physical steps:** the screen is blank in fastboot and EDL. Find the mode from the USB IDs: `18d1:d00d` is
  fastboot, `05c6:9008` is EDL. Tell the person: unplug the power, hold the button(s), plug the power in, and let
  go after 3 to 5 seconds (held for about 15 seconds, they reset the display). A display that starts
  normally shows the Lenovo logo and doesn't appear on USB at all: unplug and try again.
- **Secrets:** never ask for, print or store Wi-Fi passwords, Home Assistant tokens or the Kiosk Satellite admin
  password. The person enters those on the display.
- **Backups:** never upload or share a backup. It holds data unique to that display.

## Working on this repo

- **Layout:** Python package in `lhk/`, one module per concern; tests in `tests/`, which use fakes and never need
  hardware or network.
- **TDD:** write the failing test first.
- **Run the tests:** `python -m pytest -q`.
- **Every external command** goes through `ctx.runner`. Every fastboot command goes through `flash.assert_safe`.
- **Downloads** are pinned in `manifest.json` with SHA-256. Never host firmware, credentials or edl here.
- **Design and decisions:** `docs/design.md`, the plan in `docs/plans/`, and field notes in `docs/findings/`.
