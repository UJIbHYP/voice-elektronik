#!/system/bin/sh
# ==============================================================
# Elektronic Android — Клиент распознавания речи (Оптимизированный)
# ==============================================================

AUDIO_FILE="$1"
MODDIR="$(cd "$(dirname "$0")/.." && pwd)"

[ ! -f "$AUDIO_FILE" ] && exit 1

# Очистка предыдущей закэшированной команды
rm -f /data/local/tmp/giga_last_cmd

# Загрузка конфигурации
if [ -f "${MODDIR}/giga.conf" ]; then
    . "${MODDIR}/giga.conf"
fi

HOST="${SERVER_HOST:-127.0.0.1}"
PORT="${SERVER_PORT:-8737}"
MODE="${STT_MODE:-local_server}"

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

export PATH="/data/data/com.termux/files/usr/bin:$PATH:/system/bin:/system/xbin"

transcribe_http() {
    URL="http://${HOST}:${PORT}/v1/audio/transcriptions"
    RESP=""

    # Прямая передача WAV без MIME multipart оверхеда экономит до 400-500 мс
    if [ -x "/data/data/com.termux/files/usr/bin/curl" ]; then
        RESP=$(/data/data/com.termux/files/usr/bin/curl -s -m 10 -X POST -H "Content-Type: audio/wav" --data-binary "@${AUDIO_FILE}" "$URL" 2>/dev/null)
    elif command -v curl >/dev/null 2>&1; then
        RESP=$(curl -s -m 10 -X POST -H "Content-Type: audio/wav" --data-binary "@${AUDIO_FILE}" "$URL" 2>/dev/null)
    elif command -v wget >/dev/null 2>&1; then
        RESP=$(wget -q -O - --post-file="${AUDIO_FILE}" --header="Content-Type: audio/wav" "$URL" 2>/dev/null)
    else
        PY=$(find_python)
        RESP=$($PY -c "
import urllib.request
with open('${AUDIO_FILE}', 'rb') as f:
    data = f.read()
req = urllib.request.Request('${URL}', data=data, headers={'Content-Type': 'audio/wav'})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        print(r.read().decode())
except Exception:
    pass
" 2>/dev/null)
    fi

    # Быстрое извлечение текста и команды через awk в один проход
    if [ -n "$RESP" ]; then
        echo "$RESP" | awk -F'"' '
        {
            for (i = 1; i <= NF; i++) {
                if ($i == "text") { text = $(i+2) }
                if ($i == "command") {
                    if ($(i+2) != "" && $(i+1) ~ /:/) {
                        cmd = $(i+2)
                    }
                }
            }
        }
        END {
            if (cmd != "") {
                print cmd > "/data/local/tmp/giga_last_cmd"
            }
            if (text != "") {
                print text
            }
        }
        '
    fi
}

transcribe_cli() {
    PY=$(find_python)
    PISAR_SCRIPT="${MODDIR}/server/pisar.py"
    if [ -f "$PISAR_SCRIPT" ]; then
        PISAR_MODEL_DIR="${MODEL_DIR:-${MODDIR}/model}" $PY "$PISAR_SCRIPT" "$AUDIO_FILE" 2>/dev/null
    fi
}

case "$MODE" in
    local_server|remote)
        RESULT=$(transcribe_http)
        if [ -z "$RESULT" ]; then
            # Резервный вызов CLI если локальный сервер ещё не ответил
            RESULT=$(transcribe_cli)
        fi
        echo "$RESULT"
        ;;
    local_cli)
        transcribe_cli
        ;;
    *)
        transcribe_http
        ;;
esac
