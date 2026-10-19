#!/system/bin/sh
# ==============================================================
# Elektronic Android — Слушатель удержания клавиши Volume Down
# ==============================================================

MODDIR="$(cd "$(dirname "$0")/.." && pwd)"

# Загрузка конфигурации
if [ -f "${MODDIR}/giga.conf" ]; then
    . "${MODDIR}/giga.conf"
fi

HEX_KEYCODE="0072" # 114 в hex = KEY_VOLUMEDOWN
if [ "${TRIGGER_KEYCODE:-114}" != "114" ]; then
    HEX_KEYCODE=$(printf "%04x" "$TRIGGER_KEYCODE")
fi

HOLD_TIME_MS="${TRIGGER_HOLD_MS:-300}"
# Вычисляем задержку в секундах один раз при старте, чтобы не запускать awk на каждое нажатие
HOLD_TIME_SEC=$(awk "BEGIN {print $HOLD_TIME_MS / 1000}")
[ -z "$HOLD_TIME_SEC" ] && HOLD_TIME_SEC="0.3"

REC_FILE="/data/local/tmp/giga_rec.wav"
LOG_FILE="/data/local/tmp/giga_pisar.log"

log() {
    [ "${DEBUG_LOG:-1}" = "1" ] && echo "$(date '+%Y-%m-%d %H:%M:%S') [LISTENER] $1" >> "$LOG_FILE"
}

vibrate() {
    [ "${HAPTIC_FEEDBACK:-1}" = "1" ] && cmd vibrator vibrate "$1" 2>/dev/null || true
}

log "Запуск перехвата клавиши: код ${HEX_KEYCODE} (Volume Down, порог ${HOLD_TIME_MS}мс)..."

HOLD_TIMER_PID=""

# Очистка предыдущих записей
rm -f "$REC_FILE"

# Запуск getevent для прослушивания событий ввода
getevent | while read -r line; do
    # Строка имеет формат: /dev/input/eventX: 0001 0072 00000001
    case "$line" in
        *": 0001 "*${HEX_KEYCODE}*" 00000001"*)
            # НАЖАТИЕ (DOWN)
            # Фоновый таймер: если клавиша удерживается дольше HOLD_TIME_MS, стартуем запись
            (
                sleep "$HOLD_TIME_SEC" 2>/dev/null || sleep 0.3
                touch /data/local/tmp/giga_hold_active
                vibrate 60
                "${MODDIR}/bin/audio_recorder.sh" start "$REC_FILE"
            ) &
            HOLD_TIMER_PID=$!
            ;;

        *": 0001 "*${HEX_KEYCODE}*" 00000002"*)
            # УДЕРЖАНИЕ (REPEAT от ядра)
            if [ ! -f /data/local/tmp/giga_hold_active ]; then
                touch /data/local/tmp/giga_hold_active
                vibrate 60
                "${MODDIR}/bin/audio_recorder.sh" start "$REC_FILE"
            fi
            ;;

        *": 0001 "*${HEX_KEYCODE}*" 00000000"*)
            # ОТПУСКАНИЕ (UP)
            # Отменяем фоновый таймер короткого нажатия
            if [ -n "$HOLD_TIMER_PID" ]; then
                kill "$HOLD_TIMER_PID" 2>/dev/null || true
                HOLD_TIMER_PID=""
            fi

            if [ -f /data/local/tmp/giga_hold_active ]; then
                # Это было зажатие клавиши (Push-to-talk)
                rm -f /data/local/tmp/giga_hold_active
                vibrate 35
                log "Клавиша отпущена. Остановка записи..."
                "${MODDIR}/bin/audio_recorder.sh" stop

                # Восстанавливаем громкость асинхронно, не задерживая запуск распознавания
                if [ "${RESTORE_VOLUME:-1}" = "1" ]; then
                    (cmd media_session volume --show --adj raise >/dev/null 2>&1) &
                fi

                # Запускаем распознавание в отдельном фоновом субпроцессе немедленно
                (
                    if [ -s "$REC_FILE" ]; then
                        log "Обработка аудиофайла: $REC_FILE"
                        RECOGNIZED_TEXT=$("${MODDIR}/bin/stt_client.sh" "$REC_FILE")
                        log "Распознано: '$RECOGNIZED_TEXT'"

                        if [ -n "$RECOGNIZED_TEXT" ]; then
                            # Сначала проверяем голосовые команды
                            if ! "${MODDIR}/bin/command_engine.sh" "$RECOGNIZED_TEXT"; then
                                # Если это не команда — вставляем как текст (диктовка)
                                log "Вставка текста в активное поле..."
                                "${MODDIR}/bin/text_injector.sh" "$RECOGNIZED_TEXT"
                            fi
                        fi
                    else
                        log "Предупреждение: файл записи пуст."
                    fi
                ) &
            fi
            ;;
    esac
done
