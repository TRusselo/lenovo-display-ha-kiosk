# Linux, step by step

For x86-64 PCs. It takes **20 to 30 minutes**, most of it waiting. On other CPUs, use the
[Python method](PYTHON.md).

## 1. What you need

- A **Lenovo Smart Display 8**: the label on the back says **SD-8501F**. Other models aren't supported.
- A **USB data cable**. Many cheap cables only charge. One that has moved photos off a phone is a good sign.
- About **12 GB free**.

## 2. Download and unzip

1. From [Releases](../../../releases), download **`lhk-linux-x86_64.zip`**.
2. Unzip it into a folder of its own: right-click it and choose **Extract Here**, or run `unzip
   lhk-linux-x86_64.zip -d lhk-kiosk`.

The folder holds a folder called `lhk` (the program) and these instructions. Your downloads and the display's
backup are saved in this folder too.

## 3. Open a terminal in the folder

Right-click inside the folder and choose **Open Terminal Here** (the wording varies by desktop). Or open a
terminal and `cd` into the folder.

## 4. Allow USB access (once)

Linux needs a rule that lets you use the display over USB without root. Copy these lines into the terminal;
they ask for your password:

```bash
sudo groupadd -f plugdev
sudo cp lhk/_internal/assets/linux/51-lhk.rules /etc/udev/rules.d/
sudo cp lhk/_internal/assets/linux/lhk-no-qcserial.conf /etc/modprobe.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo modprobe -r qcserial
```

If the display is already connected, unplug its USB and plug it back in.

On a normal desktop that's all. **Over SSH, or on a distro without systemd (Void, Alpine, Gentoo with
OpenRC)**, also run this, then log out and back in:

```bash
sudo usermod -aG plugdev $USER
```

If the tool ever says this account isn't allowed to use the display, this step is the fix. See
[drivers.md](drivers.md) for what each line does.

## 5. Run it

```bash
./lhk/lhk setup
```

## 6. Follow the prompts

- When it says **DO THIS ON THE DISPLAY**, it tells you which buttons to hold. Unplug the display's power, hold
  the buttons, plug the power back in, and let go after 3 to 5 seconds. The screen stays blank. If you see the
  Lenovo logo, it's starting normally: unplug it and try again.
- When it asks you to do something on the display (Wi-Fi, time zone, Kiosk Satellite's setup), do it there.
  Kiosk Satellite's setup also works in a browser: the tool shows the address.
- When it says **NOT DONE YET**, come back to the terminal and press **Enter**.
- If it stops for any reason, run `./lhk/lhk setup` again. It carries on where it left off.

## 7. Keep your backup

At the end the tool names your backup file, in the `backup` folder. Copy it somewhere safe, off this computer
if you can, and keep it private: it's the only way back to the display's original software.

Afterwards you can remove the two system files:

```bash
sudo rm /etc/udev/rules.d/51-lhk.rules /etc/modprobe.d/lhk-no-qcserial.conf
```
