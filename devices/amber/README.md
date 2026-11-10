# Lenovo Smart Display 8 (SD-8501F, "amber"): manual steps

These are the same steps `lhk setup` runs, in the same order. Each step says what to do and **how to check it
worked**: don't go on until the check passes. The guided tool does all of this for you; use this page if you'd
rather do it by hand, or if you're an AI agent following along.

> [!CAUTION]
> This unlocks verified boot and replaces the operating system. Without a backup, you may not be able to go
> back to stock. Read each step before running it.

**Conventions:**
- Commands run on your computer, in a terminal.
- `adb` and `fastboot` are Google's [platform-tools](https://developer.android.com/tools/releases/platform-tools).
- The screen stays **blank** in fastboot and EDL modes. Use `fastboot devices` or the USB device list
  (`05c6:9008` is EDL, `18d1:d00d` is fastboot) to see the mode.
- **To enter a mode:** unplug the power, hold the button(s), plug the power in, and let go after 3 to 5
  seconds. Held for about 15 seconds, they reset the display. If you see the Lenovo logo, it's starting
  normally: unplug and try again.

## 1. `prerequisites`: free space and tools

- **What you need:** a USB-A or USB-C **data** cable, and at least **12 GB free**.
- **USB-C port:** it's under the rubber cover at the bottom right of the display's back.
- **Tools:** download Google's platform-tools for your OS and unzip them.
- **Drivers:** set up USB access for your OS: [docs/drivers.md](../../docs/drivers.md).

**Check:** `adb version` and `fastboot --version` both print a version.

## 2. `downloads`: firmware and tools

Download these and check each one's SHA-256 against [`manifest.json`](../../manifest.json):

| File | Used for |
|---|---|
| `OIMK.211005.001-userdebug-blueberry-FRW.7z` | The userdebug build (a full-disk dump) |
| `Lenovo-Android-Things-avb-unlock.zip` | The AVB unlock tool and credentials |
| `amber_bluebbery_prog_emmc_firehose_8953_ddr.zip` | EDL loader, for backup and restore |
| bkerler/edl at the pinned commit | Backup and restore |

**Check:** every hash matches. On Linux or macOS: `sha256sum FILE`. On Windows: `certutil -hashfile FILE SHA256`.

## 3. `backup`: back up the stock display

Strongly recommended. **If anything goes wrong, you may not be able to restore this display unless you can find
its firmware elsewhere.**

1. Unplug the display's power. Connect USB.
2. Hold **volume up and volume down together**, plug in the power, and let go after 3 to 5 seconds.
3. Run, from the edl folder:

   ```bash
   python edl.py gpt backup/partitions --memory=eMMC --loader=amber_bluebbery_prog_emmc_firehose_8953_ddr.mbn
   python edl.py rl backup/partitions --skip=userdata --memory=eMMC --loader=amber_bluebbery_prog_emmc_firehose_8953_ddr.mbn
   ```

4. Write `SHA256SUMS` for the files in `backup/partitions`.

**Check:** 55 `.bin` files plus `gpt_main0.bin`, about 2.5 GB in total.

`lhk` also packs the backup into one zip next to the folder (about 850 MB). `lhk restore` takes either.

**Keep the backup private.** It holds data unique to your display: `persist`, `modemst`, `devinfo` and
`keymaster`. It only restores to the same display.

## 4. `unlock`: unlock verified boot (AVB)

1. Unplug the power. Hold **volume down**, plug in the power, and let go after 3 to 5 seconds.
2. Check the starting state: `fastboot getvar at-vboot-state`. The 8" shows
   `at-perm-attr-hash=802e273eca8ccaaa69b1623f96cd7e11`.
3. Run `python at_auth_unlock.py creds/` from the unzipped AVB unlock folder, with `fastboot` on your PATH.

`fastboot flashing unlock` is refused on this build. That's expected; this step replaces it.

**Check:** `fastboot getvar at-vboot-state` shows `avb-locked=0`. `bootloader-locked` stays `1`, which is fine.

**Never run `fastboot oem at-lock-vboot`** after flashing the userdebug build. It can hard-brick the display.

## 5. `flash`: flash the userdebug build to slot A

0. **Check both slots match first.** Some displays run from slot B after an update. This step flashes slot A
   and makes it active, but never writes the per-slot firmware. So compare the two slots in your backup:
   `sbl1`, `aboot`, `tz`, `rpm`, `keymaster`, `cmnlib`, `devcfg`, `oem_bootloader`, `dsp`, `modem`, `drm`
   and `bluetooth`. Compare `NAME_a.bin` with `NAME_b.bin`, for example with `sha256sum`.
   - If every pair is identical, as on the tested displays, go on.
   - **If any differ, stop:** slot A may hold older firmware, and the new system might not start. Please report
     it.
   - Without a backup, this can't be checked.
1. Extract `FRW.bin` from the `.7z`. It's a whole-disk image laid out like the **10"**.
2. Read **its own** partition table, and copy out `boot_a`, `system_a`, `vendor_a`, `oem_a` and `vbmeta_a`.
   `lhk` does this; by hand, use the GPT's first LBA and sector count with `dd`, at 512-byte sectors.
