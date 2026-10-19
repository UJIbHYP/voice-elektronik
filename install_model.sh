#!/system/bin/sh
# ==============================================================
# Elektronic Android — Загрузчик локальной модели речи ONNX
# ==============================================================

MODDIR="${0%/*}"
MODEL_DIR="${MODDIR}/model"
MODEL_URL="https://github.com/moznoazachem/giga-pisar-cli/releases/download/v1.0/gigaam-v3-onnx-int8.tar.gz"
ARCHIVE="/data/local/tmp/gigaam-v3-onnx-int8.tar.gz"

# Экспортируем пути Termux и системы в PATH
export PATH="$PATH:/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin"

echo "=== Elektronic: Установка локальной модели речи ==="
mkdir -p "$MODEL_DIR"

if [ -f "${MODEL_DIR}/v3_e2e_rnnt.yaml" ] && [ -f "${MODEL_DIR}/v3_e2e_rnnt_encoder.onnx" ]; then
    echo "[+] Модель уже установлена в ${MODEL_DIR}"
    exit 0
fi

echo "[*] Загрузка архива модели (~204 МБ)..."

# Определение утилиты загрузки
CURL_BIN=""
WGET_BIN=""
if command -v curl >/dev/null 2>&1; then
    CURL_BIN="curl"
elif [ -x "/data/data/com.termux/files/usr/bin/curl" ]; then
    CURL_BIN="/data/data/com.termux/files/usr/bin/curl"
fi

if command -v wget >/dev/null 2>&1; then
    WGET_BIN="wget"
elif [ -x "/data/data/com.termux/files/usr/bin/wget" ]; then
    WGET_BIN="/data/data/com.termux/files/usr/bin/wget"
fi

DOWNLOADED=0

if [ -n "$CURL_BIN" ]; then
    echo "[*] Используется curl: $CURL_BIN"
    "$CURL_BIN" -L --progress-bar -o "$ARCHIVE" "$MODEL_URL" && DOWNLOADED=1
elif [ -n "$WGET_BIN" ]; then
    echo "[*] Используется wget: $WGET_BIN"
    "$WGET_BIN" -O "$ARCHIVE" "$MODEL_URL" && DOWNLOADED=1
else
    # Резервная загрузка через Python urllib
    PYTHON_BIN=""
    if command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    elif [ -x "/data/data/com.termux/files/usr/bin/python3" ]; then
        PYTHON_BIN="/data/data/com.termux/files/usr/bin/python3"
    fi

    if [ -n "$PYTHON_BIN" ]; then
        echo "[*] Используется Python urllib..."
        $PYTHON_BIN -c "
import urllib.request, sys
url = '${MODEL_URL}'
dest = '${ARCHIVE}'
print('Загрузка в процессe...')
urllib.request.urlretrieve(url, dest)
print('Готово!')
" && DOWNLOADED=1
    fi
fi

if [ "$DOWNLOADED" -ne 1 ] || [ ! -s "$ARCHIVE" ]; then
    echo "[-] Ошибка: не удалось загрузить архив."
    rm -f "$ARCHIVE"
    exit 1
fi

echo "[*] Распаковка модели в ${MODEL_DIR}..."

# Определение утилиты tar
TAR_BIN=""
if command -v tar >/dev/null 2>&1; then
    TAR_BIN="tar"
elif [ -x "/data/data/com.termux/files/usr/bin/tar" ]; then
    TAR_BIN="/data/data/com.termux/files/usr/bin/tar"
fi

if [ -n "$TAR_BIN" ]; then
    "$TAR_BIN" -xzf "$ARCHIVE" -C "$MODEL_DIR" --strip-components=1 2>/dev/null || \
    "$TAR_BIN" -xzf "$ARCHIVE" -C "$MODEL_DIR"
else
    # Резервная распаковка через Python tarfile
    $PYTHON_BIN -c "
import tarfile
with tarfile.open('${ARCHIVE}', 'r:gz') as t:
    t.extractall('${MODEL_DIR}')
"
fi

rm -f "$ARCHIVE"

# Проверка и перемещение файлов, если распаковались во вложенную папку
if [ ! -f "${MODEL_DIR}/v3_e2e_rnnt.yaml" ]; then
    NESTED=$(find "$MODEL_DIR" -maxdepth 2 -name "v3_e2e_rnnt.yaml" | head -n 1)
    if [ -n "$NESTED" ]; then
        NESTED_DIR=$(dirname "$NESTED")
        if [ "$NESTED_DIR" != "$MODEL_DIR" ]; then
            mv "$NESTED_DIR"/* "$MODEL_DIR"/
            rmdir "$NESTED_DIR" 2>/dev/null || true
        fi
    fi
fi

if [ -f "${MODEL_DIR}/v3_e2e_rnnt.yaml" ]; then
    echo "[+] Модель успешно установлена и готова к работе в ${MODEL_DIR}!"
    ls -lh "$MODEL_DIR"
else
    echo "[-] Внимание: проверьте содержимое ${MODEL_DIR}."
fi
