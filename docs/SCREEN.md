# Turning the screen off

## Use the screensaver at brightness 0

Kiosk Satellite's own screen off doesn't work on these displays (see below). Its screensaver does the same job:

1. In Kiosk Satellite's screensaver settings, turn on **screensaver brightness** and set its level to **0**.
2. Start the screensaver when you want the screen off: after its timeout, on its schedule, or from Home
   Assistant with the display's `switch.<name>_screensaver_active` entity.
3. Tap the screen to wake it. The tap closes the screensaver and brightness comes back. It doesn't reach the
   dashboard underneath, so nothing gets pressed in the dark.

At brightness 0 the backlight is fully off. In a dark room it looks the same as a powered-down panel, with no
glow.

In Home Assistant the same settings are `switch.<name>_screensaver_brightness` and
`number.<name>_screensaver_brightness_level`.

## Why the screen light entity does nothing

Kiosk Satellite's `light.<name>_screen` turns the screen off by asking Android to sleep. Android Things refuses
every sleep request. The power key, the sleep key and the app all get the same answer, in the display's log:

```text
PowerManagerService: Android Things devices don't support sleep yet. Not sleeping...
```

So the entity changes to off in Home Assistant, but the screen stays on. On Kiosk Satellite devices running
full Android, such as an Echo Show with LineageOS, the same entity works.

## What Lenovo's software did

The stock firmware's screen off (a swipe from the left edge) didn't power anything down either. It set the
screen brightness to 0 and showed a black screen, with the panel and touch left on. That's why a tap woke it.
The screensaver at brightness 0 is the same approach.

## Why not power the panel off

The panel can be powered off below Android, through the graphics system. It goes dark, but the touch
controller (Himax) switches off with it, and its driver has no tap-to-wake mode. Only something outside the
screen, such as Home Assistant, could turn it back on, so a tap can't wake it.

Tested on two converted SD-8501F displays, 2026-11-12.
