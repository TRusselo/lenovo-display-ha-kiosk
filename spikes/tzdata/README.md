# Spike: current time zone data on Android Things 8.1

**Question:** can the tool fix wrong clocks in regions whose DST rules changed
after the build, so users can pick their real zone?

**Method (Kitchen display, 2026-11-08):**
1. The display shipped with `tzdata2020a` in `/system/usr/share/zoneinfo/tzdata`
   (594 zones).
2. `build_tzdata.py` compiles IANA `tzdata2026f.tar.gz` with `zic -b fat`. Fat,
   because Android 8's libcore reads the 32-bit section, which slim files leave
   empty. It packs the result in AOSP ZoneCompactor's format (header, index of
   name/offset/length, TZif data, `zone.tab` without comments): 597 zones.
   - IANA tarball sha256 `01b4a91cec5167ed48c11e8ab78f2048cead78ce94b0cafcad0ae8c5a3044d3d`.
3. With root and `/system` remounted: pushed it over
   `/system/usr/share/zoneinfo/tzdata`, ran `chmod 644` and `restorecon`, then
   rebooted.

**Results:**

| Check | Before (2020a) | After (2026f) | Expected |
|---|---|---|---|
| Boot | ok | ok, no tz errors in logcat | ok |
| C library, `TZ=America/Edmonton date` | UTC-7 | **UTC-6 (CST)** | UTC-6 |
| C library, `TZ=America/Winnipeg date` | UTC-6 | **UTC-5** | UTC-5 |
| Java (`dumpsys alarm` nowRTC) with `persist.sys.timezone=America/Edmonton` | UTC-7 | **UTC-6** | UTC-6 |
| Kiosk Satellite clock (Flutter, uses the C library) | | see below | |
| Dashboard in the WebView (own copy of ICU data) | | see below | |

**Not covered:** the ICU overlay (`icu_tzdata.dat`). It holds zone *names* and
`android.icu` rules; offsets used by the C library and Java come from `tzdata`.
`tzlookup.xml` is unchanged.

**Verified by eye (user, 2026-11-08):** with the 2026f data and the zone set to
`America/Edmonton`, Kiosk Satellite's clock and the Home Assistant dashboard
times were both correct. **Spike succeeded.** Shipped as `lhk/tzdata.py` with the
built file in `assets/tzdata/tzdata`.
