#!/system/bin/sh
# ==============================================================
# Elektronic Android — Управление записью микрофона (Оптимизированный)
# ==============================================================

ACTION="$1"
OUTPUT_FILE="${2:-/data/local/tmp/giga_rec.wav}"
PID_FILE="/data/local/tmp/giga_recorder.pid"

MODDIR="$(cd "$(dirname "$0")/.." && pwd)"

# Загрузка конфигурации
if [ -f "${MODDIR}/giga.conf" ]; then
    . "${MODDIR}/giga.conf"
fi

# Поиск доступного инструмента записи
find_recorder() {
    if [ "${RECORDING_METHOD:-auto}" != "tinycap" ] && [ -f "${MODDIR}/tools/recorder.dex" ]; then
        echo "dex"
    elif [ -x "/system/bin/tinycap" ]; then
        echo "/system/bin/tinycap"
    elif [ -x "/vendor/bin/tinycap" ]; then
        echo "/vendor/bin/tinycap"
    elif [ -x "/system/xbin/tinycap" ]; then
        echo "/system/xbin/tinycap"
    elif [ -x "${MODDIR}/bin/tinycap" ]; then
        echo "${MODDIR}/bin/tinycap"
    elif [ -f "${MODDIR}/tools/recorder.dex" ]; then
        echo "dex"
    elif command -v termux-microphone-record >/dev/null 2>&1; then
        echo "termux"
    else
        echo "none"
    fi
}

start_record() {
    rm -f "$OUTPUT_FILE" "$PID_FILE"
    RECORDER=$(find_recorder)

    case "$RECORDER" in
        *"tinycap"*)
            # Запись 16 кГц, 16 бит, 1 канал (моно)
            "$RECORDER" "$OUTPUT_FILE" -r 16000 -b 16 -c 1 >/dev/null 2>&1 &
            echo $! > "$PID_FILE"
            ;;
        "dex")
            CLASSPATH="${MODDIR}/tools/recorder.dex" app_process / com.pisar.Recorder "$OUTPUT_FILE" >/dev/null 2>&1 &
            echo $! > "$PID_FILE"
            ;;
        "termux")
            termux-microphone-record -f "$OUTPUT_FILE" -l 0 -e wav -r 16000 >/dev/null 2>&1 &
            echo $! > "$PID_FILE"
            ;;
        *)
            if command -v python3 >/dev/null 2>&1 && [ -f "${MODDIR}/tools/record.py" ]; then
                python3 "${MODDIR}/tools/record.py" "$OUTPUT_FILE" >/dev/null 2>&1 &
                echo $! > "$PID_FILE"
            else
                echo "[-] Ошибка: не найден инструмент записи звука (tinycap / recorder.dex)." >&2
                return 1
            fi
            ;;
    esac
}

stop_record() {
    if [ -f "$PID_FILE" ]; then
        REC_PID=$(cat "$PID_FILE")
        if [ -n "$REC_PID" ] && kill -0 "$REC_PID" 2>/dev/null; then
            # Мягкое завершение SIGINT для корректного сохранения заголовка WAV через ShutdownHook
            kill -INT "$REC_PID" 2>/dev/null || kill -TERM "$REC_PID" 2>/dev/null
            count=0
            # Быстрый опрос каждые 15 мс вместо грубого sleep 0.1
            while kill -0 "$REC_PID" 2>/dev/null && [ $count -lt 8 ]; do
                usleep 15000 2>/dev/null || sleep 0.02
                count=$((count + 1))
            done
            if kill -0 "$REC_PID" 2>/dev/null; then
                kill -9 "$REC_PID" 2>/dev/null
            fi
        fi
        rm -f "$PID_FILE"
    fi
    if command -v termux-microphone-record >/dev/null 2>&1; then
        termux-microphone-record -q >/dev/null 2>&1 || true
    fi
}

case "$ACTION" in
    start)
        start_record
        ;;
    stop)
        stop_record
        ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
            echo "recording"
        else
            echo "idle"
        fi
        ;;
    *)
        echo "Использование: $0 {start|stop|status} [output_file]"
        exit 1
        ;;
esac
