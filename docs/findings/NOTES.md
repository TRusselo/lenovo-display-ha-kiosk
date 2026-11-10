# Lenovo Smart Display to Home Assistant local voice: progress notes

Working notes for a later GitHub post, repo or install guide. Goal: take Lenovo
Smart Displays off Google and run them as Home Assistant voice satellites with a
dashboard, in the spirit of
[echo-dot-assist](https://github.com/Gamer92000/echo-dot-assist).

**Status (2026-11-05): BOTH displays fully converted, with working ambient-light
sensor (adaptive brightness).** The key that unblocked everything: use the
`iot_msm8x53_som-userdebug OIMK.211005.001` debug firmware (the **same version
as stock**, so the VCNL 4200 light + proximity sensors work) — NOT the old
`jasper-blueberry OIM6.190107.017` debug build, which is the wrong base (light
sensor missing). Root, light sensor, proximity, de-Google, Kiosk Satellite and
Music Assistant now all work together on both displays (kitchen <display-ip>,
master bedroom <display-ip>). WebView is the stock 87.0.4280.101 and renders
Home Assistant fine — no "browser too old" error, so the old WebView 66→138
upgrade is no longer required.

Evidence labels:
- **Observed:** read from my own devices.
- **Reported:** from someone else's write-up, not reproduced here.
- **Unknown:** still has to be tested.

## The right firmware (key finding, 2026-11-05)

**Use `iot_msm8x53_som-userdebug OIMK.211005.001`, not the old jasper-blueberry
debug build.**

- **The problem:** the `jasper-blueberry OIM6.190107.017` debug build has root
  (`adb root`) but the ambient-light sensor is missing (all sensors are
  dynamic-only; `getDynamicSensorList(TYPE_LIGHT)` returns empty). Stock
  (`OIMK.211005.001 user`) has the light sensor but no root.
- **The fix:** there is a **userdebug build of the same OIMK.211005.001** version.
  It is the "unified" debug firmware for the Lenovo 8"/10" (and JBL Link View),
  and it has BOTH: `ro.debuggable=1`/`ro.build.type=userdebug` (so `adb root`
  works) **and** the same kernel as stock (so the VCNL 4200 light sensor works).
- **Download:** RYuhMine's archive —
  `https://archive.org/download/android-things-oreo-builds/OIMK.211005.001-userdebug-blueberry-FRW.7z`
  (a single `FRW.bin`, 3.9 GB full-eMMC dump; extract `boot_a`/`system_a`/
  `vendor_a`/`oem_a`/`vbmeta_a` from the GPT with `dd`, convert the big ones to
  sparse with `img2simg`, then `fastboot flash`).
- **Verified on both SD-8501F (kitchen + master bedroom):** booted
  `userdebug/dev-keys`, fingerprint
  `…OIMK.211005.001/7795499:userdebug/dev-keys`; `adb root` → uid 0; `dumpsys
  sensorservice` shows `VCNL 4200 Ambient Light Sensor` **and** `VCNL 4200
  Proximity Sensor` active; Kiosk Satellite's `/api/commands/getLightLevel`
  returns `{present: true, lux: <live value>, live: true}` (both read ~26–27 lux
  in a dim room).
- **De-Google on this build** (`pm disable`, survives reboot):
  - `com.google.assistant.gallium.dragonglass.platform.androidthings.system`
  - `com.google.android.apps.mediashell`
  - `com.google.android.things.checkin`
  - `com.google.android.things.customcheckin`
  - **Do NOT disable `com.google.assistant.gallium.client.androidthingshost`** — it is the
    Android Things *sensor host* that registers the VCNL 4200 light/proximity sensors, and
    disabling it makes the ambient-light sensor disappear after reboot (it carries the
    Assistant launcher `GalliumActivity` spinner too, but that's harmless behind Kiosk
    Satellite; the component can't be disabled individually — "Shell cannot change component
    state"). The phone-home/Assistant parts are the other four packages above.
  - Leave everything else `com.google.*` enabled — the `things.internal.*`
    (net/media/bluetooth/adb), `ext.*`, `tts`, `inputmethod.home`, `wifisetup`,
    `permissions`, `gsf` are framework/OS parts, not the Assistant. Disabling
    them breaks Wi-Fi/audio/input.
- **Kiosk Satellite self-update fix.** The in-app "Updates" screen fails on these
  devices for two reasons, both fixed with adb root:
  1. **"Not enough space on existing volume"** — `/data` (1 GB) fills with a
     leftover `us.spotco.mulch_wv` WebView from the old 66→138 upgrade (~107 MB)
     plus `vmdl*.tmp` failed-download stubs (~92 MB each). Fix:
     `pm uninstall us.spotco.mulch_wv` then `rm -rf /data/app/vmdl*.tmp`.
  2. **"Not allowed to install unknown apps"** — there is no Settings UI, so the
     `REQUEST_INSTALL_PACKAGES` AppOp stays `deny`. Fix:
     `appops set me.jxl.kiosk_satellite REQUEST_INSTALL_PACKAGES allow`
     (`pm grant` does **not** work — it's an AppOp, not a changeable runtime
     permission).
- **Do NOT rootify stock.** On this device the ramdisk is discarded (system is
  mounted as root, `/dev/root on / type ext4`), and `ro.debuggable` is derived
  from `ro.build.type`, so editing the ramdisk `prop.default` or the system
  `build.prop`/`default.prop` never sticks. Flashing the userdebug build is the
  only reliable route.

## Mic gain, sensors, and volume (2026-11-05)

- **Mic was ~20–30 dB too quiet** at the raw analog stage. The Kiosk Satellite
  digital `audio.mic_gain_db` alone (even +24 dB) wasn't enough. **Fix:** raise the
  analog/codec gain in `/system/etc/mixer_paths_openq624_fep.xml` — `ADC1/2/3 Volume`
  6→12 and `DEC1/2 Volume` 84→96 — then `adb remount` + push + reboot. Combined with
  `audio.mic_gain_db=24` and `audio.mic_capture_mode=voice_communication` (the call
  path carries the multi-mic array + noise cancellation), wake-word detection went
  from ~12 inches to **10+ feet**. Note the stock and userdebug `mixer_paths` are
  byte-identical (ADC was always 6) — the stock only sounded right because Google
  Assistant did its own AGC/beamforming on top.
- **Volume buttons**: Android routes the hardware volume keys to Kiosk Satellite's
  Music Assistant media session (always "connected"), not the device's STREAM_MUSIC.
  **Fix:** set `sendspin.master_volume = True` ("Control the device volume") — then
  the buttons change the MA player volume, which MA applies to the device, and
  assistant sounds follow. Confirmed: VOLUME_UP moves MA volume 48→49 and STREAM_MUSIC
  follows. (`sendspin.volume_keys` / `kiosk.disable_volume` are not the fix;
  `sendspin.master_volume` is.)
- **Light sensor attach is racy across reboots**: Kiosk Satellite's `LightSensor`
  sometimes doesn't re-attach to the VCNL 4200 after a boot (the sensor host is still
  enabled; it's a boot-timing race, not the host). **Manual fix:** restart Kiosk
  Satellite once after boot —
  `adb shell "am force-stop me.jxl.kiosk_satellite"` then
  `adb shell "am start -n me.jxl.kiosk_satellite/.MainActivity"` — and the light level
  returns (`present: true, live: true`).
- **Do NOT add an init.rc boot service for this.** Attempting a `service …` +
  `start` in `/init.rc` (to auto-restart Kiosk Satellite 45s after boot) soft-bricked
  the device (no boot, stuck in fastboot). Recover by re-flashing `system_a`. Writing
  `/init.rc` also needs `setenforce 0` first (SELinux blocks it — the failed `adb
  push` silently *deleted* `/init.rc`, which is boot-critical). Keep the manual
  restart; don't touch init.rc.

## Why this started

Alberta moved to permanent UTC-6 on 2026-11-01. The displays no longer get
firmware updates and kept showing UTC-7, an hour behind.

- **Observed:** both displays report `timezone: America/Edmonton` over their local API.
- **Observed:** tzdata 2026f on a Linux PC has Edmonton at UTC-6 after the change,
  matching `America/Regina`.
- **Inferred, not confirmed:** the displays carry tzdata from before the change.

## Hardware

| | |
|---|---|
| Model | Lenovo Smart Display 8, `SD-8501F`, codename Amber |
| Stock OS | Android Things 8.1 |
| Cast build | `1.56.285116` |
| OEM version | `40.16.5+opal_prod.1.1.0.7795499` |
| System build | `OIMK.211005.001` |

All observed from `eureka_info`, except the codename and OS, which are reported.

A Lenovo Smart Clock on the same network has Cast build `1.56.285116`, OEM version
`11.51.6+prod.1.1.0.7795499`, and the same `America/Edmonton` setting. It is not
covered by the unlock guide below.

## Local Cast API

Useful for anyone who only wants to fix the clock and keep Google.

- **Observed:** `GET https://<ip>:8443/setup/eureka_info?params=settings` works with
  no token and returns the time zone. The certificate is self-signed.
- **Observed:** `POST /setup/set_eureka_info` with no token, or with an invalid
  `cast-local-authorization-token` header, returns HTTP 401.
- **Unknown:** whether a POST of `{"settings":{"timezone":"America/Regina"}}` with a
  valid token works, updates the displayed clock, and survives a reboot or Google
  sync. `set_cast_timezone.py` does this, but it has never been run with a real token.
- **Reported:** tokens can be fetched with
  [glocaltokens](https://pypi.org/project/glocaltokens/) and are short-lived.

No longer the plan, since the goal is now de-Googling. Kept as a footnote for the
write-up.

## Unlock and flash (reported, not yet done here)

Source: [XDA thread by deadman96385](https://xdaforums.com/t/lenovo-smart-display-8-10-amber-blueberry-avb-bootloader-unlock-firmware.4472049/)
for SD-8501F, SD-X701B and SD-X501F. Read the thread itself before flashing.

1. Unplug power. Peel the adhesive silicone cover off the bottom right to reveal a
   USB-C port. Connect it to the PC with a USB-A to USB-C cable.
2. Hold volume down, plug in power, and keep holding for 10-15 seconds to reach
   fastboot. It boots slowly.
3. Run `fastboot flashing unlock`.
4. Unlock AVB with the thread's tool: `at_auth_unlock.exe creds\`, or `avb-unlock.bat`.
   **The stock OS no longer boots fully after this.**
5. Flash firmware with the `flash-all` script in the firmware zip.
6. Use adb and adb root to set up the device.

Warnings from the sources:
- **Never run `fastboot oem at-lock-vboot!` on non-stock firmware.** It reportedly
  hard-bricks the device, needing EDL recovery.
- With AVB off the device can't reach its TEE keys, so the thread says the user
  firmware won't finish setup.
- The unified debug firmware was only tested on the 10", and the thread says it
  should work on the 8". Separate 8" firmware is also listed.

Before starting, download and keep a copy of these, all linked from the thread's
first post. All four links answered on 2026-11-03. Record hashes once downloaded.

| File | Purpose | Size |
|---|---|---|
| `Amber-factory-S0.28.20-20180510_US.zip` | 8" stock debug firmware; the thread marks it untested | 736 MB |
| `jasper-blueberry_Prod-MSM8x53_2089_8.12.3+debug.1.1.0.5307861_development_build.zip` | Android 8.1 debug firmware | 626 MB |
| `Lenovo-Android-Things-avb-unlock.zip` | AVB unlock tool | 4 MB |
| `amber_bluebbery_prog_emmc_firehose_8953_ddr.zip` | EDL recovery | under 1 MB |

Reported in the thread: a launcher that opens and then closes isn't supported by
Android Things, and one without widget support, such as KISS Launcher, is needed.

## Setup notes for Linux

- **Observed:** the unlock tool named in the thread is a Windows `.exe`. Wine is
  installed here, but running the tool under it is **untested**. A Windows machine
  is the fallback.
- **Observed:** existing udev rules only cover the Echo IDs (`0e8d`, `1949`,
  `0bb4:0c01`). The display's fastboot USB ID isn't known yet, so it may need its own
  rule. Record it from `lsusb` the first time it connects.
- **Observed:** with one display reportedly plugged in over USB, `lsusb`, `adb
  devices` and `fastboot devices` show nothing from Lenovo, Google or Qualcomm.
  Check that the cable is in the hidden USB-C port, and try fastboot mode.

## Download review (read only, nothing flashed)

SHA-256 of the files as downloaded:

```
8ebe3fd8c93f27e4c9fb043462ea97375514b58e1e6a65521cfec3e8845757e9  Amber-factory-S0.28.20-20180510_US.zip
891ffcad69a44cbe1121aa3165302e3a78b981b7e81bc0244175a24b00a24719  jasper-blueberry_Prod-MSM8x53_2089_8.12.3+debug.1.1.0.5307861_development_build.zip
8e2ae30844961614cff7e4aeb1ed0d4d08d1f617aaf27d0835b79ed91d0c8be3  Lenovo-Android-Things-avb-unlock.zip
e5abaec6fca5e0dc3a79c050fc06aa047f1b521ffb2e7ec8cb0f2140f09a06b1  amber_bluebbery_prog_emmc_firehose_8953_ddr.zip
```

Observed from the files themselves:

- **No Wine needed.** The AVB zip includes `at_auth_unlock.py`, the source of the Windows
  tool's job. It needs Python with a `Crypto` module (PyCryptodome should provide it,
  untested) and only calls `fastboot`. It makes no network calls. Credentials for Amber are
  in `creds/amber-unlock_credentials.zip`.
- **Stock script relocks.** `flash-all.sh` in the Amber stock zip ends with
  `fastboot oem at-lock-vboot`, with no prompt. Don't run it without reading it first.
- **The debug firmware's partition table differs from the Amber stock zip's.** Same 56
  partitions and sizes, but 23 are at different offsets, and only some get reflashed.
  Moved and not rewritten: `devinfo`, `factory`, `factory_bootloader`, `keystore`,
  `config`, `limits`, `dip`, `syscfg`, `mcfg`, `apdp`, `msadp`, `dpo`. Their old contents
  would no longer line up. `devinfo` and `factory` are the worrying ones. `persist` and
  `modemst` don't move, and `persist` isn't flashed by either script.
- **Not known:** the layout actually on my display. It runs a 2021 build, so it may not match
  either table. Fastboot only reports sizes. Reading the GPT over EDL would show offsets.
- **Debug `flash-all.sh` overwrites both slots** and the bootloader chain (`sbl1`, `aboot`,
  `tz`, `rpm`) by default, so no stock slot is left to fall back on. It also formats
  userdata. `FLASHB=false` limits it to slot A, but the table is still rewritten.
- **The stock zip isn't the current stock OS.** It's from 2018, and the display runs
  `OIMK.211005.001` from 2021. It may not be an exact way back.
- **Panels:** both the stock and debug kernels list the same smaller-panel entries
  (`hx8394d wxga`, `hx83100a 800p`), so the debug kernel may well drive the 8" screen. Which
  panel this unit has isn't known, and a blank screen remains possible.

Before unlocking: try a read-only EDL backup and GPT dump. A possible safer flash, also
untested, is to skip the partition table and bootloaders and write only `boot`, `system`,
`vendor`, `oem` and `vbmeta`.

## Observed boot sequence (SD-8501F, stock, volume down at power-on)

| Time | USB device | State |
|---|---|---|
| 0 s | `05c6:9008` | Qualcomm EDL (QDL) mode, also binds `qcserial` |
| 19 s | none | EDL disconnects |
| 26 s | `18d1:d00d` | Fastboot |
| 41 s | none | Fastboot disconnects, display then boots stock normally |

The thread's 10-15 second hold looks too short here. Fastboot appeared 26 seconds
after USB connect. The screen stayed blank while volume down was held, and the
display started booting when it was released, about 15 seconds into fastboot.

Kernel log for the whole session (corrects an earlier conclusion that fastboot lasts
exactly as long as the button is held):

| Connect | USB device | Disconnect |
|---|---|---|
| 21:43:14 | `05c6:9008` EDL | 21:43:33 |
| 21:43:40 | `18d1:d00d` fastboot | 21:43:55 |
| 21:45:33 | fastboot | 21:45:48 |
| 21:46:11 | EDL | 21:46:26 |
| 21:48:07 | fastboot | 21:48:22 |
| 21:48:27 | fastboot (`getvar all` ran here) | 21:48:38 |
| 22:02:43 | fastboot | 22:02:58 |

So fastboot sessions usually end after about 15 seconds. In the one run with the button
held throughout, it dropped and came back 5 seconds later. **The 21:48:38 drop was before
the instruction to release was sent, so release didn't cause it.** Likely, but unproven:
fastboot has a 15-second timeout, and a held button re-enters it on the next boot. Not
known: whether a running flash survives that timeout. Use a clip for now.

**Staying in fastboot (observed):** letting go of the button right after fastboot appears
kept it connected for over 70 seconds (22:24:41 onward), and it was still up when checked.
No clip needed; a held button seems to be what causes the 15-second resets. Use a USB-list
loop to see the mode, since the screen stays blank.

**Unlock attempt (2026-11-03):** `fastboot flashing unlock` on the 2021 stock build failed
with `oem unlock is not allowed`. State afterward: `unlocked: no`, `secure: yes`,
`bootloader-locked=1`, `avb-locked=1`. Nothing changed. Fastboot stayed up for over 5 minutes
this time, so the 15-second drop is not a problem once the buttons are released.

**AVB unlock (2026-11-04, DONE):** the bootloader unlock is a red herring on this build.
`fastboot flashing get_unlock_ability` returns `0` (permanently disallowed), but
`at-vboot-state` shows `avb-unlock-disabled=0`, so the authenticated AVB unlock is the real
path — matches the thread's note that newer firmware ties the BL unlock into AVB.

- `python3 at_auth_unlock.py creds/` works with **no Wine needed**. System Python already
  has PyCryptodome (`from Crypto.Hash import SHA512` etc.). The tool found
  `amber-unlock_credentials.zip` by product-ID hash (`7867a4…`) and ran clean.
- Sequence it runs: `oem at-get-vboot-unlock-challenge` → `get_staged` → sign challenge with
  the PUK key → `stage` → `oem at-unlock-vboot` → `getvar at-vboot-state`.
- **Result: `avb-locked=0`.** `bootloader-locked` stays `1`, `unlocked:no`, `secure:yes`.
  That is expected and does not block flashing — the debug `flash-all.sh` only gates on
  `avb-locked`, not on the `unlocked` bit.
- Serial is `<serial-1>`. Fastboot access needs no udev rule; ID is `18d1:d00d`.
- This is reversible while on stock: `fastboot oem at-lock-vboot` relocks. Do NOT relock
  after flashing the debug firmware (different keys).

## Firmware to flash next

Goal: Android 8.1 debug (`jasper-blueberry_Prod-MSM8x53_…_development_build.zip`), the same
path mirodawa used to get a dashboard on the 8". Risks to respect:

- Do **not** flash the debug `partition-table.img` and do **not** run its `flash-all.sh`
  unmodified — the real GPT matches the *stock* Amber zip, not the debug table.
- Skip the bootloader chain (`sbl1/aboot/tz/rpm`) on the first attempt and flash only
  `boot`, `system`, `vendor`, `oem`, `vbmeta` (slot A), keep slot B stock as fallback.
- The debug `flash-all.sh` `format userdata` step fails on newer fastboot
  (`mke2fs: invalid option -- 'b'`); use `fastboot erase userdata` instead. Several thread
  users hit this.
- Audio risk (reported): a Reddit write-up on this exact device says the **amplifier fails
  to load after the XDA firmware flash**. Speaker output is a real unknown, not just the mic.

## Voice + dashboard bring-up (2026-11-04, evening)

- **Mic was ~20–30 dB too quiet** (peak −39 to −45 dBFS; wake-word score 9–10.5 vs
  threshold 11 = near-miss only when speaking loud & close). The ALSA card, WSA881x amp
  and PMIC analog mic are all present; mixer_paths + audio_policy are byte-identical to
  stock, and no ACDB data exists on either stock or debug, so it's not a "missing cal" I
  can restore. **Fix that worked: Kiosk Satellite Mic Gain** (`audio.mic_gain_db`, −24…+24)
  set to **+15 dB** and `voice.wake_word_sensitivity` to **very**, via
  `PATCH /api/settings` on the remote admin (port 2324). Detection is now reliable.
- **Remote admin** auth: `POST /api/login {"password": <admin pw>}` → token (the pw is
  stored plaintext in `FlutterSharedPreferences.xml` as `remote.password`). Settings are a
  PATCH of `{key: value}`; `audio.mic_gain_db` is a `number` (step 1 dB).
- **Pipeline is still "Home Assistant Cloud"** (`voice.ha_pipeline`) — switch to the local
  "Hassistant" pipeline for a fully-local setup.
- **Dashboards are broken because the WebView is Chromium 66** (2018). JS console shows
  missing `Intl`, WebRTC `addTransceiver` (Chr 73+), `Element.getAnimations()` (Chr 84+).
  Same dashboards render fine on the Echo Show 8.
- **WebView upgrade is blocked by a private signing key.** The build is `userdebug`/`dev-keys`
  but signed with a NON-public Lenovo/Google platform key (SHA-1 `cd21ab22d1d1b6388aaceaa52b82be3fa4e60c58`;
  the public AOSP test keys do not match). Consequences:
  - Can't re-sign `framework-res.apk` to add a WebView provider to `config_webview_packages`
    (which only allowlists `com.android.webview`).
  - Can't repackage Mulch (`us.spotco.mulch_wv`, Chromium 131, armeabi-v7a, minSdk 26 —
    the only recent 32-bit WebView) to `com.android.webview`: `apktool` fails on an
    unresolvable framework package ("package id 36"); its native lib is package-agnostic and
    the dex has only one R-class ref, so it's *nearly* repackageable, but the manifest decode
    is the blocker.
  - Can't RRO-overlay `config_webview_packages`: the `<webviewprovider>` attributes
    (`availableByDefault`, `packageName`, `description`) are private attrs not resolvable
    from an overlay XML.
  - **Recoverable state achieved anyway:** `/system` made writable (`adb disable-verity` +
    reboot + `adb remount`), Mulch installed (not active), WebView still 66.
- **SOLVED (2026-11-04, later):** upgraded the WebView via the procedure from
  [kiosk-satellite discussion #846](https://github.com/jxlarrea/kiosk-satellite/discussions/846)
  (dimatx, SD-X701B). Steps:
  1. Back up `/system/app/webview`, `/data/system/packages.xml` + `packages.list`, and
     Kiosk Satellite's `/data/data/me.jxl.kiosk_satellite/`.
  2. `mv /system/app/webview /data/local/tmp/webview-old` (system is RW after
     `adb disable-verity` + reboot + `adb remount`).
  3. Surgically remove the `com.android.webview` `<package>…</package>` block from
     `packages.xml` and the `com.android.webview …` line from `packages.list` (uid 10031,
     no shared-user). This is the fix for `INSTALL_FAILED_UPDATE_INCOMPATIBLE` — it clears
     the old Lenovo-key signature so a differently-signed `com.android.webview` can install.
  4. Reboot, then `adb install` **LineageOS WebView 138.0.7204.63 arm-v7a minAPI26**
     (APKMirror). The newer 155.x is minAPI29 → won't install on API 27.
  - Result: WebView 138 active + survives reboot; Kiosk Satellite survived (surgical edit
    did NOT drop user apps, unlike dimatx's report); mic-gain config intact; the Chromium-66
    JS errors (Intl / addTransceiver / getAnimations) are gone. Only a benign
    `localStorage: Access is denied` console line remains.
  - **Music Assistant doesn't auto-pair:** Kiosk Satellite normally discovers MA via mDNS
    during HA setup (the Echo did this, no second login). On this device the Android Things
    build's mDNS/NSD service discovery doesn't fire, so MA sits unpaired. Fix: set
    `sendspin.ma_url` (http://<MA host>:8095) and `sendspin.ma_token` (MA's long-lived access
    token) manually via `PATCH /api/settings`, then `sendspin.enabled=true`. Result:
    `connected=true server=Music Assistant`, player registers as "Master Bedroom Kiosk",
    `synced=true`. A benign secondary `queue watcher connect failed (Connection refused,
    port 51xxx)` remains (live queue stream) but playback works.
  - **Sendspin is not a separate service/Docker.** It's a synced-audio protocol built into
    Music Assistant (server side) + Kiosk Satellite's native player (client side). Nothing
    extra to run. The **"Sendspin server" box should stay blank** (auto mDNS discovery works);
    the docs' "Music Assistant listens on port 8927" is wrong for this MA build — setting
    `sendspin.server=<display-ip>:8927` disconnected the player, so revert to blank.
  - **Voice "stop playing" → "I don't know any media player in this room":** fix in Home
    Assistant by assigning the new media player device to the room/area (e.g. Master Bedroom).
    Then "stop playing" resolves and works.
  - **Floating player had no controls at first:** transient — the player reports `synced=false`
    while it settles, then `synced=true` with full commands (play/pause/stop/next/prev/seek).
    Also `sendspin.player_size=compact` is a display-only card; `large` adds prev/play/next.
  - **Theme quirk:** dashboards with *no theme selected* render cards grey on PC/phone but
    white on the Lenovo — the default theme's card-background CSS falls back to white
    (likely the same localStorage denial, so the theme's CSS vars never load). Selecting any
    theme in HA makes it render identically everywhere. Cosmetic; selecting a theme works around it.

## Flash and bring-up log (2026-11-04)

- **Flashed** Android 8.1 debug (`jasper-blueberry_…_development_build.zip`) to slot A:
  `boot/system/vendor/oem/vbmeta` **plus** `dsp/modem/drm/bluetooth`. Skipped the
  partition-table and the bootloader chain; slot B left stock. Used `fastboot erase
  userdata` (not `format`, which hits `mke2fs: invalid option -- 'b'`).
- **Boots** into Android 8.1.0 `userdebug`, fingerprint
  `Things/iot_msm8x53_som/msm8x53_som:8.1.0/OIM6.190107.017/5307861:userdebug/dev-keys`.
  `adb root` works. `ro.product.cpu.abi=armeabi-v7a`.
- **Audio HW present:** ALSA card `msm8953-openq624-snd-card`; speaker amp is WSA881x
  (`wsa881x-i2c-codec`), mic is PMIC analog codec (uses analog mics — DMIC1/2 pins
  absent, expected). Output device `AUDIO_DEVICE_OUT_SPEAKER` live. End-to-end
  mic/speaker test still pending (no tinycap/tinyplay on the build).
- **Screen:** after AVB unlock + debug flash the Google Assistant launcher
  (`com.google.assistant.core/.launcher.SystemLauncherShim`) shows the Google 4-dots
  spinner forever (no Google reachability, TEE keys gone). Harmless; replaced by Kiosk
  Satellite once launched.
- **Wi-Fi:** `wpa_cli` out-of-band join fails — the framework disconnects with
  `Connected to unknown networkId -1`. Fix: register through the framework. Built a
  tiny `app_process` helper (`AddWifi`, javac + d8) that calls
  `WifiManager.addNetwork/enableNetwork/saveConfiguration/reconnect`; needs
  `Looper.prepareMainLooper()` before `ActivityThread.systemMain()` (else
  "Can't create handler … Looper.prepare()"). Network persists across reboot.
- **Clock:** `setprop persist.sys.timezone America/Regina` (UTC-6, no DST) + NTP after
  Wi-Fi. Correct without touching tzdata (Regina was always UTC-6).
- **De-Google:** `pm disable` on `com.google.android.apps.mediashell`,
  `com.google.assistant.core`, `com.google.android.apps.quartz`,
  `com.google.android.things.checkin`, `…customcheckin`. Stops the mediashell
  crash-loop (`crash_dump32` was burning a whole core). Disable persists across reboot.
- **Kiosk Satellite** `2026.11.6` `armeabi-v7a` installed (`me.jxl.kiosk_satellite`),
  bundles `libbarhopper_v3.so` (wake word) + `libkiosk_wake_fft.so`. Remote admin on
  `:2324`. Home launcher alias is `.HomeAlias` (MAIN+HOME+DEFAULT) but is not
  settable via shell (`SecurityException: Shell cannot change component state`); the
  app enables it itself via its "Home launcher" setting. `.BootReceiver` auto-starts
  it on boot regardless.
- **APK hash:** `kiosk-satellite-2026.11.6.armeabi-v7a.apk`
  `5ed603f91fa4fa997ecbf561e3a4e340a8f59f5da2bdbe58d83a1cc40d0e0913`.

## Satellite app decision

Kiosk Satellite is the pick. Confirmed on its download page: a dedicated **`armeabi-v7a`
build** ("Echo Show devices, older Fire tablets and other budget or older hardware") and a
universal build; needs Android 7.0+. It is fully local (no Google Play Services), has
native voice satellite + on-device wake word, low-power optimizations for old devices, and
needs only a long-lived HA token. The debug firmware likely has no GMS, so anything needing
Play Services is out. View Assist Companion has a dedicated guide for this exact Lenovo but
needs a custom HA integration (`vaca`) plus an audio-relay piece (Stream Assist / webcam
app) — more moving parts. The real gate for *both* apps is whether the mic array and amp
enumerate under the debug firmware; that is the step-5 go/no-go test.

**How to reach each mode (observed):** hold **volume up and volume down together** while
plugging in power for EDL (Sahara). Hold **volume down only** for fastboot. The two early
EDL boots with volume down alone are unexplained.

## EDL results on my display

- **Firehose works.** `amber_bluebbery_prog_emmc_firehose_8953_ddr.mbn` loaded and read at
  about 30 MB/s. `qcserial` has to be blocked first, or edl fails with `Resource busy`:
  `blacklist qcserial` in `/etc/modprobe.d/`, then `sudo rmmod qcserial`.
- **Real partition table: matches the Amber stock zip.** Only the last entry, `dpo`, differs
  (23 sectors vs 16). **The debug firmware's table doesn't match: 23 partitions would move,
  including `devinfo` and `factory`. So don't flash `partition-table.img` from the debug zip
  or run its `flash-all.sh` unmodified on an SD-8501F.** All partition sizes match, so the
  debug images should fit the existing layout.
- **EDL also drops after 15 seconds** (22:12:05 to 22:12:20), as fastboot does, and the
  display then boots normally. Every session ends around that mark, in any mode, so this
  looks like a hardware reset. Possibly a hold-to-reset on the volume button, since Qualcomm
  power chips can do that, or a watchdog. Not known yet.
- **Letting go of the buttons as soon as edl detects the device stopped the reset.** The
  next run stayed connected for over 2 minutes and finished. One run, but the only change
  was releasing the buttons. Not yet tested the same way in fastboot.
- **Full stock backup done (2026-11-03):** all 55 partitions except `userdata`, 2.5 GB, with
  `SHA256SUMS` verified. It's the 2021 stock OS, so it's a closer way back than the 2018 zip.
  **It holds unit-specific data (`persist`, `modemst`, `devinfo`, `keymaster`), so never publish it.**
- The screen stays blank in EDL and fastboot on this model, with no status text.
- First run read `persist`, `modem`, `drm`, `bluetooth`, `sbl1`, `aboot`, `rpm`, `tz`,
  `devcfg`, `modemst1/2`, `misc`, `fsc`, `ssd`, `DDR`, `fsg`, `sec` and `boot`, plus GPT.
  `system_a.bin` is partial. Full backup without `userdata` needs about 2.7 GB, about 90 seconds.

Stock bootloader state, from `fastboot getvar all`: `unlocked:no`, `secure:yes`,
slots A and B with A active and both successful, `max-download-size:0x1fe00000`,
`at-attest-dh:1:p256`. Fastboot access worked from this PC with no new udev rule.

## Satellite software

| | [View Assist Companion](https://github.com/msp1974/ViewAssist_Companion_App) | [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite) |
|---|---|---|
| Lists this Lenovo? | Yes, [View Assist guide](https://dinki.github.io/View-Assist/docs/supported-devices/android-devices/lenovo-smart-display) | Main page doesn't; [one SD-X701B report](https://github.com/jxlarrea/kiosk-satellite/discussions/846) |
| On-device wake word | Yes | Yes |
| Needs in Home Assistant | Custom integration (`vaca`) | Nothing for voice; discovered, plus a long-lived token |
| Android and 32-bit | Not stated on the main page | Android 7+; an `armeabi-v7a` APK is named in the report |
| Known problems | Guide warns its WebView update step has an issue | Screen never truly turns off; WebView update is manual and fragile |

The Kiosk Satellite report on the SD-X701B (Snapdragon 625, 2 GB RAM, Android 8.1,
32-bit only) says these work:
- install and setup
- a Home Assistant dashboard, with about a minute for the first paint of a heavy one
- recovery after a cold boot

It lists wake word, mic quality and speech-to-text as **not tested**.

**The main open question: does the mic array work under the debug firmware, and is
wake word usable? I found no report that confirms this on an SD-8501F.**

## Home Assistant side

Observed on my instance:
- The preferred pipeline, `Hassistant`, is already local: `stt.faster_whisper`,
  `conversation.home_assistant`, `tts.piper` with `en_GB-alan-medium`.
- That pipeline has no wake word entity set. Both apps above do wake word on the device.
- View Assist isn't installed through HACS.
- Other pipelines still use cloud services (Home Assistant Cloud, OpenAI, Gemini,
  Claude). The `Ollama` pipeline also uses Google TTS. Avoid these for a local setup.

## Plan

1. Download and keep the files listed above.
2. Pick one display as the test unit. The other stays on stock until voice is proven.
3. Reach fastboot, record the USB ID, add a udev rule if needed.
4. Unlock the bootloader and AVB, then flash the debug firmware.
5. Confirm adb root works, then record what the mic hardware shows.
6. **Go/no-go test:** install Kiosk Satellite or View Assist Companion and check wake
   word, speech-to-text and audio output.
7. Disable leftover Google services and block the display from reaching Google,
   then check it still works.
8. Set the time zone and confirm the clock is right. Since Android 8.1 has old
   tzdata, `America/Regina` is probably still the simple fix.
9. Repeat on the second display, then script the steps.

## To record during the work

- [ ] Exact firmware zip names and hashes
- [ ] Fastboot and adb USB IDs
- [ ] Whether the Windows tool runs under Wine
- [ ] Mic and speaker results, including wake word range
- [ ] Which app was chosen and why
- [ ] Idle CPU, memory and temperature, on 24/7 power
- [ ] Whether the screen can be turned off
- [ ] Every Google package disabled, and any breakage
- [ ] What failed, and how it was recovered

## Before publishing

- Don't redistribute firmware or the AVB tool's credentials. Link to the source
  thread, since rights to them are unclear.
- `set_cast_timezone.py` contains my device names and LAN addresses. Replace those
  with arguments.
- Never post Google tokens, cookies or device local-token hashes.
- Credit deadman96385 for the unlock work, and the View Assist and Kiosk Satellite
  authors.
- Add a warning that this is irreversible without the saved firmware and can brick
  the device.
