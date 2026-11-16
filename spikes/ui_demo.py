"""Shows the setup screen with pretend steps: no display, no downloads.
Run: python spikes/ui_demo.py  (add --fast to skip the pauses)"""
import sys
import time

sys.path.insert(0, ".")
from lhk import plan  # noqa: E402
from lhk.ui import UI  # noqa: E402

fast = "--fast" in sys.argv
pause = (lambda s: None) if fast else time.sleep
ui = UI()
titles = [s.title for s in plan.setup_steps()]
done = set()

ui.intro("Setup takes 20 to 30 minutes and needs 12 GB free: about 1 GB of downloads the first time, the "
         "unpacked firmware, and a backup of the display (about 3.5 GB). The tool tells you each time it "
         "needs you at the display.")
ui.screen(titles, 1, done)
with ui.busy("Checking free space"):
    pause(1)
done.add(1)

ui.screen(titles, 2, done)
with ui.busy("Downloading OIMK.211005.001-userdebug-blueberry-FRW.7z (704 MB)") as job:
    for mb in range(0, 705, 64):
        job.note(f"{mb} of 704 MB, {mb * 100 // 704}%")
        pause(0.4)
with ui.busy("Downloading amber_bluebbery_prog_emmc_firehose_8953_ddr.zip (300 KB)"):
    pause(0.5)
done.add(2)

ui.screen(titles, 3, done)
ui.physical("Unplug the display's power. Hold VOLUME UP and VOLUME DOWN together, plug the power back in, "
            "and let go after 3 to 5 seconds. The screen stays blank in this mode.")
ui.status("none")
pause(1.5)
ui.status("EDL")
ui.say("Found it. Let go of the buttons if you're still holding them.")
with ui.busy("Backing up the display") as job:
    for i, name in enumerate(["vbmeta_a", "boot_a", "system_a", "vendor_a", "oem_a"] * 11, 1):
        job.note(f"{i} of 55: {name}")
        pause(0.08)
    job.done("Backed up 55 partitions")
with ui.busy("Packing the backup into one file, kiosk2.zip"):
    pause(1)
ui.keep("The backup is also saved as one file: /home/someone/lhk-workdir/lenovo-display/backup/kiosk2.zip. "
        "Copy it somewhere safe and keep it private.")
done.add(3)

ui.screen(titles, 6, done | {4, 5})
with ui.busy("Waiting for the new system's first start") as job:
    pause(2)
    job.pause("Not on USB yet")
ui.physical("The display hasn't shown up over USB. Unplug the USB cable from the display, count to 3, and "
            "plug it back in. Leave the power plugged in. The four dots can keep spinning even when it's ready.")
ui.ask("Press Enter to try again, or type stop: ")
with ui.busy("Waiting for the display on USB"):
    pause(1)
with ui.busy("Waiting for the new system's first start"):
    pause(1.5)
done |= {4, 5, 6, 7}

ui.screen(titles, 8, done)
ui.physical("The Android Things settings are open:\n"
            "  1. Menu (☰) > System > Date & time: pick your time zone. If yours isn't in the "
            "list, pick any: you can type the right one here afterwards.\n"
            "  2. Networks: pick your Wi-Fi and type its password on the on-screen keyboard.\n"
            "Don't press Check for update or Factory data reset on that page.")
pause(1.5)
ui.say("Wi-Fi connected.")
ui.ask("The display's time zone is GMT. If your zone wasn't in the list, type its name (for example "
       "America/Edmonton), or press Enter to keep it: ")
ui.keep("Time zone set to America/Edmonton. It takes effect when the display restarts, which this tool does "
        "near the end. Don't pick a zone in the list again, or it replaces this one.")
done.add(8)

ui.screen(titles, 14, done | set(range(9, 14)))
ui.alert("NOT DONE YET! THIS TOOL NEEDS YOU TO PRESS THE VOLUME BUTTONS ON THE DISPLAY.")
ui.physical("Press VOLUME UP on the display once.")
pause(1.5)
ui.physical("Press VOLUME DOWN on the display once.")
pause(1.5)
ui.say("Volume buttons work.")

ui.screen(titles, len(titles) + 1, set(range(1, len(titles) + 1)))
ui.ok("All done. The display is a Home Assistant kiosk.")
ui.alert("SAVE YOUR BACKUP: copy ~/lhk/backup/kiosk2.zip somewhere safe, off this computer if you can, and "
         "keep it private. It's the only way back to this display's stock software.")
ui.section("What's next", ["Change Kiosk Satellite's settings from a browser: http://10.0.0.50:2324",
                           "Turn the screen off, with tap to wake: docs/SCREEN.md",
                           "Fit more on the screen: docs/SIZE.md"])
