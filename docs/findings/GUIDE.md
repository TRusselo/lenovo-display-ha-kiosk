# Lenovo Smart Display 8 (SD-8501F) → Home Assistant voice satellite

A clean write-up of the method that works, written from `NOTES.md` (the full
working log, kept as-is). Status as of 2026-11-08: two displays converted.
Both have the fixes below:
- Kiosk Satellite permission grants and device owner
- `screen.hide_navigation_bar=false`
- the `bootfix/` services: the light sensor restart and the volume buttons

Verified after a reboot on both displays: Master Bedroom (`<serial-1>`) and
Kitchen (`<serial-2>`).

**Evidence labels:** **Observed** = seen on my own devices. **Reported** = from
someone else, not reproduced. **To verify** = I believe it but haven't
confirmed it on the current build. Items marked **To verify** are collected
in [Verify before publishing](#verify-before-publishing).

> **Warning:** this unlocks verified boot and replaces the OS. Without a backup
> you can't get back to stock, and a mistake can brick the display. Make the
> EDL backup first.

## What you end up with

- Android Things 8.1 `userdebug` build of the **same version as stock**
  (`OIMK.211005.001`), so root works **and** the stock kernel's drivers stay.
- Google Assistant, Cast and check-in disabled.
- [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite) as launcher,
  dashboard, voice satellite with on-device wake word, and Music Assistant
  player.
- Working: light and proximity sensors, mic (wake word from 10+ feet), speaker,
  Music Assistant playback. Stock WebView 87 renders Home Assistant dashboards.

## Hardware and modes

| | |
|---|---|
| Model | Lenovo Smart Display 8, `SD-8501F`, codename Amber |
| SoC | Snapdragon 624 (msm8953), 2 GB RAM, 32-bit userspace (`armeabi-v7a`) |
| Stock build | Android Things 8.1, `OIMK.211005.001` |
| Data port | USB-C under the adhesive silicone cover, bottom right |

The screen stays **blank** in both EDL and fastboot. Watch the mode from the PC:

```bash
bash -c 'while :; do m=none; u=$(lsusb); [[ $u == *05c6:9008* ]] && m=EDL; [[ $u == *18d1:d00d* ]] && m=FASTBOOT; printf "\r%s %-10s" "$(date +%T)" "$m"; sleep 0.5; done'
```

| Mode | How (observed) | USB ID |
|---|---|---|
| Fastboot | Hold **volume down**, plug in power, **let go as soon as it shows FASTBOOT** | `18d1:d00d` |
| EDL (Sahara) | Hold **volume up + volume down**, plug in power, let go once detected | `05c6:9008` |

**Holding a button resets the display after about 15 seconds**, in either
mode. Release it as soon as the mode appears and it stays connected.

## 1. Back up stock over EDL (do this first)

- Tool: [bkerler/edl](https://github.com/bkerler/edl). Firehose:
  `amber_bluebbery_prog_emmc_firehose_8953_ddr.mbn` (from the XDA thread below).
- Linux needs `qcserial` blocked, or edl fails with `Resource busy`: put
  `blacklist qcserial` in `/etc/modprobe.d/`, then `sudo rmmod qcserial`. A udev
  rule for `05c6:9008` lets it run without root. Remove both afterwards.
- `backup-stock.sh` reads every partition except `userdata` (about 2.5 GB) and
  writes `SHA256SUMS`. It's safe to re-run; it resumes.
- **Never publish the backup.** It has unit-specific data (`persist`,
  `modemst`, `devinfo`, `keymaster`).

Observed: the real partition table matches the Amber stock zip. The old
jasper-blueberry debug zip's `partition-table.img` does **not** match (23
partitions would move), so never flash that table.

## 2. Unlock verified boot

- `fastboot flashing unlock` **fails** on this build (`oem unlock is not
  allowed`, `get_unlock_ability` = 0). That's expected; skip it.
- The real path is the authenticated AVB unlock from deadman96385's
  [XDA thread](https://xdaforums.com/t/lenovo-smart-display-8-10-amber-blueberry-avb-bootloader-unlock-firmware.4472049/):
  `python3 at_auth_unlock.py creds/`. No Wine needed; system Python with
  PyCryptodome works. Result: `avb-locked=0`. `bootloader-locked` stays `1`,
  and that doesn't block flashing.
- **Never run `fastboot oem at-lock-vboot` after flashing non-stock images.**
  It reportedly hard-bricks the device.

## 3. Flash the userdebug build

- Firmware: `OIMK.211005.001-userdebug-blueberry-FRW.7z` from the
  [android-things-oreo-builds archive](https://archive.org/details/android-things-oreo-builds)
  (reported). It's a single 3.9 GB full-eMMC dump, `FRW.bin`.
- Extract `boot_a`, `system_a`, `vendor_a`, `oem_a` and `vbmeta_a` from its GPT
  with `dd`. Convert the big ones to sparse images with `img2simg`, then
  `fastboot flash` each one to **slot A only**. Leave the partition table and the
  bootloader chain (`sbl1`, `aboot`, `tz`, `rpm`) alone, and keep slot B stock.
- Use `fastboot erase userdata`, not `format` (`format` fails with
  `mke2fs: invalid option -- 'b'`).
- Check: fingerprint ends `OIMK.211005.001/7795499:userdebug/dev-keys`, and
  `adb root` gives uid 0.

**Why not the jasper-blueberry debug build:** `OIM6.190107.017` has root, but no
light sensor, a 2018 WebView 66, and a too-quiet mic. That path is in
`NOTES.md` as history only.

## 4. Base setup over adb

- **Wi-Fi:** **To verify** which method works on this build. `wpa_cli` failed on
  the old build because the framework dropped the network. A small `app_process`
  helper calling `WifiManager.addNetwork/enableNetwork/saveConfiguration`
  worked there. `join-wifi.sh` still uses `wpa_cli`.
- **Clock:** `setprop persist.sys.timezone America/Regina`. Regina is always
  UTC-6, which matches Alberta's permanent time. Observed on the current build.
- **De-Google:** `pm disable` these four. Observed disabled, and survives reboot:
  - `com.google.assistant.gallium.dragonglass.platform.androidthings.system`
  - `com.google.android.apps.mediashell`
  - `com.google.android.things.checkin`
  - `com.google.android.things.customcheckin`
- **Keep these enabled:**
  - **`com.google.android.things.sparrow.oem`** is the OEM user-space driver. It
    registers the VCNL 4200 light and proximity sensors, and reads the volume
    buttons.
  - `com.google.assistant.gallium.client.androidthingshost`, which the notes say
    makes the light sensor disappear when disabled.
  - The framework packages: `things.internal.*`, `wifisetup`, `gsf`, `tts` and
    others.

## 5. Audio

- Mic gain at the analog stage: in `/system/etc/mixer_paths_openq624_fep.xml`,
  set `ADC1/2/3 Volume` to 12 (from 6) and `DEC1/2 Volume` to 96 (from 84).
  Then `adb remount`, push the file, and reboot.
- Kiosk Satellite: `audio.mic_gain_db=24` and
  `audio.mic_capture_mode=voice_communication`. Wake word went from about 12
  inches to 10+ feet.

## 6. Kiosk Satellite

- Use build `armeabi-v7a`. Remote admin is on port `2324`.
- **Permission grants**, observed applied on the Master Bedroom display on
  2026-11-08, all from the
  [Kiosk Satellite permissions docs](https://kiosksatellite.com/docs/permissions):

  ```bash
  adb shell appops set me.jxl.kiosk_satellite REQUEST_INSTALL_PACKAGES allow
  adb shell appops set me.jxl.kiosk_satellite WRITE_SETTINGS allow
  adb shell appops set me.jxl.kiosk_satellite SYSTEM_ALERT_WINDOW allow
  adb shell appops set me.jxl.kiosk_satellite GET_USAGE_STATS allow
  adb shell dumpsys deviceidle whitelist +me.jxl.kiosk_satellite
  adb shell cmd notification allow_listener me.jxl.kiosk_satellite/.MediaSessionListener
  adb shell dpm set-active-admin me.jxl.kiosk_satellite/.KioskAdminReceiver
  ```

  `REQUEST_INSTALL_PACKAGES` is an app op, so use `appops`, not `pm grant`.
- Then make it **device owner** for silent updates:
  `adb shell dpm set-device-owner me.jxl.kiosk_satellite/.KioskAdminReceiver`.
  It needs no accounts and one user; only a factory reset undoes it.
- **Permission audit (2026-11-08):** Kiosk Satellite requests 42 permissions,
  and 20 show as not granted. None of those is missing in practice:
  - **App ops**, all set to `allow`: `REQUEST_INSTALL_PACKAGES`,
    `SYSTEM_ALERT_WINDOW`, `WRITE_SETTINGS` and `PACKAGE_USAGE_STATS`.
  - **Don't exist on Android 8.1 (API 27)**, so they can't be granted:
    `BLUETOOTH_CONNECT/SCAN`, `FOREGROUND_SERVICE` and all
    `FOREGROUND_SERVICE_*`, `POST_NOTIFICATIONS`, `READ_MEDIA_IMAGES/VIDEO`,
    `SCHEDULE_EXACT_ALARM`, `USE_EXACT_ALARM`,
    `UPDATE_PACKAGES_WITHOUT_USER_ACTION` and `MANAGE_EXTERNAL_STORAGE`.
  - **Left off on purpose:**
    - `READ_LOGS`: the docs list it for Meta Portal only, and it lets the app
      read every log.
    - The accessibility "System UI guard": Android Things has no system UI to
      guard.
    - Shizuku: not needed with device owner.
- **Self-update:** `/data` is only 1 GB. Delete leftover `vmdl*.tmp` files in
  `/data/app`, and any old WebView APKs.
- **Music Assistant:** mDNS discovery doesn't work on Android Things, so set
  `sendspin.ma_url` and `sendspin.ma_token` by hand. Leave `sendspin.server`
  blank. Assign the media player to an area in Home Assistant so that voice
  commands like "stop playing" work.
- **Voice pipeline:** **To verify.** On 2026-11-08 the Master Bedroom display
  was still set to `Home Assistant Cloud`. Set the local pipeline for a fully
  local setup.
- **Theme:** select any theme in Home Assistant. Not observed on the current
  build's WebView 87; the white-card issue was only seen on the old build.

## Known issues (open)

### Volume buttons do nothing (fixed)

**Observed (2026-11-08):** the buttons aren't Linux input keys. They're GPIOs
read by `com.google.android.things.sparrow.oem`, which logs
`VolumeObserver: Volume listener notified with value: DOWN/UP` for every press.
It forwards presses to a registered
`com.google.sparrow.IVolumeKeyEventListener`, a Google component; that's my
inference from the app's strings. Nothing on the converted build registers as
that listener. So Android never sees a volume key, no media session gets it,
and `sendspin.master_volume` can't help.

**Fixed with a boot helper (observed working on the Master Bedroom display,
2026-11-08).**

- **Pins:** `gpio85` is volume up (`active_low=1`) and `gpio1019` is volume
  down. Both are already exported in `/sys/class/gpio` and read `1` while
  pressed. The log's `value: DOWN/UP` is press and release, and it's the same
  for both buttons, so the pins are the only way to tell them apart.
- **Helper:** `bootfix/volkeys/VolKeys.java`, built into
  `/system/framework/ks-volkeys.jar`. It's a long-running `app_process`
  program that polls both pins every 30 ms and injects `KEYCODE_VOLUME_UP` or
  `KEYCODE_VOLUME_DOWN` through `InputManager.injectInputEvent`. Kiosk
  Satellite receives them as normal volume keys (`dispatchVolumeKeyEvent`).
- **5 keys per press:** music volume has 100 steps here
  (`ro.config.media_vol_steps=100`), so one key is 1%. Five keys make one press
  equal Kiosk Satellite's 5% step. Holding repeats after 0.5 s, every 0.3 s.
- **Started by** `ks_volume_keys` in `ks-boot-fix.rc`, through the
  `ks-volume-keys.sh` launcher, which is labelled `dumpstate_exec`.

Build it on the PC with JDK 17+ and the Android SDK:

```bash
cd bootfix/volkeys
javac --release 8 -cp $ANDROID_SDK/platforms/android-35/android.jar -d build/classes VolKeys.java
(cd build/classes && jar cf ../classes.jar ks/*.class)
$ANDROID_SDK/build-tools/35.0.0/d8 --min-api 26 --lib $ANDROID_SDK/platforms/android-35/android.jar --output build/ks-volkeys.jar build/classes.jar
```

Install it next to the light sensor fix:

```bash
adb push bootfix/volkeys/build/ks-volkeys.jar /system/framework/ks-volkeys.jar
adb push bootfix/ks-volume-keys.sh /system/bin/ks-volume-keys.sh
adb shell chmod 644 /system/framework/ks-volkeys.jar
adb shell chmod 755 /system/bin/ks-volume-keys.sh
adb shell chcon u:object_r:dumpstate_exec:s0 /system/bin/ks-volume-keys.sh
```

What didn't work, and why:

| Attempt | Result |
|---|---|
| Watching sparrow.oem's log line, then reading the pins | Most taps were already released by the time the line arrived |
| Shell script writing to `/dev/input/event2` with `sendevent` | Works as root, but the `dumpstate` domain is denied `input_device` |
| `inputdriver_daemon` or `peripheralman` domains | They can't run shell scripts (`shell_exec` denied) |
| `input keyevent` from a script | Works from `dumpstate`, but about 0.94 s per press, from Java start-up |

The Java helper uses the same `InputManager` path as `input keyevent`, but
starts Java only once. Its only denials are for writing a compiled copy of the
code (`dalvikcache`), so it runs uncompiled, which is fine at this size.

### Light sensor missing after boot (Kiosk Satellite as home launcher)

**Observed (2026-11-08):** after a boot, Kiosk Satellite had no light sensor
connection and brightness stayed at 204. Restarting the app fixed it at once.
The VCNL 4200 is a *dynamic* sensor that `sparrow.oem` registers after boot.
As the home launcher, Kiosk Satellite starts before that and doesn't pick up
the sensor when it appears. That matches the report that it worked while the
launcher chooser delayed start-up.

**Fixed with a boot service (observed working on the Master Bedroom display,
2026-11-08).** Files are in `bootfix/`:

- `ks-boot-fix.sh` waits until `dumpsys sensorservice` lists the VCNL 4200,
  then force-stops Kiosk Satellite and relaunches the home screen. It logs under
  the `ks-boot-fix` tag.
- `ks-boot-fix.rc` is a **separate** file in `/system/etc/init/`, which init
  loads on its own. It starts the script on `sys.boot_completed=1`.
  **`/init.rc` is never edited.** A bad `.rc` file is only skipped, so the device
  still boots.
- **SELinux:** `seclabel u:r:su:s0` is refused
  (`avc: denied { transition } … tcontext=u:r:su:s0`). Instead, label the script
  `dumpstate_exec`. init is always allowed to start that type in the `dumpstate`
  domain, which can run `dumpsys` and `am`.

Install, with `adb root` and `adb remount`:

```bash
adb push bootfix/ks-boot-fix.sh /system/bin/ks-boot-fix.sh
adb push bootfix/ks-boot-fix.rc /system/etc/init/ks-boot-fix.rc
adb shell chmod 755 /system/bin/ks-boot-fix.sh
adb shell chmod 644 /system/etc/init/ks-boot-fix.rc
adb shell chcon u:object_r:dumpstate_exec:s0 /system/bin/ks-boot-fix.sh
```

Result after a reboot with the power pulled (cold boot, 2026-11-08): the
sensor was registered about 2 seconds after `boot_completed`. Kiosk Satellite
was restarted, its new process attached to the light sensor, and its Adaptive
brightness screen showed the sensor again. **Fixed.**

To remove it, delete both files.

A last-resort alternative, if a device can't take the boot service: a Home
Assistant automation presses the "Restart app" button after a fresh boot. Guard
it with a cooldown on that button's last-pressed time, otherwise the app
restart re-triggers it (network uptime goes `unavailable` and comes back
unchanged).

### Touch "stops" in a dark room; music stutters

**Likely root cause (observed 2026-11-08):** Kiosk Satellite's
`screen.hide_navigation_bar=true` hides the navigation bar without immersive mode
(`vsysui=0x702`). On Android 8 that puts a full-screen invisible
`nav_input_consumer` window (1280×800) above the app, to catch the touch that
would bring the bar back. Android Things has no navigation bar, so touches are
swallowed intermittently. Fix: set `screen.hide_navigation_bar=false` with
`PATCH /api/settings` or the app's Screen settings. Afterwards the consumer
window was gone and `vsysui=0x700`. **Touch confirmed fixed on both displays
(2026-11-08).** Reported upstream as
[kiosk-satellite#1358](https://github.com/jxlarrea/kiosk-satellite/issues/1358).
Whether this also fixed the music stutter is **To verify**. The notes below
are the investigation, kept for the record.

Observed (2026-11-08):
- The touch hardware works. At about 8% backlight and while touch had
  "stopped", the panel kept sending normal events (31 taps in 15 seconds).
  Android delivered them to Kiosk Satellite's focused window, so this is the app
  not responding, not touch or the backlight.
- Kiosk Satellite keeps the camera open for motion detection: the app plus
  `mm-qcamera-daemon` use 40–130% CPU. It also rebinds the camera when its
  mode changes.

Observed at the moment of a freeze, 13:53 on 2026-11-08, with the lights off:
- Touch stopped, and Kiosk Satellite's on-screen lux froze at 1.
- The hardware sensor kept reporting about 40 lux, live, and Kiosk Satellite
  still held its sensor connection.
- Brightness kept changing, so part of the app was still running.
- A stack dump showed the Android main thread idle, not blocked, and the
  Flutter raster thread nearly idle. So the UI stops drawing and handling
  input, but the process is alive.
- The busiest thread is `DartWorker`, at about 45 s of CPU in 5 minutes.

It happens every time the lights go off, sometimes after about a minute. With
the lights on and the backlight forced to about 8%, touch kept working. **So it's
something in Kiosk Satellite triggered by darkness, not the backlight or the
touch panel.** Camera motion detection (`motion.sensor`) is the main suspect.

**Next test:** turn off the motion sensor in Kiosk Satellite's own settings,
not by editing its file. Then turn the lights off. If it still freezes, report
it to Kiosk Satellite with the data above.

**Lesson (2026-11-08):** never edit `FlutterSharedPreferences.xml` with
`sed -i`. The rewritten file loses the app's SELinux categories
(`app_data_file:s0:c512,c768`), the app can't read its settings, and it starts
the setup wizard. Change settings through the app or its remote admin API. If a
restore is ever needed: force-stop, `cp` the backup, `chown u0_a36:u0_a36`,
`chmod 660`, then `chcon u:object_r:app_data_file:s0:c512,c768`.

### Updates need a tap on screen (device owner set)

**Done on the Master Bedroom display (2026-11-08):**
`dpm set-device-owner me.jxl.kiosk_satellite/.KioskAdminReceiver` returned
`Success`, and `dumpsys device_policy` shows Kiosk Satellite as Device Owner.
Kiosk Satellite's docs say device owner gives silent self-updates on every
Android version. Whether the next real update installs with no tap is **To
verify**, when Kiosk Satellite next ships one. Only a factory reset, which means
a reflash here, removes device owner.

Background:

- The `REQUEST_INSTALL_PACKAGES` app op only lets the install prompt appear.
- Silent updates need **device owner**:
  `dpm set-device-owner me.jxl.kiosk_satellite/.KioskAdminReceiver`. Only a
  factory reset removes it.
- Or use Kiosk Satellite's update helper, which stops at every reboot.
- Prerequisites observed: no accounts and one user.

### Other

- A debug-build `console` service restarts every 5 seconds and gets killed
  (SELinux denials). It's harmless, but it's constant churn. **To verify**
  whether stopping it changes anything.

## Verify before publishing

- [ ] Wi-Fi method on the `OIMK` build (`wpa_cli` vs the `AddWifi` helper)
- [ ] Whether `androidthingshost` really carries the light sensor, given that
      `sparrow.oem` contains the VCNL 4200 driver
- [ ] Volume `value` meaning: press one button only, several times
- [ ] Whether the Kitchen display matches every observation above (only the
      Master Bedroom display was checked on 2026-11-08)
- [ ] Whether the voice pipeline is local on both displays
- [ ] Exact `dd` offsets and commands used to extract images from `FRW.bin`
- [ ] Before publishing, remove the serial, LAN addresses, Wi-Fi name and
      dashboard URL from the scripts and notes

## Credits

deadman96385 (AVB unlock, firmware, XDA thread), RYuhMine (`OIMK` userdebug
archive), jxlarrea (Kiosk Satellite), dimatx (WebView procedure,
kiosk-satellite discussion #846), bkerler (edl).
