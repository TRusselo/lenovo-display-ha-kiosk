# Release design: Lenovo Smart Display → Home Assistant Kiosk Satellite

Status: draft for approval, 2026-11-08. It will move into the new repo once approved.

## Intent

Let someone with a stock Lenovo Smart Display 8 (SD-8501F) and a USB cable turn
it into a de-Googled Home Assistant voice satellite and dashboard. The result
should match the two displays converted by hand: same firmware, fixes and
settings. Today that took days of research and debugging. The release should
reduce it to following prompts.

**Why:** these displays stopped getting updates. They keep failing in small
ways: DST changes leave the clock wrong, and Google keeps winding down
features. A display that runs [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite)
against Home Assistant is still good hardware. Inspired by
[echo-dot-assist](https://github.com/Gamer92000/echo-dot-assist), and follows
its conventions where they fit.

## Who it's for

Someone who:
- has the display and a **data** USB-C cable
- can follow physical steps like "unplug power, hold volume down, plug power in,
  let go when told"
- runs **Windows** (most), **Linux** or **macOS**
- doesn't know fastboot, EDL, SELinux or Android internals, and shouldn't need to

AI agents are a second audience. They follow the manual instructions, and must
be able to check each step the same way the tool does.

## Goals

1. **Guided tool:** one command runs the whole conversion. It stops only for
   physical actions or confirmations, says exactly what to do, and shows a live
   readout of which mode the display is in (the screen stays blank).
2. **Manual instructions:** the same steps, written so a person or agent can do
   them by hand, with the same checks.
3. **Two ways to run it:**
   - **Standalone program**, for most users: no Python to install. Releases
     attach one for Windows, macOS and Linux.
   - **Python method**, for medium-experience users: the same tool run from
     source with their own Python, with install steps for each system.
4. **Download at run time, verify everything:** firmware, unlock tools and
   Kiosk Satellite come from their original sources, checked against pinned
   SHA-256 hashes, and for Kiosk Satellite also its signing certificate.
5. **Resumable:** progress is saved, so a stopped run continues where it left
   off. Every run writes a log.
6. **Safe by default:** a full stock backup over EDL before any change. It can
   be skipped, but only after a clear warning.

## Non-goals

- Models other than the SD-8501F as *supported*. The 10" (SD-X701B, "blueberry")
  and 7" (CD-17302F, "ivy") get an "untested, reports welcome" note listing the
  known differences.
- The Lenovo Smart Clock (a separate effort).
- Setting up Home Assistant itself, the Assist pipeline or Music Assistant.
- Fixing Kiosk Satellite bugs. We report them upstream (e.g.
  kiosk-satellite#1358) and use settings to work around them.

## Anti-goals (failure even if it "works")

- **Redistributing firmware, Google/Lenovo binaries or the AVB unlock
  credentials.** The repo links to them; it never hosts them.
- **Handling user secrets:** no Wi-Fi passwords, Home Assistant tokens or Google
  credentials in the tool, its logs or its saved progress.
- **Editing `/init.rc`, flashing the debug partition table, or running any
  `flash-all` script unmodified.** All three are known ways to brick an 8".
- **Anything that relocks AVB** (`fastboot oem at-lock-vboot`) after
  non-stock images are flashed.
- **Silent "success":** every step checks its result on the device before
  moving on.

## Constraints and known facts

These are proven on two displays; `GUIDE.md` and `NOTES.md` have the detail.

**Modes**
- Fastboot: hold **volume down**, plug in power, let go as soon as it
  appears (`18d1:d00d`).
- EDL: hold **volume up + down** (`05c6:9008`).
- Holding a button for about 15 seconds resets the display, so the tool must
  say *let go now* the moment it sees the mode.
- The screen stays blank in both modes.

**Unlock**
- `fastboot flashing unlock` is refused on this build. Use the authenticated AVB
  unlock (`at_auth_unlock.py` with the Amber credentials) to get
  `avb-locked=0`. `bootloader-locked` stays `1`, and that's fine.

**Firmware**
- Use the `OIMK.211005.001` **userdebug** full-eMMC dump
  (`OIMK.211005.001-userdebug-blueberry-FRW.7z`, archive.org).
- From it, extract only `boot_a`, `system_a`, `vendor_a`, `oem_a` and `vbmeta_a`,
  by reading its GPT.
- Flash slot A only. Never the partition table or the bootloader chain. Slot B
  stays stock.
- Use `fastboot erase userdata`, not `format`.

**Backup**
- `edl` with `amber_bluebbery_prog_emmc_firehose_8953_ddr.mbn` reads every
  partition except `userdata` (about 2.5 GB, about 90 seconds).
- Linux needs `qcserial` blocked and a udev rule. Windows needs the WinUSB driver
  (Zadig) for EDL.

**After flashing**
- `adb root`, `adb disable-verity`, reboot, `adb remount`.
- Disable the four Google packages from `GUIDE.md`. Keep `sparrow.oem` and
  `androidthingshost`.
- Mic gain in `mixer_paths_openq624_fep.xml`.
- Kiosk Satellite (`armeabi-v7a`), its app ops and grants, and device owner.
- `screen.hide_navigation_bar=false`.

**Boot fixes (`bootfix/`)**
- `ks-boot-fix.rc` in `/system/etc/init/`.
- Two scripts labelled `dumpstate_exec`.
- `ks-volkeys.jar` in `/system/framework/`.

**Wi-Fi, time zone and Home Assistant sign-in happen on the display:**
- Wi-Fi and time zone through the Android Things settings menu, which has a zone
  picker. After flashing the screen shows Google's spinner, so the tool opens
  that menu over adb.
- Home Assistant sign-in through Kiosk Satellite's own setup wizard: QR code by
  camera, or typed on screen.

**Time zones**
- Kiosk Satellite's clock, screensaver and alarms use Android's zone.
  Dashboards use Home Assistant's.
- The build's time zone data is old, so regions with recently changed DST rules
  show the wrong time.
- The tool should install current IANA time zone data into
  `/data/misc/zoneinfo/current/` before the user picks a zone. **Unproven: needs
  a spike.**
- If that fails, document picking a zone whose offset has never changed.
- The WebView's internal copy of the time zone data likely stays old. Document
  this.

## Decided

- **Repo:** `lenovo-display-ha-kiosk`, a new public GitHub repo.
  - Description and topics carry the search terms: "degoogled", Home
    Assistant, Kiosk Satellite, Lenovo Smart Display, Android Things.
  - A Lenovo Smart Clock repo follows separately, with matching naming.
- **Licence: MIT**, the same as echo-dot-assist. It covers only our own code
  and docs.
  - **`edl` is GPL-3.0, so it's downloaded at run time and never bundled into
    the standalone programs.** Bundling it would make the release binaries GPL
    works.
  - The firmware, unlock credentials and Kiosk Satellite keep their own terms,
    and are linked, never hosted.

- **Language:** Python 3, as a single cross-platform tool. *My call; the user
  left it to me.*
- **Distribution:**
  - GitHub Releases attach standalone programs built by GitHub Actions with
    PyInstaller, one each for Windows, macOS and Linux.
  - Python-based downloads (`edl`, `at_auth_unlock.py`) run inside the bundled
    Python.
  - **Python method, a supported user path:** for medium-experience users who
    prefer to see and run the code themselves.
    - Clone the repo or download the source zip, then run the same tool with
      their own Python 3.10+. Same steps, prompts, checks and resume as the
      standalone program; only how it's started differs.
    - Dependencies install with one command (`pip install -r requirements.txt`
      in a venv, or `uv run`).
    - The docs give Python install steps for each system:
      - Windows: python.org installer with "Add to PATH" ticked, or `winget`.
      - macOS: python.org installer or Homebrew. Apple's Command Line Tools
        Python 3.9 is too old.
      - Linux: the distro's `python3` and `python3-venv` packages.
    - Agents use this path too.
- **No firmware package.** The repo holds only our own work: boot fixes, the
  volume helper source, mic-gain patch, de-Google list, grants and the tool.
  `ks-volkeys.jar` is built by CI and attached to releases, so users need no
  Java or SDK.
- **Downloads:** Google's `platform-tools` for each OS, the firmware dump, the AVB
  unlock zip and firehose (XDA links), Kiosk Satellite's newest release, and
  `edl`. All checked against pinned hashes; Kiosk Satellite also against its
  pinned signing certificate. A hash mismatch stops the run.
- **Backup:** on by default; can be skipped. Before skipping the user must
  confirm a plain warning: *if anything goes wrong, you may not be able to
  restore the display unless you can find its firmware elsewhere.* The backup
  is never uploaded and never published, because it holds unit-specific data.
- **Restore to stock:** a separate `restore` command that writes the EDL
  backup back, from the same tool, with the same prompts and checks.
  - It refuses a backup whose `SHA256SUMS` don't match, or whose partition table
    doesn't match the device.
  - It warns that the display will be back on the 2021 stock OS with
    Google services.
  - It downloads every tool before asking for EDL mode.
  - It takes the backup folder or the one-file zip the backup step writes.
  - It then locks verified boot again (`fastboot oem at-lock-vboot`, after the
    user types `lock`), because unlocked stock never gets past Google
    Assistant's loading dots. It locks only a backup that proves it is stock:
    signed `vbmeta` with no verification flags on both slots, and neither
    `boot` slot holding the userdebug boot this tool flashes. This is the one
    place the tool relocks, along with `lhk lock`, which reads the display's
    own `boot` and `vbmeta` over EDL and applies the same stock check to them.
- **Physical steps:** prompts in plain words, a live mode readout, an explicit
  "let go now" on detection, and a retry if the wrong mode appears.
- **Wi-Fi, time zone and Home Assistant sign-in** are done on the display, not in
  the tool.
- **Repo conventions from echo-dot-assist:**
  - "vibecoded, unaudited, your risk" caution and a credits box
  - supported-models table (✅/🧪)
  - per-device README with the manual steps
  - beginner `docs/WINDOWS.md`
  - `CLAUDE.md` / `AGENTS.md` for agents
  - resumable steps, `--dry-run`, `--from STEP`, a log file

## Step outline

1. **Prerequisites:** check the cable and data mode; on Windows, install the
   drivers with guided steps.
2. **Downloads:** fetch and verify everything into a local cache.
3. **Backup (EDL):** recommended; skippable with the warning.
4. **Fastboot and AVB unlock.**
5. **Flash** the userdebug images to slot A, then erase `userdata`.
6. **First boot:** `adb root`, disable verity, remount.
7. **Time zone data update** (if the spike works).
8. **On the display:** Wi-Fi and time zone in the Things menu, which the tool
   opens.
9. **De-Google** and the mic-gain patch.
10. **Kiosk Satellite:** install (verified), grants, device owner,
    `hide_navigation_bar=false`, home launcher.
11. **Boot fixes:** install, then reboot.
12. **Verify:**
    - both services running
    - Kiosk Satellite connected to the light sensor
    - no `nav_input_consumer` window
    - device owner set
    - the user presses each volume button
13. **On the display:** Kiosk Satellite's setup wizard connects to Home
    Assistant.

## Left to the builder

- Code structure, the CLI framework, how progress is saved and the log format.
- How the live mode readout looks (single line vs simple TUI).
- Exact wording of prompts, as long as it's plain and tested on a non-technical
  reader.
- Windows driver steps: Zadig for EDL, Google USB driver for fastboot/adb.
  Verify on a real Windows machine before claiming support.
- The time zone data spike, and its fallback docs.

## Open items to verify before release

- [ ] Time zone data update spike: does it work, and what does it cover?
- [ ] A full end-to-end run from stock on a third display, or a restored one
- [ ] Windows end-to-end, especially EDL drivers and the at_auth unlock
- [ ] macOS end-to-end
- [ ] Redistribution wording: link-only for firmware and credentials
