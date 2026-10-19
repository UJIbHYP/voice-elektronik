##########################################################################################
# Elektronic Android — customize.sh
# Интерактивный установщик с выбором загрузки модели кнопками громкости
##########################################################################################

ui_print " "
ui_print "=========================================="
ui_print "       Elektronic Android (Электроник)    "
ui_print "   Локальная диктовка и голосовые команды "
ui_print "=========================================="
ui_print " "

# 1. Проверка архитектуры
if [ "$ARCH" != "arm64" ]; then
  ui_print "[-] Ошибка: Поддерживается только архитектура arm64 (aarch64)!"
  abort "Неподдерживаемая архитектура процессора: $ARCH"
fi

# 2. Установка прав доступа
ui_print "[*] Настройка прав доступа на исполняемые файлы..."
set_perm_recursive "$MODPATH/bin" 0 0 0755 0755
set_perm_recursive "$MODPATH/server" 0 0 0755 0755
set_perm_recursive "$MODPATH/tools" 0 0 0755 0755
set_perm_recursive "$MODPATH/system/bin" 0 0 0755 0755
set_perm "$MODPATH/service.sh" 0 0 0755
set_perm "$MODPATH/install_model.sh" 0 0 0755
set_perm "$MODPATH/giga.conf" 0 0 0644
set_perm "$MODPATH/commands.conf" 0 0 0644

mkdir -p "$MODPATH/model" 2>/dev/null
set_perm "$MODPATH/model" 0 0 0777

# 3. Интерактивная функция выбора через кнопки громкости
choose_download_model() {
  ui_print " "
  ui_print "--------------------------------------------------"
  ui_print " [?] Надо ли скачать модель речи GigaAM v3 (~204 МБ)?"
  ui_print "--------------------------------------------------"
  ui_print "   [ГРОМКОСТЬ ВВЕРХ (+)] : ДА (скачать сейчас)"
  ui_print "   [ГРОМКОСТЬ ВНИЗ  (-)] : НЕТ (пропустить)"
  ui_print "--------------------------------------------------"

  local out="/data/local/tmp/giga_vol_choice"
  rm -f "$out"

  # Фоновый перехват события нажатия
  (
    getevent -l 2>/dev/null | while read -r line; do
      case "$line" in
        *KEY_VOLUMEUP*DOWN*|*KEY_VOLUMEUP*00000001*|*0073*00000001*)
          echo "yes" > "$out"
          break
          ;;
        *KEY_VOLUMEDOWN*DOWN*|*KEY_VOLUMEDOWN*00000001*|*0072*00000001*)
          echo "no" > "$out"
          break
          ;;
      esac
    done
  ) &
  local listener_pid=$!

  # Ожидание выбора пользователя (до 60 секунд)
  local timer=0
  while [ ! -f "$out" ] && [ $timer -lt 600 ]; do
    sleep 0.1
    timer=$((timer + 1))
  done

  kill "$listener_pid" 2>/dev/null || true
  pkill -P "$listener_pid" 2>/dev/null || true
  pkill -f "getevent" 2>/dev/null || true

  local choice="no"
  if [ -f "$out" ]; then
    choice=$(cat "$out")
    rm -f "$out"
  else
    ui_print " [!] Время ожидания истекло (таймаут 60 сек)."
  fi

  if [ "$choice" = "yes" ]; then
    ui_print " [+] Выбрано: [ДА] Загрузка модели..."
    return 0
  else
    ui_print " [-] Выбрано: [НЕТ] Пропуск загрузки модели."
    return 1
  fi
}

# 4. Проверка наличия модели или запуск загрузки
if [ -f "$MODPATH/model/v3_e2e_rnnt.yaml" ] && [ -f "$MODPATH/model/v3_e2e_rnnt_encoder.onnx" ]; then
  ui_print "[+] Модель GigaAM v3 уже присутствует в модуле!"
else
  if choose_download_model; then
    ui_print "[*] Запуск загрузчика модели (требуется интернет)..."
    export PATH="$PATH:/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin"
    sh "$MODPATH/install_model.sh"
    if [ -f "$MODPATH/model/v3_e2e_rnnt.yaml" ]; then
      ui_print "[+] Модель успешно скачана и установлена!"
    else
      ui_print "[-] Внимание: не удалось скачать модель сейчас."
      ui_print "    Вы сможете скачать её позже командой:"
      ui_print "    su -c 'sh /data/adb/modules/giga_pisar_android/install_model.sh'"
    fi
  else
    ui_print " [i] Модель не загружена."
    ui_print "     Вы сможете скачать её в любое время командой:"
    ui_print "     su -c 'sh /data/adb/modules/giga_pisar_android/install_model.sh'"
    ui_print "     или вручную скопировать файлы модели в папку model/."
  fi
fi

ui_print " "
ui_print "=========================================="
ui_print " [✓] Установка модуля успешно завершена!  "
ui_print "     Перезагрузите устройство.            "
ui_print "=========================================="
ui_print " "
