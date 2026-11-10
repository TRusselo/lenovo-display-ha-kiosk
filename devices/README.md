# Other Lenovo Smart Displays

Only the **Smart Display 8 (SD-8501F, "amber")** is tested. The others share the platform (Snapdragon
msm8953/APQ8053, Android Things 8.1) but haven't been tried with this tool.

| Model | Codename | What's known |
|---|---|---|
| Smart Display 10 (SD-X701B) | blueberry | The userdebug dump this tool flashes *is* a 10" disk image, and the AVB unlock credentials include blueberry. The 10" has a 1920×1200 screen and its own partition layout. **Not covered:** the identity check (it only knows the 8"), the mixer patch (tuned on the 8"), the volume button GPIO numbers (`gpio85`/`gpio1019` on the 8") and the light sensor. |
| Smart Display 7 (CD-17302F) | ivy | Separate XDA thread and firmware. Nothing here has been checked against it. |

**`--force-model` is for the 10" only.** The 7" uses different firmware, and the EDL loader and the system
image this tool uses aren't for it: don't run the tool on a 7".

**If you try a 10"**, run with `--force-model` at your own risk, keep the backup, and please open an issue with:
- the output of `fastboot getvar all` and `adb shell wm size`
- the button GPIOs, which you can find by watching `/sys/class/gpio/gpio*/value` while pressing each button
- what worked and what didn't
