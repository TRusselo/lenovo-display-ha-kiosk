#!/system/bin/sh
# Lenovo Smart Display: restart Kiosk Satellite once the light sensor exists.
#
# The VCNL 4200 light sensor is a dynamic sensor that sparrow.oem registers
# some time after boot. Kiosk Satellite starts earlier as the home launcher,
# finds no light sensor and never looks again, so adaptive brightness stays
# dead until the app restarts. Started by ks-boot-fix.rc after boot.

PKG=me.jxl.kiosk_satellite
TAG=ks-boot-fix

log -t $TAG "waiting for the light sensor"
i=0
until dumpsys sensorservice 2>/dev/null | grep -q "VCNL 4200 Ambient Light Sensor |"; do
  i=$((i + 1))
  if [ $i -gt 150 ]; then
    log -t $TAG "light sensor never appeared, giving up"
    exit 1
  fi
  sleep 2
done
log -t $TAG "light sensor registered after about $((i * 2)) s"

# Let Kiosk Satellite finish its own start-up before restarting it
sleep 15
am force-stop $PKG
sleep 2
am start -a android.intent.action.MAIN -c android.intent.category.HOME >/dev/null 2>&1
log -t $TAG "restarted $PKG"
