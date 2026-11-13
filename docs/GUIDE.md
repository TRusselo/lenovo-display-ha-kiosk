# Guide

Every page in one place, in the order you'll need them.

## How setup goes

```text
 Your computer                 The display
 -------------                 -----------
 1. Download and unzip lhk
 2. Run: lhk setup
       |
       |-- backup ------------>  EDL mode (screen black)
       |-- unlock, flash ----->  fastboot mode (screen black)
       |-- root, settings ---->  starts the new system
       |                         you: Wi-Fi and time zone
       |-- Kiosk Satellite --->  you: Home Assistant sign-in
       |-- final check
       v
 3. Keep the backup zip        Home Assistant dashboard
```

The tool tells you each time it needs you at the display. The screen stays black in EDL and fastboot modes:
that's normal.

## Before you start

Pick the guide for your computer:
- [Windows](WINDOWS.md), with [USB drivers](drivers.md)
- [Mac](MACOS.md) (Apple silicon)
- [Linux](LINUX.md)
- [Running from source](PYTHON.md): any computer with Python 3.10 or newer, including Intel Macs

New to this? [Words you'll see](../README.md#words-youll-see) explains the terms.

## During setup

- The [manual](../devices/amber/README.md) has the same steps as the tool, numbered the same way, each with
  the check that proves it worked. Read it to see what a step does, or to do it by hand.
- If the tool stops, run the same command again. It carries on where it left off.

## After setup

- [Turning the screen off](SCREEN.md), with tap to wake.
- [Time zones](TIMEZONES.md), and why a dashboard can show a time an hour off.
- Kiosk Satellite's settings: on the display, or in a browser at `http://<the display's address>:2324`. The
  tool shows the address at the end.
- To go back to Google's software: `lhk restore`, explained under "How it works" in the [README](../README.md#how-it-works).

## Problems or questions

Ask in the [Home Assistant Community thread](https://community.home-assistant.io/t/lenovo-smart-display-8-as-a-de-googled-ha-dashboard-running-kiosk-satellite-w-assist-working-testers-wanted/1033810) or the [XDA thread](https://xdaforums.com/t/lenovo-smart-display-8-home-assistant-kiosk-satellite.4808181/) (no GitHub account needed), or [open an issue](../../../issues). Say which computer you used, how far it got, and copy the last lines the tool printed.

[What's changed](../CHANGELOG.md) lists what's new in each version.
