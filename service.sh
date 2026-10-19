#!/system/bin/sh
# ==============================================================
# Elektronic Android — Magisk Boot Service
# ==============================================================

MODDIR="${0%/*}"

# Ожидание завершения загрузки Android
while [ "$(getprop sys.boot_completed)" != "1" ]; do
    sleep 2
done

# Пауза для полной инициализации подсистем ввода (input) и аудио
sleep 5

# Обеспечение прав исполнения на все исполняемые файлы
chmod -R 755 "${MODDIR}/bin" "${MODDIR}/server" 2>/dev/null || true

# Запуск главного демона Elektronic
"${MODDIR}/bin/giga_daemon.sh" >/dev/null 2>&1 &
