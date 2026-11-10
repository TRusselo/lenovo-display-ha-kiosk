# USB drivers and permissions

The display shows up as two different USB devices, depending on its mode:

| Mode | USB ID | Used for |
|---|---|---|
| Fastboot | `18d1:d00d` | Unlocking and flashing |
| EDL (Qualcomm 9008) | `05c6:9008` | The stock backup and restore |

Once the display is converted, Android itself also appears over adb.

## Windows

**Fastboot and adb:** install Google's USB driver.
1. Download the [Google USB Driver](https://developer.android.com/studio/run/win-usb) and unzip it.
2. Put the display in fastboot (the tool tells you how).
3. Open **Device Manager**, right-click the device with a warning icon, choose **Update driver → Browse my
   computer**, and pick the unzipped folder.

**EDL (backup and restore only):** the tool talks to the display directly. It brings its own libusb, but
Windows also needs the **WinUSB** driver attached to the display.
1. Download [Zadig](https://zadig.akeo.ie/).
2. Put the display in EDL (the tool tells you how; the screen stays blank).
3. In Zadig, choose **Options → List All Devices**, then pick **QUSB__BULK** (USB ID `05C6 9008`).
4. Choose **WinUSB** and click **Replace Driver**.

Holding the buttons for about 15 seconds resets the display, so let go 3 to 5 seconds after plugging in
the power. Then you have time.

## Linux

One udev rule covers EDL, fastboot and adb, and one setting stops the `qcserial` driver claiming the display in
EDL (otherwise `edl` fails with `Resource busy`). One-time changes, which need `sudo`:

```bash
sudo groupadd -f plugdev
sudo cp assets/linux/51-lhk.rules /etc/udev/rules.d/
sudo cp assets/linux/lhk-no-qcserial.conf /etc/modprobe.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
sudo modprobe -r qcserial
```

Then unplug the display's USB and plug it back in, if it was connected.

The rule gives access to whoever is logged in at the computer (`uaccess`, on systemd desktops), and to the
`plugdev` group. Over SSH or without systemd-logind, add yourself to the group and log out and back in:
`sudo usermod -aG plugdev $USER`. When access is missing, the tool says so and points here.

You can remove both files afterwards:

```bash
sudo rm /etc/udev/rules.d/51-lhk.rules /etc/modprobe.d/lhk-no-qcserial.conf
```

## macOS

Nothing to install: the tool brings its own copy of libusb for EDL. macOS support is untested on a real display
so far.
