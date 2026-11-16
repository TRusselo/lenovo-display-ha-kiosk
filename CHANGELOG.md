# Changelog

What changed for people converting a display. Newest first.

## Unreleased

### Setup
- **A new setup screen.** On a terminal, each step redraws one screen: a progress bar and every step,
  ticked as it's done, with the current one highlighted. Work in progress shows on one live line, such as
  "Backing up the display: 12 of 55" or "Downloading: 312 of 704 MB, 44%", instead of a long list. Output
  piped to a file, and Windows' classic console, keep the plain scrolling text.
- **Instructions for the display stand out.** On a terminal, they're short yellow "On the display" boxes,
  and questions for you are yellow too.
- **No USB after flashing no longer stops setup.** The first start can take 10 minutes or more, and the
  display may not show up on USB until its cable is replugged. Setup now asks you to unplug the USB cable,
  count to 3 and plug it back in, then carries on.
- **Devices on adb over Wi-Fi are ignored**, instead of stopping setup as "more than one device".
- Setup says up front that it needs 12 GB free, and small downloads no longer show as "0 MB".
- **When setup stops, you see why.** The last lines of the log appear under the error, with your home folder
  shown as `~`, ready to copy into a forum post.
- **A "What's next" list at the end:** Kiosk Satellite's settings address, turning the screen off, and where
  to ask questions.
- **Makes room for Kiosk Satellite.** Cast's leftover data is cleared, and setup checks for free space
  before installing. On one display Cast's data had filled the storage.
- **Reconnects Wi-Fi** before Kiosk Satellite's setup if the display has lost it.
- **Mac: stops before EDL mode if libusb is missing**, and says to run `brew install libusb`.
- The final check fails if Kiosk Satellite isn't device owner. Without that, it can't update itself or stay
  the home screen.

### Docs
- New [guide index](docs/GUIDE.md), from choosing a guide to using the display afterwards.
- [Fitting more on the screen](docs/SIZE.md): use Kiosk Satellite's zoom, not Android's screen density.
- [Turning the screen off](docs/SCREEN.md): Kiosk Satellite's screensaver at brightness 0, with tap to wake.
  Its screen light entity can't turn the screen off on these displays.
- [Dashboards can still be an hour off](docs/TIMEZONES.md#dashboards-can-still-be-an-hour-off): the built-in
  browser uses its own old time zone rules. The fix is to format times in Home Assistant.
- Mac guide: use a USB-A to USB-C cable and install libusb with Homebrew. What to do when macOS blocks the program, and that one display has been converted on a Mac by
  running from source.
- Windows guide: what to do if antivirus removes the program, and how to check the download against the
  release checksums.
- Each system's guide links to [Words you'll see](README.md#words-youll-see).
- README and guides rewritten for people new to GitHub, with links to the Home Assistant Community thread, the
  XDA thread and the Hackaday.io page.

## 0.1.0 (2026-11-10)

First release.
- Converts a Lenovo Smart Display 8 (SD-8501F) into a Home Assistant dashboard and voice satellite running
  Kiosk Satellite.
- Ready-made programs for Windows, Mac (Apple silicon) and Linux, plus running from source with Python.
- Downloads everything from the original sources and checks each file against a pinned checksum.
- A full backup before anything changes, and `lhk restore` to go back to stock with verified boot locked again.
- Current time zone data, Google services off, working volume buttons and light sensor.
- Stops and picks up again: run the same command to carry on.
