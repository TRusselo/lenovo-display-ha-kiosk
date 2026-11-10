# lenovo-display-ha-kiosk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A public repo whose guided Python tool and matching manual instructions
turn a stock Lenovo Smart Display 8 (SD-8501F) into a degoogled Home Assistant
Kiosk Satellite, and can restore it to stock.

**Architecture:** A Python package `lhk` holds one module per concern: device
I/O, downloads, firmware, steps. A small step runner executes an ordered list
of `Step`s, saving progress after each so runs resume. Every external command
goes through one `Runner` interface, so tests use a fake and never need
hardware. Our on-device work (boot fixes, volume helper) lives in `assets/`.
CI builds the volume helper jar and the standalone programs.

**Tech Stack:**
- Python 3.10+
- `pyusb` for EDL detection
- `py7zr` to unpack the firmware
- `requests` for downloads
- `pytest`
- PyInstaller
- GitHub Actions
- JDK 17 and Android SDK `d8`, CI only, for `ks-volkeys.jar`

**Spec:** `docs/2026-11-08-release-design.md`. It moves into the repo at
`docs/design.md` in Task 1. Field-proven details are in `GUIDE.md` and
`NOTES.md`, copied into the repo as `docs/findings/`.

## Global Constraints

**Device**
- Supported device: SD-8501F only. Its fastboot `getvar product` must match
  the value recorded from the two real displays in Task 4. Anything else is
  refused unless the user passes `--force-model`, marked 🧪.
- USB IDs: fastboot `18d1:d00d`, EDL `05c6:9008`.

**Flashing**
- Flash only to slot A, only these partitions: `boot_a`, `system_a`, `vendor_a`,
  `oem_a`, `vbmeta_a`.
- Never flash `partition`, `sbl1*`, `aboot*`, `tz*`, `rpm*`, `devinfo` or
  `persist`.
- Never send `oem at-lock-vboot`, `flashing lock` or `format userdata`. Use
  `erase userdata`.
- Never write `/init.rc`.

**Downloads and secrets**
- Never bundle or host firmware, AVB credentials, `edl` or the Kiosk Satellite
  APK. Download them at run time and verify each against pinned SHA-256 in
  `manifest.json`.
- No Wi-Fi password, Home Assistant token or Kiosk Satellite admin password
  ever goes into logs, progress or output. The admin password is read from the
  device over root, used in memory only, and never printed.

**Licence and naming**
- Licence: MIT for repo content. `edl` (GPL-3.0) is never included in the
  standalone programs.
- Repo name `lenovo-display-ha-kiosk`.
- Description: "Degoogled Lenovo Smart Display 8 → Home Assistant kiosk:
  Kiosk Satellite dashboard + local voice satellite. Guided unlock, backup and
  flash for Windows, macOS and Linux."
- Topics: `home-assistant` `degoogled` `kiosk` `kiosk-satellite`
  `lenovo-smart-display` `android-things` `voice-assistant` `assist`
  `music-assistant`.

**Prompts and output**
- Prompts are plain English, with no jargon in user-facing text.
- Physical-step prompts say exactly which buttons to hold. The live readout
  shows `EDL`, `FASTBOOT`, `ADB` or `none`.
- The tool says "Let go now" within 1 s of detecting the mode.
- Backup-skip warning, word for word: "If anything goes wrong, you may not be
  able to restore this display unless you can find its firmware elsewhere."
  The user must type `skip` to confirm.

## Verified on hardware before implementation (2026-11-08, Master Bedroom display)

These override anything above or below that disagrees with them.

**Identity**
- `fastboot getvar product` is `msm8x53` and `variant` is `msm8x53_som`. Both are
  generic and probably the same on the 10", so they **can't identify an
  SD-8501F on their own.**
- Identify the 8" instead by:
  - adb `wm size` = `Physical size: 800x1280`, with density 300; the 10" is
    1920×1200
  - plus fastboot `at-perm-attr-hash` = `802e273eca8ccaaa69b1623f96cd7e11`,
    pending a match on the Kitchen display
- After the AVB unlock, `getvar unlocked` reads **`yes`**, and `avb-locked=0`,
  `bootloader-locked=1`. `GUIDE.md`/`NOTES.md` say `unlocked:no`, which is out
  of date.

