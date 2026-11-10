# Windows, step by step

For Windows 10 or 11 on an Intel or AMD PC. It takes **20 to 30 minutes**, most of it waiting.

> [!NOTE]
> Tested end to end on Linux only. The Windows program hasn't converted a real display yet. If you try it,
> please [open an issue](../../../issues) to say how it went, whether it worked or not.

## 1. What you need

- A **Lenovo Smart Display 8**: the label on the back says **SD-8501F**. Other models aren't supported.
- A **USB data cable**. Many cheap cables only charge. One that has moved photos off a phone is a good sign.
- About **12 GB free** on the PC.

## 2. Download and unzip

1. From [Releases](../../../releases), download **`lhk-windows-x86_64.zip`**.
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
