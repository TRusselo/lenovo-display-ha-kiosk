# Windows, step by step

For Windows 10 or 11 on an Intel or AMD PC. It takes **20 to 30 minutes**, most of it waiting.

> [!NOTE]
> Tested end to end on Linux, and on a Mac running from source. The Windows program hasn't converted a real
> display yet. If you try it,
> please say how it went, whether it worked or not, in the
> [Home Assistant Community thread](https://community.home-assistant.io/t/lenovo-smart-display-8-as-a-de-googled-ha-dashboard-running-kiosk-satellite-w-assist-working-testers-wanted/1033810) or the [XDA thread](https://xdaforums.com/t/lenovo-smart-display-8-home-assistant-kiosk-satellite.4808181/) (no GitHub account needed), or [open an issue](../../../issues).

New to this? [Words you'll see](../README.md#words-youll-see) explains terminal, EDL mode, fastboot mode and
verified boot in a few lines.

## 1. What you need

- A **Lenovo Smart Display 8**: the label on the back says **SD-8501F**. Other models aren't supported.
- A **USB data cable**. Many cheap cables only charge. One that has moved photos off a phone is a good sign.
  If the display doesn't show up on USB, see [the guide](GUIDE.md#if-the-display-doesnt-show-up-on-usb).
- About **12 GB free** on the PC.

## 2. Download and unzip

1. Download **[lhk-windows-x86_64.zip](https://github.com/TRusselo/lenovo-display-ha-kiosk/releases/latest/download/lhk-windows-x86_64.zip)**. That link always gets the newest version.
2. Right-click the zip and choose **Extract All**. Pick a folder **without spaces** in its name, for example
   `C:\lhk`, and click **Extract**.

The folder now holds a folder called `lhk` (the program) and these instructions. Your downloads and the
display's backup are saved in this folder too.

## 3. Install the USB drivers (once)

Windows needs two drivers to talk to the display. Follow the **Windows** part of [drivers.md](drivers.md):
- Google's USB driver, for fastboot and adb;
- the WinUSB driver, installed with Zadig, for the backup.

You can do each one when the tool first asks for that mode: it tells you which mode the display is in.

## 4. Open a command window in the folder

1. Open the folder in File Explorer.
2. Click the address bar at the top, type `cmd` and press **Enter**.

A black window opens, already in the right folder.

## 5. Run it

Type this and press **Enter**:

```bat
lhk\lhk setup
```

(In PowerShell or Windows Terminal instead, type `.\lhk\lhk setup`.)

## 6. Follow the prompts

- When it says **DO THIS ON THE DISPLAY**, it tells you which buttons to hold. Unplug the display's power, hold
  the buttons, plug the power back in, and let go after 3 to 5 seconds. The screen stays blank. If you see the
  Lenovo logo, it's starting normally: unplug it and try again.
- When it asks you to do something on the display (Wi-Fi, time zone, Kiosk Satellite's setup), do it there.
  Kiosk Satellite's setup also works in a browser: the tool shows the address.
- When it says **NOT DONE YET**, come back to the window and press **Enter**.
- If it stops for any reason, run the same command again. It carries on where it left off.

## 7. Keep your backup

At the end the tool names your backup file, in the `backup` folder. Copy it somewhere safe, off this PC if you
can, and keep it private: it's the only way back to the display's original software.

## If antivirus blocks the program

The program isn't signed, and antivirus software sometimes flags programs built this way (with PyInstaller)
even when they're harmless. If `lhk` disappears, or Windows says it found a threat in it:

1. Check the zip is the real one. In the folder with the zip, run:
   ```bat
   certutil -hashfile lhk-windows-x86_64.zip SHA256
   ```
   Compare the result with the `lhk-windows-x86_64.zip` line in `SHA256SUMS` on the
   [release page](../../../releases/latest). If they don't match, delete the zip and download it again.
2. If they match, open **Windows Security > Virus & threat protection > Protection history**, find the entry for
   `lhk`, and choose **Allow** or **Restore**.
3. Or [run it from source](PYTHON.md) instead: the same tool, run with Python.

## Questions or problems?

Ask in the [Home Assistant Community thread](https://community.home-assistant.io/t/lenovo-smart-display-8-as-a-de-googled-ha-dashboard-running-kiosk-satellite-w-assist-working-testers-wanted/1033810) or the [XDA thread](https://xdaforums.com/t/lenovo-smart-display-8-home-assistant-kiosk-satellite.4808181/) (no GitHub account needed), or [open an issue](../../../issues). Say how far it got, and copy the last few lines the tool printed.