3. Flash to slot A only:

   ```bash
   fastboot flash boot_a boot_a.img
   fastboot flash system_a system_a.img
   fastboot flash vendor_a vendor_a.img
   fastboot flash oem_a oem_a.img
   fastboot flash vbmeta_a vbmeta_a.img
   fastboot erase userdata
   fastboot set_active a
   fastboot reboot
   ```

**Never** flash the partition table, the bootloader chain (`sbl1`, `aboot`, `tz`, `rpm`), `devinfo`, `persist`,
`dsp`, `modem`, `drm` or `bluetooth`, and never `format userdata`. The display's own stock `dsp`, `modem`,
`drm` and `bluetooth` are the right ones for the 8". Slot B stays stock.

**Check:** after the first boot (a few minutes), `adb shell getprop ro.build.fingerprint` ends with
`OIMK.211005.001/7795499:userdebug/dev-keys`, and `adb shell wm size` shows `800x1280`.

## 6. `root`: root and a writable /system

Wait for `adb shell getprop sys.boot_completed` to print `1` before each command.

```bash
adb root
adb disable-verity
adb reboot
adb root
adb remount
```

**Check:** `adb shell id -u` prints `0`, and `adb shell 'touch /system/.x && rm /system/.x'` succeeds.

## 7. `tzdata`: current time zone data

```bash
adb push assets/tzdata/tzdata /system/usr/share/zoneinfo/tzdata
adb shell chmod 644 /system/usr/share/zoneinfo/tzdata
adb shell restorecon /system/usr/share/zoneinfo/tzdata
```

**Check:** `adb shell head -c 11 /system/usr/share/zoneinfo/tzdata` prints the new version, for example
`tzdata2026f`. See [docs/TIMEZONES.md](../../docs/TIMEZONES.md).

## 8. `things-settings`: Wi-Fi and time zone, on the display

After flashing, the screen shows a Google spinner. Open the Android Things settings:

```bash
adb shell monkey -p com.android.iotlauncher -c android.intent.category.HOME 1
```

On the display:
- **Networks:** pick your Wi-Fi, and type the password on the on-screen keyboard.
- **☰ > System > Date & time:** pick your **real** time zone.
- **Don't press Check for update or Factory data reset.**

**Check:** `adb shell ip -4 addr show wlan0` shows an `inet` address.

## 9. `degoogle`: turn off Assistant, Cast and check-ins

```bash
adb shell pm disable com.google.assistant.gallium.dragonglass.platform.androidthings.system
adb shell pm disable com.google.android.apps.mediashell
adb shell pm disable com.google.android.things.checkin
adb shell pm disable com.google.android.things.customcheckin
```

**Never disable** `com.google.android.things.sparrow.oem`: it drives the light sensor and volume buttons.
Also leave `com.google.assistant.gallium.client.androidthingshost` alone, and every other `com.google.*`
package: they're part of Android Things itself.

**Check:** `adb shell pm list packages -d` lists those four.

## 10. `mixer`: microphone gain

In `/system/etc/mixer_paths_openq624_fep.xml`, change exactly six lines:
- the **top-level** `DEC1 Volume` and `DEC2 Volume`, from `84` to `96`
- every `ADC1/2/3 Volume` **inside `<path>` blocks**, from `6` to `12` (four lines)

Leave the top-level `ADC… value="4"` lines as they are. Pull the file with `adb pull`, edit it, `adb push` it
back, and `adb shell chmod 644` it.

**Check:** `adb shell grep -c 'value="12"' /system/etc/mixer_paths_openq624_fep.xml` prints `4` or more, and the
two DEC lines show `96`.

## 11. `kiosk-install`: install Kiosk Satellite

