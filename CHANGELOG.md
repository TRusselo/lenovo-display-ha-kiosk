# Changelog

What changed for people converting a display. Newest first.

## Unreleased

### Setup
- **Clearer progress.** Setup lists every step at the start, numbers each one as it begins ("Step 5 of 15"),
  matching the [manual](devices/amber/README.md), and marks it done when it finishes.
- **Long waits show they're still working.** On a terminal, a spinner and the time taken so far, and each
  finished job says how long it took.
- **Instructions for the display stand out more.** "DO THIS ON THE DISPLAY" is in colour on a terminal.
- **When setup stops, you see why.** The last lines of the log appear under the error, with your home folder
  shown as `~`, ready to copy into a forum post.
- **A "What's next" list at the end:** Kiosk Satellite's settings address, turning the screen off, and where
  to ask questions.
- The final check fails if Kiosk Satellite isn't device owner. Without that, it can't update itself or stay
  the home screen.

### Docs
- New [guide index](docs/GUIDE.md), from choosing a guide to using the display afterwards.
- [Turning the screen off](docs/SCREEN.md): Kiosk Satellite's screensaver at brightness 0, with tap to wake.
  Its screen light entity can't turn the screen off on these displays.
- [Dashboards can still be an hour off](docs/TIMEZONES.md#dashboards-can-still-be-an-hour-off): the built-in
  browser uses its own old time zone rules. The fix is to format times in Home Assistant.
- Mac guide: what to do when macOS blocks the program, and that one display has been converted on a Mac by
  running from source.
- Windows guide: what to do if antivirus removes the program, and how to check the download against the
  release checksums.
- Each system's guide links to [Words you'll see](README.md#words-youll-see).
- README and guides rewritten for people new to GitHub, with links to the Home Assistant Community thread, the
  XDA thread and the Hackaday.io page.

### Fixes
- Unpacking downloads works on Python 3.10, which has no tar extraction filters.

## 0.1.0 (2026-11-10)

First release.
- Converts a Lenovo Smart Display 8 (SD-8501F) into a Home Assistant dashboard and voice satellite running
  Kiosk Satellite.
- Ready-made programs for Windows, Mac (Apple silicon) and Linux, plus running from source with Python.
- Downloads everything from the original sources and checks each file against a pinned checksum.
- A full backup before anything changes, and `lhk restore` to go back to stock with verified boot locked again.
- Current time zone data, Google services off, working volume buttons and light sensor.
- Stops and picks up again: run the same command to carry on.
