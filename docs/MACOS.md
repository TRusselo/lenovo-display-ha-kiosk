# macOS, step by step

For Macs with Apple silicon (M1 and later). It takes **20 to 30 minutes**, most of it waiting.

> [!NOTE]
> One tester has converted a display on a Mac, by [running from source](PYTHON.md). The ready-made program
> below hasn't converted one yet: for that tester, macOS blocked it with security warnings. If that happens to
> you, see [If macOS blocks the program](#if-macos-blocks-the-program). Either way, please say how it went in the
> [Home Assistant Community thread](https://community.home-assistant.io/t/lenovo-smart-display-8-as-a-de-googled-ha-dashboard-running-kiosk-satellite-w-assist-working-testers-wanted/1033810) or the [XDA thread](https://xdaforums.com/t/lenovo-smart-display-8-home-assistant-kiosk-satellite.4808181/) (no GitHub account needed), or [open an issue](../../../issues).

On an **Intel Mac**, there's no ready-made program: use the [Python method](PYTHON.md) instead.

New to this? [Words you'll see](../README.md#words-youll-see) explains terminal, EDL mode, fastboot mode and
verified boot in a few lines.

## 1. What you need

- A **Lenovo Smart Display 8**: the label on the back says **SD-8501F**. Other models aren't supported.
- A **USB-A to USB-C data cable**, plugged into a USB-A hub or adapter on the Mac. With a USB-C to USB-C
  cable, the display may not show up once its new system starts. Many cheap cables only charge. One that has
  moved photos off a phone is a good sign.
- About **12 GB free** on the Mac.
- **libusb**, for the backup. Install [Homebrew](https://brew.sh), then run `brew install libusb`. The tool
  stops and says so if it's missing.

## 2. Download and unzip

1. Download **[lhk-macos-arm64.zip](https://github.com/TRusselo/lenovo-display-ha-kiosk/releases/latest/download/lhk-macos-arm64.zip)**. That link always gets the newest version.
2. Double-click the zip. It unzips into a folder next to it. You can move that folder anywhere, for example
   into your home folder.

   Safari may have unzipped it already: if your Downloads folder has a folder called `lhk-macos-arm64` instead of
   a zip, use that folder.

The folder holds a folder called `lhk` (the program) and these instructions. Your downloads and the display's
backup are saved in this folder too.

## 3. Open Terminal in the folder

1. Open **Terminal** (in Applications > Utilities, or search for it with Spotlight).
2. Type `cd ` (with a space after it), then drag the unzipped folder from Finder into the Terminal window, and
   press **Return**.

## 4. Run it

Copy these two lines into Terminal and press **Return**:

```bash
xattr -dr com.apple.quarantine lhk
./lhk/lhk setup
```

The first line stops macOS from blocking the program because it was downloaded and isn't signed by Apple. You
only need it once. Run it from the folder you unzipped, the one that has the `lhk` folder in it: it clears the
block from `lhk` and everything inside it.

Don't double-click anything inside the `lhk` folder in Finder. The program runs in Terminal.

## 5. Follow the prompts

- When it says **DO THIS ON THE DISPLAY**, it tells you which buttons to hold. Unplug the display's power, hold
  the buttons, plug the power back in, and let go after 3 to 5 seconds. The screen stays blank. If you see the
  Lenovo logo, it's starting normally: unplug it and try again.
- When it asks you to do something on the display (Wi-Fi, time zone, Kiosk Satellite's setup), do it there.
  Kiosk Satellite's setup also works in a browser: the tool shows the address.
- When it says **NOT DONE YET**, come back to Terminal and press **Return**.
- If it stops for any reason, run `./lhk/lhk setup` again. It carries on where it left off.

## 6. Keep your backup

At the end the tool names your backup file, in the `backup` folder. Copy it somewhere safe, off this Mac if you
can, and keep it private: it's the only way back to the display's original software.

## If macOS blocks the program

macOS blocks programs from the internet that Apple hasn't checked. This one isn't checked: that needs a paid
Apple developer account. The block is a message that macOS can't verify `lhk`, or that it may be
malware. The buttons differ between macOS versions.

1. Click anything except **Move to Trash** (or **Move to Bin**).
2. In Terminal, in the folder you unzipped, run the `xattr` line from step 4 again, then `./lhk/lhk setup`.
   Check you're in the right folder first: `ls` should list `lhk`.
3. If it's still blocked, open **System Settings > Privacy & Security**, scroll down to the message about
   `lhk`, and click **Open Anyway**. macOS may ask again for some of the files inside `lhk`: the `xattr` line
   is quicker than allowing each one.
4. If it still says `lhk` **is damaged**, or Terminal prints `killed: 9`, go to the next point, and please
   report the exact message: it tells us what to fix.
5. If none of that works, [run it from source](PYTHON.md) instead. It's the same tool, run with Python, and
   macOS doesn't block it. That's how the first Mac conversion was done.

## Questions or problems?

Ask in the [Home Assistant Community thread](https://community.home-assistant.io/t/lenovo-smart-display-8-as-a-de-googled-ha-dashboard-running-kiosk-satellite-w-assist-working-testers-wanted/1033810) or the [XDA thread](https://xdaforums.com/t/lenovo-smart-display-8-home-assistant-kiosk-satellite.4808181/) (no GitHub account needed), or [open an issue](../../../issues). Say how far it got, and copy the last few lines the tool printed.
