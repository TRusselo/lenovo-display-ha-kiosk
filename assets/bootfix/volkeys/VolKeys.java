package ks;

import android.hardware.input.InputManager;
import android.os.SystemClock;
import android.view.InputDevice;
import android.view.InputEvent;
import android.view.KeyCharacterMap;
import android.view.KeyEvent;
import java.io.RandomAccessFile;
import java.lang.reflect.Method;

/**
 * Lenovo Smart Display: turn the volume button GPIOs into volume key presses.
 *
 * The buttons are read by sparrow.oem, which hands them to a Google listener
 * that no longer runs. This watches the two pins and injects KEYCODE_VOLUME_UP
 * and KEYCODE_VOLUME_DOWN through InputManager, the same path as
 * "input keyevent", but in one long-running process, so there is no Java
 * start-up delay per press. Run with:
 *   CLASSPATH=/system/framework/ks-volkeys.jar app_process /system/bin ks.VolKeys
 */
public final class VolKeys {
    private static final String UP_PIN = "/sys/class/gpio/gpio85/value";     // 1 while pressed
    private static final String DOWN_PIN = "/sys/class/gpio/gpio1019/value"; // 1 while pressed
    private static final int POLL_MS = 30;
    // Music volume has 100 steps here, so one key is 1%; 5 per press = 5%,
    // matching Kiosk Satellite's volume step.
    private static final int KEYS_PER_PRESS = 5;
    private static final int REPEAT_DELAY_MS = 500;
    private static final int REPEAT_EVERY_MS = 300;

    private static InputManager inputManager;
    private static Method injectInputEvent;

    public static void main(String[] args) throws Exception {
        inputManager = (InputManager) InputManager.class.getMethod("getInstance").invoke(null);
        injectInputEvent = InputManager.class.getMethod("injectInputEvent", InputEvent.class, int.class);
        System.out.println("ks-volkeys: watching " + UP_PIN + " and " + DOWN_PIN);

        RandomAccessFile up = new RandomAccessFile(UP_PIN, "r");
        RandomAccessFile down = new RandomAccessFile(DOWN_PIN, "r");
        int held = 0;
        long heldSince = 0;
        long lastRepeat = 0;
        while (true) {
            int key = 0;
            if (pressed(up)) {
                key = KeyEvent.KEYCODE_VOLUME_UP;
            } else if (pressed(down)) {
                key = KeyEvent.KEYCODE_VOLUME_DOWN;
            }
            long now = SystemClock.uptimeMillis();
            if (key != 0 && key != held) {
                press(key);
                heldSince = now;
                lastRepeat = now;
            } else if (key != 0 && now - heldSince >= REPEAT_DELAY_MS && now - lastRepeat >= REPEAT_EVERY_MS) {
                press(key);
                lastRepeat = now;
            }
            held = key;
            SystemClock.sleep(POLL_MS);
        }
    }

    private static boolean pressed(RandomAccessFile pin) throws Exception {
        pin.seek(0);
        return pin.read() == '1';
    }

    private static void press(int key) throws Exception {
        for (int i = 0; i < KEYS_PER_PRESS; i++) {
            long t = SystemClock.uptimeMillis();
            inject(new KeyEvent(t, t, KeyEvent.ACTION_DOWN, key, 0, 0,
                    KeyCharacterMap.VIRTUAL_KEYBOARD, 0, 0, InputDevice.SOURCE_KEYBOARD));
            inject(new KeyEvent(t, t, KeyEvent.ACTION_UP, key, 0, 0,
                    KeyCharacterMap.VIRTUAL_KEYBOARD, 0, 0, InputDevice.SOURCE_KEYBOARD));
        }
    }

    private static void inject(KeyEvent event) throws Exception {
        // 0 = InputManager.INJECT_INPUT_EVENT_MODE_ASYNC
        injectInputEvent.invoke(inputManager, event, 0);
    }
}
