
# lenovo-display-ha-kiosk

<img width="500" alt="20261110_005025_preview" src="https://github.com/user-attachments/assets/2fe74d01-364a-44ea-ae53-f39feede5279" />

**Turn a stock Lenovo Smart Display 8 into a degoogled Home Assistant kiosk: a dashboard on screen and a local voice
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

## Quick start

You don't need a GitHub account, and you don't need to know any code. You'll type one command.

**1. Download the program for your computer.** One click; it's always the newest version.

| Your computer | Download |
|---|---|
| Windows 10 or 11 | [lhk-windows-x86_64.zip](https://github.com/TRusselo/lenovo-display-ha-kiosk/releases/latest/download/lhk-windows-x86_64.zip) |
| Mac with an M1 chip or newer | [lhk-macos-arm64.zip](https://github.com/TRusselo/lenovo-display-ha-kiosk/releases/latest/download/lhk-macos-arm64.zip) |
| Linux PC | [lhk-linux-x86_64.zip](https://github.com/TRusselo/lenovo-display-ha-kiosk/releases/latest/download/lhk-linux-x86_64.zip) |

**2. Unzip it** into a folder of its own. Your downloads and the display's backup will be saved there too.

**3. Open a terminal in that folder.** A terminal is the text window where you type commands:
- **Windows:** open the folder, click the address bar at the top, type `cmd`, press Enter.
- **Mac:** open Terminal, type `cd ` (with a space), drag the folder onto the window, press Return.
- **Linux:** right-click in the folder and choose **Open Terminal Here**.

**4. Type the command** and press Enter:
- Windows: `lhk\lhk setup`
- Mac and Linux: `./lhk/lhk setup`

**5. Do what it says.** It tells you each time it needs you: which buttons to hold on the display, what to set up on
its screen, and when to press Enter. That's it. If it stops for any reason, type the same command again and it
carries on where it left off.

Each system has a one-time extra step (drivers on Windows, a permission on Mac and Linux). The full guides walk
you through it: [Windows](docs/WINDOWS.md) · [Mac](docs/MACOS.md) · [Linux](docs/LINUX.md).

> [!NOTE]
> Tested end to end on **Linux** only. The Windows and Mac programs are built and their tests pass, but neither
> has converted a real display yet. If you try one, please say how it went, whether it worked or not.

### Words you'll see

- **Terminal:** the text window where you type the command. Command Prompt on Windows, Terminal on a Mac.
- **EDL mode and fastboot mode:** special ways the display can start, for backing up and installing. You get to
  them by holding volume buttons while plugging in the power; the tool tells you which ones. **The screen stays
  black in both**, which is normal. If you see the Lenovo logo, it started normally instead: unplug and try again.
- **Verified boot:** the display's lock that only allows Google's software. The tool unlocks it to install the new
  system, and `lhk restore` locks it again if you ever go back.
- **The backup:** a copy of the display's original software, saved as one zip file. It's the only way back, so
  keep it safe.

### Questions, problems, or it worked?

Post wherever suits you; no GitHub account needed for the first two:
- [Home Assistant Community thread](https://community.home-assistant.io/t/lenovo-smart-display-8-as-a-de-googled-ha-dashboard-running-kiosk-satellite-w-assist-working-testers-wanted/1033810)
- [XDA thread](https://xdaforums.com/t/lenovo-smart-display-8-home-assistant-kiosk-satellite.4808181/)
- [GitHub issues](../../issues), if you have an account

Say which computer you used, how far it got, and copy the last few lines the tool printed. The project also has a
[Hackaday.io page](https://hackaday.io/project/207337-lenovo-smart-display-8-home-assistant-kiosk-vo).

### For tinkerers

Run it from source with your own Python 3.10+: [docs/PYTHON.md](docs/PYTHON.md). Do every step by hand, or point
an AI agent at it: [devices/amber/README.md](devices/amber/README.md) has each step with the check that proves it
worked (agents: start with [AGENTS.md](AGENTS.md)).

## How it works

The tool:
- **downloads everything it needs from the original sources** and checks each file against a pinned checksum;
- **makes a full backup first**, which you can skip after a warning;
- **tells you exactly which buttons to hold, and when to let go.** The screen stays blank in those modes, so
  the tool shows which mode the display is in, and tells you when it started normally instead;
- **can stop and pick up again.** Run the same command again to continue where it stopped.

Wi-Fi, your time zone and the Home Assistant sign-in are done **on the display itself**, with its on-screen
keyboard or by scanning a QR code. The Home Assistant part also works from a browser, at an address the tool
shows you. The tool never sees your passwords.

**To go back to Google's software**, in the same folder, type `lhk\lhk restore backup\display.zip` on Windows or
`./lhk/lhk restore backup/display.zip` on Mac and Linux. It writes the backup back, then locks verified boot again
so the original software can start. It takes about 10 minutes. A backup only restores to the display it came from.
If you leave it unlocked at the end, `lhk lock` locks it later.

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
