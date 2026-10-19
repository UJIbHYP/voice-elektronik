#!/system/bin/sh
# ==============================================================
# Elektronic Android — Парсер и исполнитель голосовых команд (Ускоренный)
# ==============================================================

RAW_TEXT="$1"
MODDIR="$(cd "$(dirname "$0")/.." && pwd)"

[ -z "$RAW_TEXT" ] && exit 1

# Загрузка конфигурации
if [ -f "${MODDIR}/giga.conf" ]; then
    . "${MODDIR}/giga.conf"
fi

[ "${COMMANDS_ENABLED:-1}" = "0" ] && exit 1

log() {
    [ "${DEBUG_LOG:-1}" = "1" ] && echo "$(date '+%Y-%m-%d %H:%M:%S') [COMMAND] $1" >> /data/local/tmp/giga_pisar.log
}

EXEC_SHELL=""

# 1. Сверхбыстрый путь: проверка команды, уже определенной сервером в памяти (0-1 мс)
if [ -s /data/local/tmp/giga_last_cmd ]; then
    EXEC_SHELL=$(cat /data/local/tmp/giga_last_cmd)
    rm -f /data/local/tmp/giga_last_cmd
fi

# 2. Резервный путь: если вызов из CLI или сервер не передал команду, вызываем единичный helper
if [ -z "$EXEC_SHELL" ]; then
    PY="${PYTHON_BIN}"
    if [ -z "$PY" ] || [ "$PY" = "auto" ] || [ ! -x "$PY" ]; then
        if [ -x "/data/data/com.termux/files/usr/bin/python3" ]; then
            PY="/data/data/com.termux/files/usr/bin/python3"
        else
            PY="python3"
        fi
    fi

    HELPER="${MODDIR}/server/commands_helper.py"
    if [ -f "$HELPER" ]; then
        PREFIX="${COMMAND_PREFIX:-андроид}"
        EXEC_SHELL=$("$PY" "$HELPER" "$RAW_TEXT" "$PREFIX" 2>/dev/null)
    fi
fi

if [ -n "$EXEC_SHELL" ]; then
    log "Выполнение команды: '$RAW_TEXT' -> '$EXEC_SHELL'"

    # Тоаст-уведомление пользователю о начале выполнения команды (в фоне, чтобы не задерживать выполнение)
    TOAST_DEX="${MODDIR}/tools/recorder.dex"
    if [ -f "$TOAST_DEX" ]; then
        (CLASSPATH="$TOAST_DEX" /system/bin/app_process / com.pisar.Toast "Выполняю команду: $RAW_TEXT" >/dev/null 2>&1) &
    fi

    # Короткая вибрация подтверждения исполнения команды
    if [ "${HAPTIC_FEEDBACK:-1}" = "1" ]; then
        cmd vibrator vibrate 40 2>/dev/null || true
    fi
    eval "$EXEC_SHELL"
    exit 0
else
    log "Команда не распознана: '$RAW_TEXT'"
    exit 1
fi