**What's flashed** (slot A, per-partition hashes compared with the stock backup)
- Changed from stock: `boot`, `system`, `vendor`, `oem`, `vbmeta`, **and also
  `dsp`, `modem`, `drm` and `bluetooth`**.
- Those four are byte-identical to the **old jasper debug build's** images. They
  were left over from the first flash.
- Everything else on slot A, and all of slot B, is stock. That includes the
  bootloader chain, `keymaster`, `cmnlib`, `devcfg` and `oem_bootloader`.
- **Open decision:** what should the tool do with `dsp`, `modem`, `drm` and
  `bluetooth`? The working configuration has jasper's versions, and `dsp` is
  the audio DSP firmware the mic tuning was done on.

**Mixer patch** (exact, against stock): in `mixer_paths_openq624_fep.xml`
- top-level defaults, lines 67–68: `DEC1 Volume` and `DEC2 Volume` 84 → 96
- inside mic paths, lines 996, 1001, 1006 and 1226: `ADC1/2/3 Volume` 6 → 12
- leave the top-level `ADC1/2/3 Volume` = 4 unchanged

This replaces the Task 9 wording "DEC … inside paths only".

**Kiosk Satellite**
- Signing certificate SHA-256
  `2a77134ce11f65ba9d08bed669fdcb742a25633c5665a6135aeca30040b068fc`.
- That's the same pin as echo-dot-assist's `KIOSK_CERT`, and its `apkcert.py`
  confirms it.

**Android Things menu**
- Opens with `monkey -p com.android.iotlauncher -c android.intent.category.HOME 1`.
- Networks has Wi-Fi.
- ☰ → **System → Date & time** has a time zone setting.
- The same page has **Check for update** and **Factory data reset**. The docs
  must warn never to press them on a converted display.

**Reboots**
- `adb reboot bootloader` reaches fastboot with no buttons on both displays,
  and `fastboot reboot` returns to Android. The tool may use them once the
  display is converted and adb works.
- From stock, the first entry into fastboot or EDL is still a physical prompt.
- Watch for one oddity in Task 15: one `fastboot reboot` on the Master Bedroom
  display came up to adb, then dropped back into fastboot by itself, roughly
  45 s later. The cause isn't known; it happened while `adb root` was sent
  during early boot. The next reboot was clean. The tool should wait for
  `sys.boot_completed=1` before sending `adb root`, and fall back to a physical
  prompt if adb doesn't come back within 2 minutes.

**The userdebug dump (`OIMK.211005.001-userdebug-blueberry-FRW.7z`), checked
2026-11-08**
- `.7z`: 738,309,431 bytes, SHA-256
  `ca243aa4fef755052d80a90915b9f64e729fc1e1a190f6baa913f3cff68f53ad`.
- It holds a single `FRW.bin` of 3,909,091,328 bytes.
- **`FRW.bin` uses the 10" partition layout.** 23 partitions sit at different
  offsets from the 8", including `devinfo`, `factory`, `keymaster`, `dsp` and
  `oem`. So Task 6 must read **FRW's own GPT** to find each image, flash it by
  name, and never write FRW's table.
- `boot_a` and `vbmeta_a` on both displays are byte-identical to FRW, which
  confirms the source.
- FRW's bootloader chain (`sbl1`, `aboot`, `tz`, `rpm`, `keymaster`, `cmnlib`,
  `devcfg`, `oem_bootloader`) is identical to both displays' stock, on both
  slots. There's nothing to flash there.
- `dsp`, `modem`, `drm` and `bluetooth` exist in three versions:
  - **jasper 2019**, on slot A of both displays: working, and the mic tuning was
    done on it
  - **FRW 2021, 10"**: untested on the 8"
  - **8" stock 2021**, on slot B, identical on both displays
- **Decided:** don't flash these four, so each display keeps its 8" stock
  versions. This matches `FLASH_SET` as written: five partitions only.
  - **Tested on the Kitchen display, 2026-11-08:** its slot B stock images were
    flashed to slot A. Boot was clean, the ADSP came up (`Q6 Is Up`), there
    were no audio service errors, Bluetooth was on, and both boot fixes ran.
    The user confirmed wake word, voice replies, music and volume "seem good".
  - The jasper and stock images from that display are kept in
    `amber/backup/kitchen-fw-test/` with `SHA256SUMS`.
  - The Master Bedroom display still runs the jasper versions.

