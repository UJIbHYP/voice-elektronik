#!/usr/bin/env python3
"""Elektronic Android — Аппаратный перехватчик клавиши громкости с эксклюзивным захватом (EVIOCGRAB).

Позволяет:
1. Одиночный клик (< 300 мс) -> нормальное изменение громкости (проброс в Android через uinput).
2. Зажатие (>= 300 мс) -> голосовой ввод текста/команд БЕЗ изменения громкости и БЕЗ вызова шторки звука!
"""
from __future__ import annotations

import os
import signal
import struct
import subprocess
import sys
import threading
import time
import fcntl
import select

UI_SET_EVBIT = 0x40045564
UI_SET_KEYBIT = 0x40045565
UI_DEV_SETUP = 0x405c5503
UI_DEV_CREATE = 0x5501
UI_DEV_DESTROY = 0x5502
EVIOCGRAB = 0x40044590

EV_SYN = 0x00
EV_KEY = 0x01

MODDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE = "/data/local/tmp/giga_pisar.log"
REC_FILE = "/data/local/tmp/giga_rec.wav"
PID_FILE = "/data/local/tmp/giga_listener.pid"

# Чтение конфигурации
def load_config() -> dict:
    cfg = {
        "TRIGGER_KEYCODE": 114,
        "TRIGGER_HOLD_MS": 300,
        "HAPTIC_FEEDBACK": 1,
        "DEBUG_LOG": 1,
    }
    conf_path = os.path.join(MODDIR, "giga.conf")
    if os.path.isfile(conf_path):
        with open(conf_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.split("#")[0].strip().strip('"').strip("'")
                if k in ("TRIGGER_KEYCODE", "TRIGGER_HOLD_MS", "HAPTIC_FEEDBACK", "DEBUG_LOG"):
                    try:
                        cfg[k] = int(v)
                    except ValueError:
                        pass
    return cfg

CONFIG = load_config()

def log(msg: str):
    if CONFIG.get("DEBUG_LOG", 1):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} [INTERCEPTOR] {msg}\n")