Download the newest `*armeabi-v7a.apk` from [Kiosk Satellite's releases](https://github.com/jxlarrea/kiosk-satellite/releases).
Check its SHA-256 against the release page, and its signing certificate:
`2a77134ce11f65ba9d08bed669fdcb742a25633c5665a6135aeca30040b068fc`. Then:

```bash
adb install -r -g kiosk-satellite-VERSION.armeabi-v7a.apk
```

**Check:** `adb shell pm path me.jxl.kiosk_satellite` prints a `package:` line.

## 12. `kiosk-grants`: permissions and device owner

```bash
adb shell appops set me.jxl.kiosk_satellite REQUEST_INSTALL_PACKAGES allow
adb shell appops set me.jxl.kiosk_satellite WRITE_SETTINGS allow
adb shell appops set me.jxl.kiosk_satellite SYSTEM_ALERT_WINDOW allow
adb shell appops set me.jxl.kiosk_satellite GET_USAGE_STATS allow
adb shell dumpsys deviceidle whitelist +me.jxl.kiosk_satellite
adb shell cmd notification allow_listener me.jxl.kiosk_satellite/.MediaSessionListener
adb shell dpm set-active-admin me.jxl.kiosk_satellite/.KioskAdminReceiver
adb shell dpm set-device-owner me.jxl.kiosk_satellite/.KioskAdminReceiver
```

Device owner lets Kiosk Satellite update itself without a tap. Only a factory reset, which means a reflash here,
removes it.

**Check:** `adb shell dumpsys device_policy` shows Kiosk Satellite under `Device Owner`.

## 13. `kiosk-settings`: connect to Home Assistant, then apply the settings

1. On the display, go through all five pages of Kiosk Satellite's setup wizard and press **Finish**: a name and
   admin password, your Home Assistant address and sign-in, the dashboard, voice and ESPHome options, then
   permissions. It saves the sign-in on page 2, so don't restart the display until you've pressed Finish.
   You can also do the wizard in a browser at `http://DISPLAY-IP:2324`, which makes pasting the Home Assistant
   address and token easy. On the display, you can scan a QR code of the token with its camera instead.
2. Then set these, in the app's settings or its remote admin (port 2324, `PATCH /api/settings`):

| Setting | Value | Why |
|---|---|---|
| `screen.hide_navigation_bar` | `false` | The display has no navigation bar. Up to 2026.11.13, hiding it on Android 8 made taps get lost ([kiosk-satellite#1358](https://github.com/jxlarrea/kiosk-satellite/issues/1358), fixed in the next release) |
| `audio.mic_gain_db` | `24` | Wake word from across the room |
| `audio.mic_capture_mode` | `voice_communication` | Uses the multi-mic noise path |
| `home.enabled` | `true` | "Act as the home screen". Off by default, and the wizard doesn't set it. Without it, Android's home is Google Assistant's screen, which can't load on these displays (Cast is off), so every restart sticks on four spinning dots |

**Never edit the app's settings file directly.** Rewriting it drops its security label, and the app falls back
to the setup wizard.

**Check:** with the app open, `adb shell dumpsys input | grep -c nav_input_consumer` prints `0`.

## 14. `bootfix`: light sensor and volume buttons

- **Volume buttons:** these are GPIOs that only a Google component used to read. The fix is a small helper that
  turns presses into volume keys.
- **Light sensor:** it appears after Kiosk Satellite has already started, so the fix restarts Kiosk Satellite
  once the sensor shows up.

Build `ks-volkeys.jar` (see [docs/PYTHON.md](../../docs/PYTHON.md)) or take it from a release. Then:

```bash
adb push assets/bootfix/ks-boot-fix.sh /system/bin/ks-boot-fix.sh
adb push assets/bootfix/ks-volume-keys.sh /system/bin/ks-volume-keys.sh
adb push ks-volkeys.jar /system/framework/ks-volkeys.jar
adb push assets/bootfix/ks-boot-fix.rc /system/etc/init/ks-boot-fix.rc
adb shell chmod 755 /system/bin/ks-boot-fix.sh /system/bin/ks-volume-keys.sh
adb shell chmod 644 /system/framework/ks-volkeys.jar /system/etc/init/ks-boot-fix.rc
adb shell chcon u:object_r:dumpstate_exec:s0 /system/bin/ks-boot-fix.sh /system/bin/ks-volume-keys.sh
adb shell restorecon /system/framework/ks-volkeys.jar /system/etc/init/ks-boot-fix.rc
adb reboot
```

**Never edit `/init.rc`**; this uses its own file in `/system/etc/init`.

**Check, after the reboot:**
- `adb shell getprop init.svc.ks_volume_keys` prints `running`
- `adb shell dumpsys sensorservice | grep kiosk_satellite.LightSensor` finds a line
- pressing volume up changes the volume

## 15. `verify`: final check

- Everything from steps 5 and 14 still holds.
- Kiosk Satellite shows your dashboard.
- Touch works.
- The wake word answers from across the room.

## Restore to stock

```bash
lhk restore backup/display
```

`lhk restore backup/display.zip` works too. The tool:

1. writes every partition over EDL, then erases `userdata`;
2. asks for fastboot mode, and locks verified boot again after you type `lock`.

Unlocked, stock never gets past Google Assistant's four loading dots, so step 2 matters. The tool locks only a
backup that proves it is stock: both `vbmeta` slots signed with no verification flags, and neither `boot` slot
holding the userdebug boot.

If you pressed Enter at the `lock` prompt, the display stays unlocked. `lhk lock` locks it later without writing
everything again: it reads the display's own `boot` and `vbmeta` over EDL, and locks only if they're stock.

Times on an 8": setup takes 20 to 30 minutes, including the downloads. A restore takes about 10 minutes.

By hand: enter EDL as in step 3, and write each `.bin` back with `edl.py w NAME FILE`. Skip `userdata` and never
write the partition table. Only do this with the backup from **this** display. Then erase `userdata`
(`edl.py e userdata`), enter fastboot as in step 4 and run `fastboot oem at-lock-vboot`. **Only lock after
writing a stock backup**, never with the userdebug build on the display.