**Identity, confirmed on both displays**
- `at-perm-attr-hash=802e273eca8ccaaa69b1623f96cd7e11`
- `wm size` 800x1280, density 300

**Both displays have the same jasper leftovers.** Slot A `dsp`, `modem`, `drm`
and `bluetooth` are identical on both. Slot B differs between the two units in
`boot`, `system`, `oem` and `vbmeta`, so they shipped with different stock
builds. **A backup may only be restored to the display it came from**, so
`restore` must match the serial too, not only the GPT.

## Review Focus

1. **The wrong or a second device is connected:** for example, a phone in
   fastboot, or both displays on USB. Expected: the tool lists the devices,
   refuses to guess, and asks the user to unplug the others. Tests in Tasks 3
   and 4.
2. **The display drops out of fastboot or EDL mid-step**, because the button was
   held too long or the cable was knocked. Expected: the tool says what happened,
   repeats the physical prompt, and retries the step without corrupting
   progress. Tests in Tasks 3 and 8.
3. **A rerun after a partial run:** already unlocked, already flashed, or Kiosk
   Satellite already installed. Expected: each step checks the device state
   first and skips what's done. Never re-unlock, re-flash or wipe again
   unasked. Tests in Tasks 2, 8 and 9.
4. **A download is interrupted, corrupted or short of disk space.** Expected:
   resume where possible; a hash mismatch deletes the file and stops with a
   clear message; refuse to start without 12 GB free in the cache folder.
   Tests in Task 5.
5. **Windows paths with spaces or non-ASCII characters** (`C:\Users\José Smith\…`)
   in the cache, backup or log folder. Expected: everything works, and paths are
   never split. Tests in Tasks 2 and 5.

---

### Task 1: Repo skeleton, licence, docs move, CI tests

