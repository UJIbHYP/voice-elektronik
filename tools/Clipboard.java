package com.pisar;

import android.content.ClipData;
import android.os.IBinder;
import java.lang.reflect.Method;

public class Clipboard {
    public static void main(String[] args) {
        if (args.length == 0) return;
        String text = args[0];
        try {
            Class<?> smClass = Class.forName("android.os.ServiceManager");
            Method getService = smClass.getMethod("getService", String.class);
            IBinder b = (IBinder) getService.invoke(null, "clipboard");

            Class<?> stubClass = Class.forName("android.content.IClipboard$Stub");
            Method asInterface = stubClass.getMethod("asInterface", IBinder.class);
            Object clipboard = asInterface.invoke(null, b);

            ClipData clip = ClipData.newPlainText("text", text);

            for (Method m : clipboard.getClass().getMethods()) {
                if (m.getName().equals("setPrimaryClip")) {
                    Class<?>[] pts = m.getParameterTypes();
                    if (pts.length == 5) { // Android 14+ / 15
                        m.invoke(clipboard, clip, "com.android.shell", null, 0, 0);
                        return;
                    } else if (pts.length == 4) { // Android 13
                        m.invoke(clipboard, clip, "com.android.shell", null, 0);
                        return;
                    } else if (pts.length == 3) { // Android 10-12
                        m.invoke(clipboard, clip, "com.android.shell", 0);
                        return;
                    } else if (pts.length == 2) {
                        m.invoke(clipboard, clip, "com.android.shell");
                        return;
                    }
                }
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
