# lenovo-display-ha-kiosk

**Turn a degoogled Lenovo Smart Display 8 into a Home Assistant kiosk: a dashboard on screen and a local voice
satellite.**

Lenovo's Smart Displays stopped getting updates, and keep losing Google features. Their clocks also drift wrong
whenever a region changes its daylight saving rules. The hardware is still good: an 8" touchscreen, far-field
mics, a speaker and a light sensor.

This tool replaces Google's software with an Android 8.1 build where
[Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite) runs your
[Home Assistant](https://www.home-assistant.io/) dashboard, listens for your wake word on the device, and plays
music from [Music Assistant](https://music-assistant.io/). Google Assistant, Cast and the phone-home check-ins
are switched off.

> [!CAUTION]
> **Vibecoded, unaudited, your risk.** The code, notes and docs were written by an AI (Claude) in conversation
> with the author, and tested on two displays. It unlocks verified boot and replaces the operating system, so
> **it can brick the display.** Make the backup the tool offers. No warranty, no support.

## Displays

|    | Display | Model | Status |
|----|---------|-------|--------|
| ✅ | Lenovo Smart Display 8 | SD-8501F | **Supported**, tested on two displays. [Device notes](devices/amber/README.md) |
| ⚠️ | Lenovo Smart Display 10 | SD-X701B | **Not supported.** Same firmware family, so `--force-model` may get partway; the sound, buttons and light sensor fixes are for the 8". [Notes](devices/README.md) |
| ❌ | Lenovo Smart Display 7 | CD-17302F | **Not supported.** Different firmware: don't use `--force-model` on it. |

The tool checks the model and refuses anything but the 8". `--force-model` skips that check, for the 10" only,
at your own risk.

## What you get

| | Stock | After |
|---|---|---|
| Assistant | Google, in the cloud | Home Assistant Assist, with wake word on the device |
| Screen | Google's ambient screen | Your Home Assistant dashboard |
| Music | Cast | Music Assistant (Sendspin), volume buttons work |
| Clock | Wrong after DST rule changes | Current time zone data |
| Brightness | Automatic | Automatic (light sensor) |
| Updates | None | Kiosk Satellite updates itself |
| Google | Everything | Off: Assistant, Cast, check-ins |

## What you need

- The display, and a USB **data** cable for its hidden USB-C port (under the rubber cover, bottom right)
- A Windows, macOS or Linux computer with about 12 GB free
- Home Assistant, ideally with a local voice pipeline
- 20 to 30 minutes; most of it is waiting

## Two ways to run it

**1. Standalone program (most people).** Nothing else to install.

1. Download the zip for your system from [Releases](../../releases).
2. Unzip it into a folder.
3. Open a terminal (Command Prompt on Windows) in that folder.
4. Run `lhk\lhk setup` on Windows, or `./lhk/lhk setup` on macOS and Linux, and follow the prompts.

Step by step, with the one-time USB setup for each system: [Windows](docs/WINDOWS.md) · [macOS](docs/MACOS.md)
· [Linux](docs/LINUX.md).

> [!NOTE]
> Tested end to end on **Linux** only. The Windows and macOS programs are built and their tests pass, but
> neither has converted a real display yet. If you try one, please [open an issue](../../issues) to say how it
> went, whether it worked or not.

**2. Python (if you like to see and run the code yourself).** Same tool, run from source with your own Python
3.10+: [docs/PYTHON.md](docs/PYTHON.md).

Either way, the tool:
- **downloads everything it needs from the original sources** and checks each file against a pinned checksum;
- **makes a full backup first**, which you can skip after a warning;
- **tells you exactly which buttons to hold, and when to let go.** The screen stays blank in those modes, so
  the tool shows which mode the display is in, and tells you when it started normally instead;
- **can stop and pick up again.** Run the same command again to continue where it stopped.

Wi-Fi, your time zone and the Home Assistant sign-in are done **on the display itself**, with its on-screen
keyboard or by scanning a QR code. The tool never sees your passwords.

**To go back to stock:** `lhk restore backup/display.zip` (or the `backup/display` folder) writes the backup
back, then locks verified boot again so stock can start. A backup only restores to the display it came from. The
backup step saves it as one zip file: copy that somewhere safe and keep it private. If a restore leaves the display
unlocked, `lhk lock` locks it. Setup takes 20 to 30 minutes, including the downloads.

**By hand, or for AI agents:** [devices/amber/README.md](devices/amber/README.md) has every step, with the check
that proves it worked. Agents: start with [AGENTS.md](AGENTS.md).

## Credits

> [!IMPORTANT]
> **This is built on other people's work.**
> - **deadman96385:** the AVB unlock and the [XDA thread](https://xdaforums.com/t/lenovo-smart-display-8-10-amber-blueberry-avb-bootloader-unlock-firmware.4472049/)
>   that made these displays hackable.
> - **RYuhMine:** the [Android Things userdebug archive](https://archive.org/details/android-things-oreo-builds).
> - **jxlarrea:** [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite).
> - **dimatx:** the first Lenovo Smart Display write-up for Kiosk Satellite.
> - **bkerler:** [edl](https://github.com/bkerler/edl).
> - **[echo-dot-assist](https://github.com/Gamer92000/echo-dot-assist):** the inspiration and conventions.
>
> This repo links to the firmware, the unlock tool and edl. It doesn't host them: the tool downloads them at
> run time from their own sources.

## Licence

MIT, for this repository's own code and docs ([LICENSE](LICENSE)). Downloaded components keep their own terms.