**Files:**
- Create:
  - `pyproject.toml` (package `lhk`, entry point `lhk = lhk.cli:main`,
    `requires-python = ">=3.10"`; dependencies `pyusb`, `py7zr`, `requests`;
    dev dependency `pytest`)
  - `requirements.txt`
  - `LICENSE` (MIT, the user's name, 2026)
  - `lhk/__init__.py` (`__version__ = "0.1.0"`)
  - `.github/workflows/test.yml` (pytest on ubuntu, windows and macos, Python 3.10
    and 3.12)
  - `.gitignore` (`cache/`, `backup/`, `logs/`, `progress/`, `build/`, `dist/`)
  - `docs/design.md`, the spec, moved
  - `docs/findings/GUIDE.md` and `docs/findings/NOTES.md`, copied with private
    data replaced by placeholders: serials, LAN IPs, Wi-Fi name, dashboard URL
  - `tests/test_smoke.py`
- Repo: create `lenovo-display-ha-kiosk` on GitHub with the description and
  topics from Global Constraints. **Ask the user before creating it, because
  it's public.**

- [ ] **Step 1:** Write `tests/test_smoke.py::test_version`: `import lhk; assert lhk.__version__ == "0.1.0"`.
- [ ] **Step 2:** Run `pytest -q`. Expected: FAIL, no module `lhk`.
- [ ] **Step 3:** Create the files above.
- [ ] **Step 4:** Run `pytest -q`. Expected: PASS.
- [ ] **Step 5:** `grep -rnE "192\.168\.|HUA05|remote\.password\"" docs/` returns nothing.
- [ ] **Step 6:** Commit: `chore: repo skeleton, MIT licence, design and findings`.

### Task 2: Step runner with resumable progress and logging

**Files:**
- Create: `lhk/steps.py`, `lhk/log.py`, `tests/test_steps.py`

**Interfaces:**
- Produces:
  - `class Step: name: str; title: str; def done(self, ctx) -> bool; def run(self, ctx) -> None`
  - `class Context: runner: Runner; ui: UI; paths: Paths; dry_run: bool; state: dict`
  - `run_steps(steps: list[Step], ctx: Context, *, start_from: str | None = None, restart: bool = False) -> None`
  - Progress file: `progress/<serial>.json`, `{"done": [step names], "version": "0.1.0"}`
  - `Paths(root: pathlib.Path)` with `.cache`, `.backup`, `.logs`, `.progress`.
  - `log.setup(path) -> logging.Logger`
  - `log.redact(text: str) -> str`: masks values of keys matching
    `password|token|psk|secret`.

- [ ] **Step 1:** Write the tests:
  - `test_skips_steps_marked_done`
  - `test_skips_when_step_done_returns_true` (device state check, Review Focus 3)
  - `test_start_from_marks_earlier_steps_done`
  - `test_restart_clears_progress`
  - `test_failure_keeps_earlier_progress` (Review Focus 2)
  - `test_paths_with_spaces_and_unicode` (`tmp_path / "José Smith" / "x y"`, Review Focus 5)
  - `test_redact_masks_passwords` (`'{"password": "hunter2"}'` → `hunter2` absent)
- [ ] **Step 2:** Run `pytest tests/test_steps.py -q`. Expected: FAIL.
- [ ] **Step 3:** Implement. Progress is written atomically (temp file, then
  `os.replace`) after each step.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: resumable step runner and redacting log`.

### Task 3: Command runner, tool locator and mode detection

**Files:**
- Create: `lhk/runner.py`, `lhk/modes.py`, `tests/fakes.py`, `tests/test_modes.py`

**Interfaces:**
- Produces:
  - `class Runner: def run(self, args: list[str], *, check=True, timeout=60) -> Result` (`Result(code: int, out: str)`), with `RealRunner` and `tests.fakes.FakeRunner(responses: dict[tuple, Result])`, which records every call in `.calls`
  - `Tools(adb: Path, fastboot: Path)`, located in `cache/platform-tools/` (Task 5 downloads them)
  - `class Mode(Enum): NONE, EDL, FASTBOOT, ADB`
  - `detect(runner, usb_scan=...) -> list[tuple[Mode, str]]`: all devices, as (mode, serial or USB path)
  - `wait_for_mode(target: Mode, ctx, *, prompt: str, timeout: float) -> str`: shows the live readout, prints "Let go now" the moment `target` appears, and returns the serial. If several devices are found, it raises `MultipleDevices`. If the wrong mode appears, it re-prompts.

- [ ] **Step 1:** Write the tests, using `FakeRunner` and a fake USB scan:
  - `test_detects_fastboot_serial`
  - `test_detects_edl_by_usb_id`
  - `test_multiple_devices_raises` (Review Focus 1)
  - `test_wrong_mode_reprompts`
  - `test_dropout_then_return_succeeds` (device present, gone, back; Review Focus 2)
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. Poll every 0.25 s. EDL is found with `usb.core.find(idVendor=0x05c6, idProduct=0x9008)`, and a missing libusb backend raises `UsbBackendMissing`, which carries per-OS fix text.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: device mode detection with live readout`.

### Task 4: Device identity guard

**Files:**
- Create: `lhk/identity.py`, `tests/test_identity.py`

**Interfaces:**
- Consumes: `Runner`, `Tools`
- Produces:
  - `check_fastboot_identity(ctx, serial) -> Identity`: reads `getvar product`, `current-slot`, `at-vboot-state` and `max-download-size`.
  - `check_adb_identity(ctx, serial) -> Identity`: reads `ro.build.fingerprint`, `ro.product.device` and `ro.build.type`.
  - `SUPPORTED = {"amber": {...}}`. On a mismatch it raises `UnsupportedDevice`, unless `ctx.state["force_model"]`.

- [ ] **Step 1: Record the real values.** Run `fastboot getvar product` and
  `adb shell getprop ro.product.device` on a real SD-8501F, and write them into
  `SUPPORTED`. This needs a person: use the Master Bedroom display.
- [ ] **Step 2:** Write the tests:
  - `test_amber_accepted`
  - `test_other_product_refused`
  - `test_force_model_allows_with_warning`
  - `test_parses_avb_locked_flag` (sample `at-vboot-state` output from `docs/findings`)
- [ ] **Step 3:** Run the tests. Expected: FAIL.
- [ ] **Step 4:** Implement it, then run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: refuse unsupported devices`.

### Task 5: Download manifest, fetch and verify

**Files:**
- Create: `manifest.json`, `lhk/downloads.py`, `tests/test_downloads.py`

**Interfaces:**
- Produces:
  - `manifest.json` entries: `{id, url, sha256, size, unpack: "zip"|"7z"|null, platform: "windows"|"darwin"|"linux"|null}`
  - Entry IDs:
    - `platform-tools-{windows,darwin,linux}`
    - `oimk-userdebug-frw` (archive.org `OIMK.211005.001-userdebug-blueberry-FRW.7z`)
    - `avb-unlock` (`Lenovo-Android-Things-avb-unlock.zip`, sha256 `8e2ae30844961614cff7e4aeb1ed0d4d08d1f617aaf27d0835b79ed91d0c8be3`)
    - `firehose` (sha256 `e5abaec6fca5e0dc3a79c050fc06aa047f1b521ffb2e7ec8cb0f2140f09a06b1`)
    - `edl` (bkerler/edl, pinned commit tarball)
  - `fetch(entry_id, ctx) -> Path`: resumes with an HTTP Range request, verifies SHA-256, unpacks into `cache/<id>/`, and returns that folder. A mismatch deletes the file and raises `HashMismatch`.
  - `require_free_space(path, bytes=12 * 1024**3)`

- [ ] **Step 1: Pin the FRW hash.** Download the FRW `.7z` once, record its
  SHA-256 and size in `manifest.json`, and do the same for each OS's
  platform-tools zip. This needs a person and network; it's a one-time job.
- [ ] **Step 2:** Write the tests, using a local HTTP server fixture:
  - `test_verifies_and_caches`
  - `test_hash_mismatch_deletes_and_raises`
  - `test_resume_after_partial_download` (Review Focus 4)
  - `test_refuses_when_disk_low`
  - `test_cache_path_with_spaces` (Review Focus 5)
- [ ] **Step 3:** Run the tests. Expected: FAIL.
- [ ] **Step 4:** Implement, then run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: verified, resumable downloads`.

### Task 6: Firmware image extraction from the full-eMMC dump

**Files:**
- Create: `lhk/firmware.py`, `tests/test_firmware.py`, `tests/data/gpt_amber.bin`
  (the real Amber GPT, which is safe to publish: offsets only, no data)

**Interfaces:**
- Produces:
  - `read_gpt(path) -> list[Partition(name, first_lba, sectors)]`, with 512-byte sectors.
  - `extract(frw: Path, names: list[str], out: Path) -> dict[str, Path]`
  - `FLASH_SET = ["boot_a", "system_a", "vendor_a", "oem_a", "vbmeta_a"]`
  - `FORBIDDEN = {"partition", "devinfo", "persist", "sbl1", "aboot", "tz", "rpm"}`. Prefixes match across slots.

- [ ] **Step 1:** Write the tests:
  - `test_reads_56_partitions_from_amber_gpt`
  - `test_extract_rejects_forbidden_names`
  - `test_extract_sizes_match_gpt` (a synthetic small disk image)
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. GPT header at LBA 1, entries from LBA 2; stream copy in 4 MiB chunks.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: extract flash images from FRW dump`.

### Task 7: Backup and restore over EDL

**Files:**
- Create: `lhk/edl.py`, `lhk/backup.py`, `tests/test_backup.py`
- Create: `docs/drivers.md`: Windows Zadig steps for `05c6:9008` (WinUSB);
  Linux `qcserial` blacklist and udev rule (`51-lhk-edl.rules`, shipped in
  `assets/linux/`); macOS needs nothing.

**Interfaces:**
- Consumes: `fetch("edl")`, `fetch("firehose")`, `wait_for_mode(Mode.EDL, …)`
- Produces:
  - `backup(ctx, out: Path) -> None`: reads every partition except `userdata`, resumes, and writes `SHA256SUMS`. It is the same logic as `amber/backup-stock.sh`: device-specific partitions first, then the rest, skipping complete files.
  - `verify_backup(path) -> list[str]`: returns problems; empty means OK.
  - `restore(ctx, backup: Path) -> None`: refuses when `verify_backup` reports problems, or when the backup's GPT doesn't match the device's GPT; writes the partitions back with `edl wl`.
  - The skip warning: the exact copy from Global Constraints, which needs the typed `skip`.

- [ ] **Step 1:** Write the tests:
  - `test_backup_resumes_and_skips_complete_files`
  - `test_backup_reads_priority_partitions_first`
  - `test_verify_backup_detects_bad_hash`
  - `test_restore_refuses_on_gpt_mismatch`
  - `test_skip_requires_typed_confirmation`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. `edl` runs from `cache/edl` under the same interpreter (`sys.executable`). The EDL prompt is "hold volume up and volume down, plug in power".
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: EDL backup, verify and restore`.

### Task 8: AVB unlock and flashing

**Files:**
- Create: `lhk/unlock.py`, `lhk/flash.py`, `tests/test_flash.py`

**Interfaces:**
- Consumes: `fetch("avb-unlock")`, `extract(...)`, `wait_for_mode(Mode.FASTBOOT, …)`, `check_fastboot_identity`
- Produces:
  - `UnlockStep`: `done()` when `avb-locked=0`. Runs `cache/avb-unlock/at_auth_unlock.py creds/` with the bundled interpreter. `pycryptodome` becomes a dependency here.
  - `FlashStep`: flashes `FLASH_SET` to slot A, then `erase userdata`, then `set_active a`, then `reboot`. `done()` checks the adb fingerprint for `OIMK.211005.001/7795499:userdebug`.
  - `assert_safe(args: list[str])`: raises `ForbiddenCommand` for any fastboot argument list that touches `FORBIDDEN`, or contains `lock`, `at-lock-vboot` or `format`.

- [ ] **Step 1:** Write the tests:
  - `test_unlock_skipped_when_already_unlocked` (Review Focus 3)
  - `test_flash_commands_exact` (asserts `FakeRunner.calls` equal the expected list)
  - `test_assert_safe_blocks_lock_and_partition_table`
  - `test_flash_retries_after_dropout` (Review Focus 2)
  - `test_flash_skipped_when_userdebug_already_booted` (Review Focus 3)
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. Every fastboot call goes through `assert_safe`. The fastboot prompt is "hold volume down, plug in power".
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: AVB unlock and slot-A flash with safety guard`.

### Task 9: Post-flash system setup

**Files:**
- Create: `lhk/system.py`, `assets/degoogle.txt`, `assets/mixer.py`, `tests/test_system.py`

**Interfaces:**
- Consumes: `check_adb_identity`, `Runner`
- Produces:
  - `RootStep`: `adb root`, `disable-verity`, reboot, `remount`. `done()` when `adb shell id -u` is `0` and `/system` is writable.
  - `OpenThingsSettingsStep`: launches `com.android.iotlauncher`. The user sets Wi-Fi and time zone on screen; the tool waits until `wlan0` has an IPv4 address.
  - `DegoogleStep`: `pm disable-user` for each line of `assets/degoogle.txt`, the 4 packages from `GUIDE.md`. `done()` from `pm list packages -d`. It refuses to disable `sparrow.oem` or `androidthingshost`.
  - `MixerStep`: `patch_mixer(xml: str) -> str` sets `ADC1/2/3 Volume` to 12 and `DEC1/2 Volume` to 96 **inside paths only**, leaving the top-level defaults alone. It pushes the result and checks it.

- [ ] **Step 1:** Write the tests:
  - `test_patch_mixer_changes_only_path_values` (fixture: the real `mixer_paths_openq624_fep.xml` excerpt, with lines 64–68 unchanged)
  - `test_degoogle_never_touches_sensor_host`
  - `test_degoogle_idempotent` (Review Focus 3)
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. Use `xml.etree` to edit, and keep the original bytes for every untouched line.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: root, de-Google, mic gain, on-screen Wi-Fi and time zone`.

### Task 10: Kiosk Satellite install, grants, device owner and settings

**Files:**
- Create: `lhk/kiosk.py`, `lhk/apkcert.py`, `tests/test_kiosk.py`
- `apkcert.py` is adapted from echo-dot-assist `scripts/lib/apkcert.py` (MIT),
  with attribution in its header.

**Interfaces:**
- Produces:
  - `latest_release(ctx) -> (url, sha256)`: from the GitHub API, asset name `*armeabi-v7a*.apk`, checked against the release's published sha256.
  - `signing_cert_sha256(apk: Path) -> str`, checked against `KS_CERT_SHA256`, pinned from the APK installed on our displays.
  - `InstallStep`, then `GrantsStep`. The grants are the 7 commands in `GUIDE.md` section 6, plus `dpm set-device-owner me.jxl.kiosk_satellite/.KioskAdminReceiver`.
  - `SettingsStep`: runs after the user finishes Kiosk Satellite's on-screen wizard (the tool waits until it can log in).
    - Logs in via `adb forward` to `:2324`, with the password read from `shared_prefs/FlutterSharedPreferences.xml` over root and kept in memory only.
    - PATCHes `screen.hide_navigation_bar=false`, `audio.mic_gain_db=24` and `audio.mic_capture_mode=voice_communication`.
    - `done()` re-reads the settings.

- [ ] **Step 1:** Write the tests:
  - `test_cert_pin_mismatch_refuses` (a fixture APK signed with a test key)
  - `test_grants_commands_exact`
  - `test_device_owner_skipped_if_already_set` (Review Focus 3)
  - `test_settings_password_never_logged` (captures the log; the password is absent)
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. **Never edit the prefs file directly.** It loses its
  SELinux categories and triggers the setup wizard; see `docs/findings`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat: verified Kiosk Satellite install, grants, device owner, settings`.

### Task 11: Boot fixes (light sensor and volume buttons), built in CI

**Files:**
- Create, copied from `amber/bootfix/`:
  - `assets/bootfix/ks-boot-fix.rc`
  - `assets/bootfix/ks-boot-fix.sh`
  - `assets/bootfix/ks-volume-keys.sh`
  - `assets/bootfix/volkeys/VolKeys.java`
- Create: `lhk/bootfix.py`, `tests/test_bootfix.py`
- Create: `.github/workflows/jar.yml`. It builds `ks-volkeys.jar` with the
  `javac --release 8` / `d8 --min-api 26` commands from `GUIDE.md` and uploads
  it as an artifact; Task 13 attaches it to the release.

**Interfaces:**
- Produces: `BootFixStep`
  - Pushes the 4 files.
  - `chmod` 755 on the scripts and 644 on the rest.
  - `chcon u:object_r:dumpstate_exec:s0` on both `.sh` files; `restorecon` on the jar and rc.
  - Reboots, then checks:
    - `init.svc.ks_volume_keys=running`
    - `ks.VolKeys` running as `u:r:dumpstate:s0`
    - `dumpsys sensorservice` shows a `kiosk_satellite.LightSensor` registration after boot
    - no `nav_input_consumer`
  - Finally asks the user to press each volume button, and checks that `volume_music_speaker` changes by about 5.
  - In source mode the jar comes from the release; in development, from `build/`.

- [ ] **Step 1:** Write the tests:
  - `test_bootfix_push_and_labels_exact`
  - `test_bootfix_never_touches_init_rc`
  - `test_verify_reports_missing_light_sensor`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement it, plus the jar workflow.
- [ ] **Step 4:** Run the tests. Expected: PASS. `jar.yml` runs green on a push.
- [ ] **Step 5:** Commit: `feat: boot fixes for light sensor and volume buttons`.

### Task 12: Time zone data update (spike first)

**Files:**
- Create: `spikes/tzdata/README.md`, the result write-up
- On success, create: `lhk/tzdata.py`, `tests/test_tzdata.py`
- Either way, create: `docs/TIMEZONES.md`

- [ ] **Step 1: Spike on a real display.**
  - Build an Android 8.1 time zone distro from current IANA data.
  - Install it to `/data/misc/zoneinfo/current/`.
  - Reboot, set a zone whose rules changed recently, and compare `date`,
    Kiosk Satellite's clock and a dashboard clock.
  - Write the results in `spikes/tzdata/README.md`.
- [ ] **Step 2 (if the spike works):** Write `test_distro_layout`:
  `tzdata`, `tzlookup.xml` and `icu/icu_tzdata.dat` are present, and the version
  file matches. Add `TzdataStep` before `OpenThingsSettingsStep`.
- [ ] **Step 3:** Write `docs/TIMEZONES.md`, region-neutral. It covers:
  - why old builds show the wrong time after DST changes
  - what the update fixes
  - that the WebView keeps its own internal copy
  - the fallback: pick a zone with a fixed offset that matches yours
- [ ] **Step 4:** Commit: `feat|docs: time zone data update` (whichever applies).

### Task 13: CLI, standalone builds and release

**Files:**
- Create: `lhk/cli.py`, `lhk/ui.py`, `lhk/plan.py`, `tests/test_cli.py`,
  `.github/workflows/release.yml`, `lhk.spec` (PyInstaller)

**Interfaces:**
- Produces:
  - `lhk setup [--dry-run] [--from STEP] [--restart] [--skip-backup] [--force-model]`
  - `lhk restore BACKUP_DIR`
  - `lhk status`
  - `plan.SETUP_STEPS`, in design order: prerequisites → downloads → backup →
    unlock → flash → root → time zone → Things settings → degoogle → mixer →
    kiosk install → grants → bootfix → wizard wait → kiosk settings → final
    verify.
  - `ui.UI`: `say`, `ask`, `confirm_typed(word)`, `physical(prompt)`. It reads
    from the terminal and works when stdin is redirected.

- [ ] **Step 1:** Write the tests:
  - `test_dry_run_prints_commands_runs_none`
  - `test_step_order_matches_design`
  - `test_restore_command_requires_backup_dir`
- [ ] **Step 2:** Run the tests. Expected: FAIL.
- [ ] **Step 3:** Implement. In `release.yml`, on a tag:
  - build the jar
  - run PyInstaller on windows-latest, macos-latest and ubuntu-latest (one-folder builds)
  - **exclude `edl`**
  - attach the zips, the jar and `SHA256SUMS` to the GitHub release
- [ ] **Step 4:** Run the tests. Expected: PASS. Tag `v0.1.0-rc1` on a branch to
  dry-run the release workflow.
- [ ] **Step 5:** Commit: `feat: CLI, standalone builds, release workflow`.

### Task 14: User and agent documentation

**Files:**
- Create:
  - `README.md`
  - `devices/amber/README.md`
  - `docs/WINDOWS.md`, `docs/MACOS.md`, `docs/LINUX.md`
  - `docs/PYTHON.md`
  - `AGENTS.md` (plus `CLAUDE.md` pointing to it)
  - `devices/README.md`

**What each file covers:**
- **`README.md`**, in echo-dot-assist's conventions:
  - a first line with "degoogled"
  - the vibecoded caution, and a credits box: deadman96385, RYuhMine, jxlarrea,
    dimatx, bkerler, echo-dot-assist
  - the supported table: ✅ SD-8501F; 🧪 SD-X701B and CD-17302F
  - what you get, the two ways to run, and the restore command
- **`devices/amber/README.md`**: the manual path, every step the tool takes,
  with the command and the check that proves it.
- **`docs/WINDOWS.md`**, **`docs/MACOS.md`** and **`docs/LINUX.md`**: beginner
  pages, copy-paste only, linking `docs/drivers.md`.
- **`docs/PYTHON.md`**: the Python method, with install steps for each OS:
  - Windows: python.org with "Add to PATH", or `winget`
  - macOS: python.org or Homebrew; Command Line Tools' 3.9 is too old
  - Linux: the distro's `python3` and `python3-venv`
- **`AGENTS.md`**, plus `CLAUDE.md` pointing to it, for agents:
  - follow `devices/amber/README.md`
  - verify each step's check before moving on
  - the forbidden list from Global Constraints
- **`devices/README.md`**: the 10" and 7" differences known so far, with an
  invitation for reports.

- [ ] **Step 1:** Write `tests/test_docs.py::test_manual_lists_every_setup_step`:
  each `SETUP_STEPS` name appears as a heading in `devices/amber/README.md`.
- [ ] **Step 2:** Write the docs.
- [ ] **Step 3:** Run `pytest -q`. Expected: PASS.
- [ ] **Step 4:** Repeat the Task 1 private-data grep on the docs. Expected: nothing.
- [ ] **Step 5:** Commit: `docs: README, manual steps, per-OS guides, agent guide`.

### Task 15: End-to-end validation on hardware

Needs a person and a display, and no code changes unless bugs turn up.

- [ ] **Step 1:** Restore one display to stock with `lhk restore`, from its
  backup. This also tests restore.
- [ ] **Step 2:** On Linux, run `lhk setup` from stock to a working kiosk.
  Record any prompt that confused the user, and fix the wording.
- [ ] **Step 3:** Repeat on Windows with the standalone program, following
  `docs/WINDOWS.md` exactly.
- [ ] **Step 4:** Repeat on macOS if available. If not, mark macOS 🧪 in the
  README.
- [ ] **Step 5:** Commit the fixes, then tag `v0.1.0` and publish the release.
