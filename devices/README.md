# Other Lenovo Smart Displays

Only the **Smart Display 8 (SD-8501F, "amber")** is tested by the author; the 10" has been converted by a user. The others share the platform (Snapdragon
msm8953/APQ8053, Android Things 8.1) but haven't been tried with this tool.

| Model | Codename | What's known |
|---|---|---|
| Smart Display 10 (SD-X701B) | blueberry | The userdebug dump this tool flashes *is* a 10" disk image, and the AVB unlock credentials include blueberry. The 10" has a 1920×1200 screen and its own partition layout. **Reported working** with `--force-model` ([#5](https://github.com/TRusselo/lenovo-display-ha-kiosk/issues/5)): backup, flash, Kiosk Satellite, the mixer patch, the volume buttons and the light sensor. The on-screen keyboard only showed after a restart, which 0.2.2 now does. The identity check still only knows the 8". |
| Smart Display M10, Japan (SD-X501F) | blueberry board, amber screen | Not tried with this tool ([#4](https://github.com/TRusselo/lenovo-display-ha-kiosk/issues/4)). Another project read an EDL backup from a locked one. It has no speaker amplifier, so there's no speaker output. |
| Smart Display 7 (CD-17302F) | ivy | Separate XDA thread and firmware. Nothing here has been checked against it. |

**`--force-model` is for the 10" models only.** The 7" uses different firmware, and the EDL loader and the system
image this tool uses aren't for it: don't run the tool on a 7".

**If you try a 10"**, run with `--force-model` at your own risk, keep the backup, and please open an issue with:
- the output of `fastboot getvar all` and `adb shell wm size`
- the button GPIOs, which you can find by watching `/sys/class/gpio/gpio*/value` while pressing each button
- what worked and what didn't
