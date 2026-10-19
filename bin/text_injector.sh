#!/system/bin/sh
# ==============================================================
# Elektronic Android — Вставка распознанного текста в активное поле
# ==============================================================

TEXT="$1"
MODDIR="$(cd "$(dirname "$0")/.." && pwd)"

[ -z "$TEXT" ] && exit 0

# Загрузка конфигурации
if [ -f "${MODDIR}/giga.conf" ]; then
    . "${MODDIR}/giga.conf"
fi

set_clipboard() {
    STR="$1"
    # Метод 1: через собственный dex с поддержкой Android 10-15
    if [ -f "${MODDIR}/tools/recorder.dex" ]; then
        CLASSPATH="${MODDIR}/tools/recorder.dex" app_process / com.pisar.Clipboard "$STR" >/dev/null 2>&1 && return 0
    fi

    # Метод 2: cmd clipboard (если поддержан прошивкой)
    if cmd clipboard set-text "$STR" >/dev/null 2>&1; then
        return 0
    fi

    # Метод 3: через termux-clipboard-set
    if command -v termux-clipboard-set >/dev/null 2>&1; then
        echo -n "$STR" | termux-clipboard-set 2>/dev/null && return 0
    fi

    return 0
}

inject_text() {
    # Помещаем текст в буфер обмена
    set_clipboard "$TEXT"

    # Если включена автоматическая вставка
    if [ "${AUTO_PASTE:-1}" = "1" ]; then
        # Минимальная пауза для обновления системного буфера обмена Android
        usleep 30000 2>/dev/null || sleep 0.03

        # Отправляем событие вставки KEYCODE_PASTE (279)
        input keyevent 279 2>/dev/null || input keyevent --meta 113 50 2>/dev/null

        # Если включена отправка сообщения (нажатие Enter)
        if [ "${AUTO_ENTER:-0}" = "1" ]; then
            usleep 50000 2>/dev/null || sleep 0.05
            input keyevent 66 2>/dev/null # KEYCODE_ENTER
        fi
    fi
}

inject_text
