# Changelog

What changed for people converting a display. Newest first.

## Unreleased

- **8" displays that don't report a hardware ID no longer need `--force-model`.** One SD-8501F's fastboot
  gives no `at-perm-attr-hash` (GitHub issue 6). Setup now carries on and checks the model by its screen
  size once the new system starts, before anything 8"-specific is changed. A different hardware ID is still
  refused.

## 0.2.2 (2026-11-17)

- **The mixer check no longer fails on Windows after a good write.** Reading the file back over adb came
  with Windows line endings that weren't written (GitHub issue 5). Setup now compares a checksum taken on
  the display instead.
- **Untested models (`--force-model`): the on-screen keyboard, and Wi-Fi without it.** On an SD-X701B no
  keyboard showed for the Wi-Fi password until the display had restarted, so setup now restarts it after
  adding Simple Keyboard. If there's still no keyboard, setup offers to join Wi-Fi from the computer: type
  the Wi-Fi name and password in the terminal. The password isn't shown, saved or logged. Thanks to
  scansscans (GitHub issue 5).
- **The "already unlocked" warning says what to do on a display that ran LANovo** or another custom
  system: type `flash`. There's no need to move or rename the backup.

## 0.2.1 (2026-11-17)

- **Only the zip is kept.** After a successful setup, the backup folder is removed once the zip next to it is
  checked and holds the same backup: it was the same 2.5 GB twice. `lhk restore backup/display` still works
  and uses the zip, and running setup again reuses the zip instead of backing up the converted display.

### Windows (thanks to reneh1987, kaptainamazing and scansscans, GitHub issues 1, 3 and 5)
- **The backup no longer crashes at 0%.** edl's progress bar uses characters Windows' console couldn't print.
  Setting `PYTHONIOENCODING` or `PYTHONUTF8` by hand is no longer needed.
- **The volume buttons and light sensor work on Windows.** The Windows build shipped the display's boot
  scripts with Windows line endings, and Android couldn't run them. They now always go to the display with
  Unix line endings, and the release build fails if they don't.
- **Missing the Zadig driver now says so**, and points to the driver steps, instead of a Python traceback.

### Untested models (`--force-model`)
- **An on-screen keyboard.** An SD-X701B showed no keyboard for the Wi-Fi password. With `--force-model`,
  setup installs [Simple Keyboard](https://github.com/rkkr/simple-keyboard) before Wi-Fi and makes it the
  keyboard, as the clock tool does. The SD-8 is left alone.
- **The slot check only stops when it should.** A display running from slot A, which has started successfully,
  is never stopped: slot A's own firmware is what starts it. A display running from slot B stops only if slot A has a different bootloader;
  older radio firmware alone (dsp, modem, drm, bluetooth) is a note. Both displays the old check stopped
  converted fine. Don't move the backup away to get past the check: `lhk restore` needs it.

## 0.2.0 (2026-11-16)

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
- A screenshot of the setup screen, and what its colours mean, in the README and the [guide](docs/GUIDE.md#what-youll-see).
- A photo of where the USB cable plugs in, and how to stand the display so the plug fits.
- New [guide index](docs/GUIDE.md), from choosing a guide to using the display afterwards.
- [Fitting more on the screen](docs/SIZE.md): use Kiosk Satellite's zoom, not Android's screen density.
- [Turning the screen off](docs/SCREEN.md): Kiosk Satellite's screensaver at brightness 0, with tap to wake.
  Its screen light entity can't turn the screen off on these displays.
- [Dashboards can still be an hour off](docs/TIMEZONES.md#dashboards-can-still-be-an-hour-off): the built-in
  browser uses its own old time zone rules. The fix is to format times in Home Assistant.
- [If the display doesn't show up on USB](docs/GUIDE.md#if-the-display-doesnt-show-up-on-usb), on any
  computer: replug the USB cable first, then try a USB-A port and cable.
- Mac guide: install libusb with Homebrew. What to do when macOS blocks the program, and that one display has been converted on a Mac by
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
