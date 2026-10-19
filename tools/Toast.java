package com.pisar;

import android.os.Binder;
import android.os.IBinder;
import android.os.Process;
import java.lang.reflect.Method;

public class Toast {
    public static void show(String message) {
        try {
            // Если процесс запущен от root (uid 0), понижаем uid до 2000 (com.android.shell)
            if (Process.myUid() == 0) {
                try {
                    Method setUid = Process.class.getMethod("setUid", int.class);
                    setUid.invoke(null, 2000);
                } catch (Throwable ignored) {}
            }

            Class<?> smClass = Class.forName("android.os.ServiceManager");
            Method getService = smClass.getMethod("getService", String.class);
            IBinder b = (IBinder) getService.invoke(null, "notification");

            Class<?> stubClass = Class.forName("android.app.INotificationManager$Stub");
            Method asInterface = stubClass.getMethod("asInterface", IBinder.class);
            Object nm = asInterface.invoke(null, b);

            IBinder token = new Binder();

            // Android 11-15: enqueueTextToast
            for (Method m : nm.getClass().getMethods()) {
                if (m.getName().equals("enqueueTextToast")) {
                    Class<?>[] pTypes = m.getParameterTypes();
                    if (pTypes.length == 7) {
                        m.invoke(nm, "com.android.shell", token, message, 0, false, 0, null);
                        return;
                    } else if (pTypes.length == 5) {
                        m.invoke(nm, "com.android.shell", token, message, 0, 0);
                        return;
                    }
                }
            }
        } catch (Throwable e) {
            e.printStackTrace();
        }
    }

    public static void main(String[] args) {
        String msg = args.length > 0 ? args[0] : "Выполняю команду: тестовая команда";
        show(msg);
    }
}
