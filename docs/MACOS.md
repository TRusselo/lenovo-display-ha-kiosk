# macOS, step by step

For Macs with Apple silicon (M1 and later). It takes **20 to 30 minutes**, most of it waiting.

> [!NOTE]
> Untested on a real display so far. If you try it, please [open an issue](../../../issues) to say how it went,
> whether it worked or not.

On an **Intel Mac**, there's no ready-made program: use the [Python method](PYTHON.md) instead.

## 1. What you need

- A **Lenovo Smart Display 8**: the label on the back says **SD-8501F**. Other models aren't supported.
- A **USB data cable**. Many cheap cables only charge. One that has moved photos off a phone is a good sign.
- About **12 GB free** on the Mac.

Nothing else to install.

## 2. Download and unzip

1. From [Releases](../../../releases), download **`lhk-macos-arm64.zip`**.
2. Double-click the zip. It unzips into a folder next to it. You can move that folder anywhere, for example
   into your home folder.

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
only need it once.

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
