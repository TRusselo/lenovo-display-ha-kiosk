# Time zones

## Why old displays show the wrong time

A device works out local time from a time zone database: the rules for every region, including when daylight
saving starts and ends. These displays shipped with the 2020 edition of that database and never get updates.

Since then, several states, provinces and countries have changed or ended daylight saving. A display still
following the old rules is an hour off for part of the year, even though its zone setting is right.

## What this tool does

It installs the current [IANA time zone database](https://www.iana.org/time-zones), built into Android's own
format, before you pick your zone. Then you choose your time zone on the display, under ☰ > System > Date &
time, and the clock follows today's rules.

That list is fixed in Android Things and misses some zones, America/Edmonton among them. If yours isn't there,
pick any zone, and type the right one when the tool asks for it after Wi-Fi connects. It checks the name
against the installed database and sets it; the display uses it from its next restart. Don't pick from the
list again afterwards, or it replaces the zone you typed.

To change it later without the tool: `adb shell setprop persist.sys.timezone America/Edmonton` (as root),
then restart the display.

Tested on a converted display: Kiosk Satellite's clock, Android's system clock and Home Assistant dashboards
all showed the right time for a region whose rules changed in 2026.

The file is built from the official IANA release by `spikes/tzdata/build_tzdata.py` and lives in
`assets/tzdata/tzdata`. When IANA publishes a new release, rebuild it with that script, which needs `zic`
from the IANA tz code, and run the tool's time zone step again.

## If a time is still wrong

- **Only on a Home Assistant dashboard:** dashboards run in the display's built-in web browser (WebView), which
  carries its own copy of time zone data. In Home Assistant, open your profile and set the time zone option to
  use the server's time zone. If that's still wrong, pick a zone on the display with the same offset whose rules
  never changed.
- **Everywhere:** check the zone picked on the display, and that the display is on Wi-Fi so it can set its
  clock.
