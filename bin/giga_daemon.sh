#!/system/bin/sh
# ==============================================================
# Elektronic Android — Главный управляющий демон (Оптимизированный)
# ==============================================================

MODDIR="$(cd "$(dirname "$0")/.." && pwd)"
PID_FILE="/data/local/tmp/giga_daemon.pid"
LOG_FILE="/data/local/tmp/giga_pisar.log"

# Загрузка конфигурации
if [ -f "${MODDIR}/giga.conf" ]; then
    . "${MODDIR}/giga.conf"
fi

log() {
    [ "${DEBUG_LOG:-1}" = "1" ] && echo "$(date '+%Y-%m-%d %H:%M:%S') [DAEMON] $1" >> "$LOG_FILE"
}

find_python() {
    if [ "${PYTHON_BIN:-auto}" != "auto" ] && [ -x "$PYTHON_BIN" ]; then
        echo "$PYTHON_BIN"
        return
    fi
    for p in "/data/data/com.termux/files/usr/bin/python3" \
             "/data/data/com.termux/files/usr/bin/python" \
             "/system/bin/python3" \
             "/system/xbin/python3" \
             "/data/adb/modules/python/bin/python3" \
             "$(command -v python3 2>/dev/null)"; do
        if [ -x "$p" ]; then
            echo "$p"
            return
        fi
    done
    echo "python3"
}

find_big_cores_mask() {
    mask=$(awk '
    {
        split(FILENAME, a, "/")
        sub(/cpu/, "", a[6])
        c = a[6] + 0
        freq = $1 + 0
        if (freq > max) {
            max = freq
            delete cores
            cores[0] = c
            n = 1
        } else if (freq == max) {
            cores[n++] = c
        }
    }
    END {
        m = 0
        for (i = 0; i < n; i++) {
            m += (2 ^ cores[i])
        }
        if (m > 0) printf "%x\n", m
    }
    ' /sys/devices/system/cpu/cpu*/cpufreq/cpuinfo_max_freq 2>/dev/null)
    echo "${mask:-c0}"
}

start_local_server() {
    PY=$(find_python)
    MODEL_PATH="${MODEL_DIR:-${MODDIR}/model}"
    PORT="${SERVER_PORT:-8737}"
    HOST="${SERVER_HOST:-127.0.0.1}"

    if [ ! -d "$MODEL_PATH" ] || [ ! -f "${MODEL_PATH}/v3_e2e_rnnt.yaml" ]; then
        log "Предупреждение: модель речи не найдена в $MODEL_PATH. Запустите install_model.sh."
        return 1
    fi

    THREADS="${INFERENCE_THREADS:-2}"
    MASK=$(find_big_cores_mask)
    log "Запуск локального сервера Elektronic (порт $PORT, потоков $THREADS, affinity: 0x$MASK)..."

    export PISAR_MODEL_DIR="$MODEL_PATH"
    if command -v taskset >/dev/null 2>&1 && [ -n "$MASK" ]; then
        taskset "$MASK" $PY "${MODDIR}/server/pisar.py" --serve --host "$HOST" --port "$PORT" --threads "$THREADS" >> "$LOG_FILE" 2>&1 &
    else
        $PY "${MODDIR}/server/pisar.py" --serve --host "$HOST" --port "$PORT" --threads "$THREADS" >> "$LOG_FILE" 2>&1 &
    fi
    SERVER_PID=$!
    echo "$SERVER_PID" > /data/local/tmp/giga_server.pid

    # Повышаем приоритет серверного процесса для минимальных задержек отклика
    renice -n -15 -p "$SERVER_PID" 2>/dev/null || true
    taskset -a -p "$MASK" "$SERVER_PID" 2>/dev/null || true
    log "Локальный сервер запущен с PID $SERVER_PID (приоритет -15, affinity mask: 0x$MASK)"
}

start_key_listener() {
    PY=$(find_python)
    INTERCEPTOR="${MODDIR}/bin/key_interceptor.py"
    if [ -f "$INTERCEPTOR" ]; then
        log "Запуск аппаратного перехватчика клавиши (EVIOCGRAB)..."
        $PY "$INTERCEPTOR" >> "$LOG_FILE" 2>&1 &
        LISTENER_PID=$!
    else
        log "Запуск стандартного слушателя key_listener.sh..."
        "${MODDIR}/bin/key_listener.sh" &
        LISTENER_PID=$!
    fi
    echo "$LISTENER_PID" > /data/local/tmp/giga_listener.pid
    log "Слушатель клавиш запущен с PID $LISTENER_PID"
}

stop_daemon() {
    log "Остановка демона Elektronic..."
    if [ -f /data/local/tmp/giga_server.pid ]; then
        kill "$(cat /data/local/tmp/giga_server.pid)" 2>/dev/null || true
        rm -f /data/local/tmp/giga_server.pid
    fi
    if [ -f /data/local/tmp/giga_listener.pid ]; then
        kill -TERM "$(cat /data/local/tmp/giga_listener.pid)" 2>/dev/null || true
        sleep 0.5
        kill -9 "$(cat /data/local/tmp/giga_listener.pid)" 2>/dev/null || true
        rm -f /data/local/tmp/giga_listener.pid
    fi
    rm -f "$PID_FILE"
    exit 0
}

trap stop_daemon TERM INT

echo $$ > "$PID_FILE"
log "=== Запуск Elektronic Daemon (версия 1.0.0, Аппаратный EVIOCGRAB) ==="

# Запуск локального сервера инференса, если выбран режим local_server
if [ "${STT_MODE:-local_server}" = "local_server" ]; then
    start_local_server
fi

# Запуск аппаратного слушателя клавиш
start_key_listener

# Супервизор
while true; do
    # Проверка работы слушателя клавиш
    if ! kill -0 "$LISTENER_PID" 2>/dev/null; then
        log "Внимание: слушатель клавиш завершился. Перезапуск..."
        start_key_listener
    fi

    # Проверка работы сервера инференса (если включен)
    if [ "${STT_MODE:-local_server}" = "local_server" ]; then
        if [ -f /data/local/tmp/giga_server.pid ]; then
            SPID=$(cat /data/local/tmp/giga_server.pid)
            if ! kill -0 "$SPID" 2>/dev/null; then
                log "Внимание: локальный сервер инференса упал. Перезапуск..."
                start_local_server
            fi
        fi
    fi

    sleep 10
done
