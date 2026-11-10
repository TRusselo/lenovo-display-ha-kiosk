# PyInstaller spec: one-folder standalone build of lhk for the current OS.
# Bundles our own files only. edl (GPL-3.0), firmware, unlock credentials and
# Kiosk Satellite are downloaded at run time and never bundled.
# Build: pyinstaller lhk.spec   (ks-volkeys.jar must be at the repo root first)
import os

from PyInstaller.utils.hooks import collect_dynamic_libs

datas = [
    ("manifest.json", "."),
    ("assets/bootfix", "assets/bootfix"),
    ("assets/tzdata", "assets/tzdata"),
    ("assets/linux", "assets/linux"),
    ("assets/degoogle.txt", "assets"),
    ("LICENSE", "."),
]
if os.path.exists("ks-volkeys.jar"):
    datas.append(("ks-volkeys.jar", "."))

a = Analysis(
    ["lhk/__main__.py"],
    pathex=["."],
    datas=datas,
    # libusb from the libusb-package wheel (LGPL-2.1, loaded dynamically), so EDL
    # detection works on Windows and macOS without installing anything.
    binaries=collect_dynamic_libs("libusb_package"),
    hiddenimports=["libusb_package", "usb.backend.libusb1", "usb.backend.libusb0", "usb.backend.openusb"],
    excludes=["tkinter", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lhk", console=True)
coll = COLLECT(exe, a.binaries, a.datas, name="lhk")