def vibrate(duration_ms: int):
    if CONFIG.get("HAPTIC_FEEDBACK", 1):
        subprocess.run(["cmd", "vibrator", "vibrate", str(duration_ms)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def find_input_device(keycode: int = 114) -> tuple[str, list[int]]:
    """Находит устройство ввода с аппаратными клавишами (Volume / Power)."""
    # Сначала проверяем стандартный /dev/input/event1 (mtk-kpd)
    candidates = ["/dev/input/event1"]
    for i in range(10):
        p = f"/dev/input/event{i}"
        if p not in candidates and os.path.exists(p):
            candidates.append(p)

    for p in candidates:
        if not os.path.exists(p):
            continue
        try:
            # Проверяем имя устройства в sysfs
            num = p.replace("/dev/input/event", "")
            name_file = f"/sys/class/input/event{num}/device/name"
            if os.path.exists(name_file):
                with open(name_file, "r") as nf:
                    name = nf.read().strip()
                if any(x in name.lower() for x in ["kpd", "gpio", "pkeys", "keypad"]):
                    return p, [114, 115, 116]
        except Exception:
            pass

    return "/dev/input/event1", [114, 115, 116]

class KeyInterceptor:
    def __init__(self):
        self.running = True
        self.dev_path, self.keys = find_input_device(CONFIG["TRIGGER_KEYCODE"])
        self.trigger_key = CONFIG["TRIGGER_KEYCODE"]
        self.hold_threshold = CONFIG["TRIGGER_HOLD_MS"] / 1000.0

        self.in_fd = -1
        self.uinput_fd = -1
        self.grabbed = False

        self.down_time = 0.0
        self.is_holding = False
        self.timer: threading.Timer | None = None
        self.lock = threading.Lock()

    def setup_uinput(self):
        self.uinput_fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.uinput_fd, UI_SET_EVBIT, EV_KEY)
        fcntl.ioctl(self.uinput_fd, UI_SET_EVBIT, EV_SYN)
        for k in self.keys:
            fcntl.ioctl(self.uinput_fd, UI_SET_KEYBIT, k)

        id_struct = struct.pack("HHHH", 0x03, 0x1234, 0x5678, 0x01)
        name = b"giga_intercept_keys"
        setup = id_struct + name.ljust(80, b"\x00") + struct.pack("I", 0)
        try:
            fcntl.ioctl(self.uinput_fd, UI_DEV_SETUP, setup)
        except OSError:
            uinput_user_dev = name.ljust(80, b"\x00") + id_struct + struct.pack("i", 0) + b"\x00" * (1112 - 80 - 8 - 4)
            os.write(self.uinput_fd, uinput_user_dev)

        fcntl.ioctl(self.uinput_fd, UI_DEV_CREATE)

    def emit(self, ev_type: int, code: int, val: int):
        t = time.time()
        s = int(t)
        us = int((t - s) * 1_000_000)
        packet = struct.pack("qqHHi", s, us, ev_type, code, val)
        os.write(self.uinput_fd, packet)

    def forward_single_click(self):
        """Отправляет одиночный импульс нажатия и отпускания в Android."""
        self.emit(EV_KEY, self.trigger_key, 1)
        self.emit(EV_SYN, 0, 0)
        time.sleep(0.02)
        self.emit(EV_KEY, self.trigger_key, 0)
        self.emit(EV_SYN, 0, 0)

    def on_hold_detected(self):
        """Срабатывает, если кнопка удерживается дольше hold_threshold (300 мс)."""
        with self.lock:
            if self.down_time > 0 and not self.is_holding:
                self.is_holding = True
                log("Зажатие клавиши подтверждено -> активация диктовки/команд (громкость не меняется)")
                vibrate(60)
                # Запуск записи звука в фоновом режиме
                rec_script = os.path.join(MODDIR, "bin", "audio_recorder.sh")
                subprocess.Popen([rec_script, "start", REC_FILE],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def process_stt_result(self):
        """Обрабатывает записанный аудиофайл после отпускания кнопки."""
        if not os.path.isfile(REC_FILE) or os.path.getsize(REC_FILE) == 0:
            log("Файл записи пуст, пропуск")
            return

        stt_script = os.path.join(MODDIR, "bin", "stt_client.sh")
        cmd_script = os.path.join(MODDIR, "bin", "command_engine.sh")
        inj_script = os.path.join(MODDIR, "bin", "text_injector.sh")

        log(f"Обработка аудиофайла: {REC_FILE}")
        try:
            res = subprocess.run([stt_script, REC_FILE], capture_output=True, text=True, timeout=15)
            recognized_text = res.stdout.strip()
        except Exception as e:
            log(f"Ошибка вызова stt_client: {e}")
            return

        log(f"Распознано: '{recognized_text}'")
        if not recognized_text:
            return

        # 1. Проверяем команду
        cmd_res = subprocess.run([cmd_script, recognized_text])
        if cmd_res.returncode == 0:
            log("Голосовая команда успешно выполнена")
            return

        # 2. Если не команда — вставляем текст
        log("Вставка текста в активное поле...")
        subprocess.run([inj_script, recognized_text])

    def run(self):
        self.setup_uinput()
        self.in_fd = os.open(self.dev_path, os.O_RDONLY | os.O_NONBLOCK)
        fcntl.ioctl(self.in_fd, EVIOCGRAB, 1)
        self.grabbed = True
        log(f"Аппаратный захват активен на {self.dev_path} (порог {CONFIG['TRIGGER_HOLD_MS']}мс)")

        try:
            while self.running:
                r, _, _ = select.select([self.in_fd], [], [], 0.5)
                if not r:
                    continue

                try:
                    data = os.read(self.in_fd, 24)
                except BlockingIOError:
                    continue

                if len(data) < 24:
                    continue

                sec, usec, ev_type, code, val = struct.unpack("qqHHi", data)

                # Проверяем, клавиша ли это
                if ev_type == EV_KEY and code == self.trigger_key:
                    if val == 1: # НАЖАТИЕ ВНИЗ (DOWN)
                        with self.lock:
                            self.down_time = time.time()
                            self.is_holding = False
                            if self.timer:
                                self.timer.cancel()
                            self.timer = threading.Timer(self.hold_threshold, self.on_hold_detected)
                            self.timer.daemon = True
                            self.timer.start()

                    elif val == 2: # REPEAT от ядра
                        # Игнорируем повторы ядра при удержании
                        pass

                    elif val == 0: # ОТПУСКАНИЕ (UP)
                        with self.lock:
                            if self.timer:
                                self.timer.cancel()
                                self.timer = None

                            if self.is_holding:
                                # Это было удержание (голосовой ввод)
                                self.is_holding = False
                                self.down_time = 0.0
                                log("Клавиша отпущена. Остановка записи...")
                                vibrate(35)
                                rec_script = os.path.join(MODDIR, "bin", "audio_recorder.sh")
                                subprocess.run([rec_script, "stop"],
                                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                # Запуск обработки в отдельном потоке
                                threading.Thread(target=self.process_stt_result, daemon=True).start()
                            else:
                                # Это был короткий одиночный клик (< 300мс)
                                self.down_time = 0.0
                                # Пробрасываем клик в Android для изменения громкости
                                self.forward_single_click()
                    continue

                # Если это событие SYN_REPORT
                if ev_type == EV_SYN:
                    # Если кнопка громкости сейчас нажата/удерживается, поглощаем SYN
                    with self.lock:
                        if self.down_time > 0 or self.is_holding:
                            continue
                    # Иначе пробрасываем
                    os.write(self.uinput_fd, data)
                    continue

                # Любые другие кнопки (Volume Up, Power и т.д.) пробрасываем мгновенно без задержек!
                os.write(self.uinput_fd, data)

        finally:
            self.cleanup()

    def cleanup(self):
        log("Освобождение аппаратного захвата...")
        if self.timer:
            self.timer.cancel()
        if self.in_fd >= 0:
            if self.grabbed:
                try:
                    fcntl.ioctl(self.in_fd, EVIOCGRAB, 0)
                except Exception:
                    pass
            try:
                os.close(self.in_fd)
            except Exception:
                pass
        if self.uinput_fd >= 0:
            try:
                fcntl.ioctl(self.uinput_fd, UI_DEV_DESTROY)
                os.close(self.uinput_fd)
            except Exception:
                pass
        log("Захват успешно снят.")

interceptor: KeyInterceptor | None = None

def handle_signal(sig, frame):
    global interceptor
    if interceptor:
        interceptor.running = False

def main():
    global interceptor
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Запись PID
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    interceptor = KeyInterceptor()
    interceptor.run()

if __name__ == "__main__":
    main()
