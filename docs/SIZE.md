# Fitting more on the screen

Out of the box, dashboards look big and little fits on the screen. Android runs these displays at 300 dpi,
so the 1280×800 panel gives a web page only 683×427 of space.

Change it in Kiosk Satellite's settings. **Don't change Android's screen density** (see below).

## The dashboard: Zoom level

Kiosk Satellite settings > **Browser** > **Zoom level**. Lower is smaller:

| Zoom level | Width the dashboard gets |
|---|---|
| 1 (default) | 683 |
| 0.8 | 853 |
| 0.65 | 1050 |
| 0.5 | 1365 |

It takes effect straight away, and taps still land where you touch. 0.65 is a good start.

## Kiosk Satellite's own screens: Scale UI

Kiosk Satellite settings > **Device** > **Scale UI** sets the size of its menu, settings and dialogs. It
doesn't change the dashboard.

## The sidebar

Home Assistant shows its sidebar on pages 870 or more wide, so it can appear at a zoom level below about
0.78. Kiosk Satellite hides it, and the header, by default: settings > **Home Assistant** > **User
Interface** > **Hide the sidebar** and **Hide the header**. Nothing else is needed, and your phone and
browser keep their sidebar.

## Why not change Android's screen density

`adb shell wm density`, or a display size setting on other devices, changes the size of everything. Kiosk
Satellite's dashboard keeps its old size until the app restarts:
- The dashboard is drawn in a smaller box in the top-left corner.
- Taps land in the wrong place. A tap on one button can press another.

If you've already changed it, put it back and restart Kiosk Satellite:

```bash
adb shell wm density reset
adb shell am force-stop me.jxl.kiosk_satellite
adb shell monkey -p me.jxl.kiosk_satellite -c android.intent.category.LAUNCHER 1
```

Tested on a converted SD-8501F, 2026-11-15.
