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

Tested on a converted display: Kiosk Satellite's clock, its alarms and Android's system clock all showed the
right time for a region whose rules changed in 2026. Dashboards need one more step: see below.

The file is built from the official IANA release by `spikes/tzdata/build_tzdata.py` and lives in
`assets/tzdata/tzdata`. When IANA publishes a new release, rebuild it with that script, which needs `zic`
from the IANA tz code, and run the tool's time zone step again.

## Dashboards can still be an hour off

Home Assistant dashboards run in the display's built-in web browser (Android System WebView 87, from 2020).
That browser carries its **own copy** of the time zone rules and ignores the one this tool installs. It can't be
updated far enough to fix this: the newest WebView that runs on these displays is older than some rule changes.

So on a dashboard:

- **Right:** times Home Assistant works out on the server, such as a clock from `sensor.time`, a Markdown card
  template, or a template sensor.
- **Can be an hour off:** times the browser works out itself, from a timestamp. That covers timestamp sensors
  shown by Home Assistant's own cards and pop-ups, history, logbook and calendar times, and custom cards that
  format dates in JavaScript (for example `new Date(...).toLocaleString()` in button-card).

Setting your Home Assistant profile to use the server's time zone doesn't help: the browser still applies its
own old rules to that zone.

**Fix:** have Home Assistant turn the time into text, and show that text. For example, Kiosk Satellite's
"Next alarm" sensor is a timestamp, and a button-card that formatted it showed 7:45 for an 8:45 alarm. A
template helper (Settings > Devices & services > Helpers > Create helper > Template > Sensor) with this state
fixes it:

```jinja
{% set t = as_datetime(states('sensor.my_display_next_alarm'), none) %}
{{ as_local(t).strftime('%a %-I:%M %p') if t else 'none' }}
```

It gives `Thu 8:45 AM`, or `none` when no alarm is set. Point the card at the new sensor and show its state
as it is.

## If a time is wrong everywhere

Check the zone picked on the display, and that the display is on Wi-Fi so it can set its clock.
