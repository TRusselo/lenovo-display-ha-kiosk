#!/system/bin/sh
# Lenovo Smart Display: make the hardware volume buttons work.
#
# Launches the long-running VolKeys helper (bootfix/volkeys/VolKeys.java),
# which watches the two button GPIOs and injects volume keys through
# InputManager. Started by ks-boot-fix.rc in the dumpstate domain; that domain
# may not write /dev/input directly, but it may call InputManager.
export CLASSPATH=/system/framework/ks-volkeys.jar
exec app_process /system/bin ks.VolKeys
