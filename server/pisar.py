#!/usr/bin/env python3
"""Elektronic CLI & HTTP Server — распознавание речи через GigaAM v3."""
from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import giga_core
import commands_helper

HOST = "127.0.0.1"
PORT = 8737


def _parse_multipart(body: bytes, content_type: str) -> bytes:
    """Извлекает бинарное содержимое поля file из multipart запроса."""
    marker = "boundary="
    if marker not in content_type:
        raise ValueError("В запросе нет multipart boundary")
    boundary = content_type.split(marker, 1)[1].strip().strip('"')
    delimiter = b"--" + boundary.encode()

    for part in body.split(delimiter):
        if b"\r\n\r\n" not in part:
            continue
        header, payload = part.split(b"\r\n\r\n", 1)
        if b'name="file"' in header or b"name='file'" in header or b"filename=" in header:
            return payload.rstrip(b"-").rstrip(b"\r\n")
    # Если передано чистое аудио в теле запроса (raw audio/wav)
    if body.startswith(b"RIFF"):
        return body
    raise ValueError("В запросе не найдено поле с аудиофайлом")


def serve(model_dir: str = "", host: str = HOST, port: int = PORT, threads: int = 2) -> None:
    print(f"[elektronic] Загрузка модели GigaAM v3 (потоков: {threads})...", file=sys.stderr, flush=True)
    engine = giga_core.Engine(model_dir, threads=threads)
    cmd_matcher = commands_helper.CommandMatcher()
    lock = threading.Lock()
    print(f"[elektronic] Сервер запущен: http://{host}:{port} (модель: {engine.model_dir})",
          file=sys.stderr, flush=True)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            pass

        def _send_json(self, code: int, data: dict) -> None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/") in ("/health", "/v1/health"):
                self._send_json(200, {"status": "ok", "model": giga_core.MODEL_NAME})
            else:
                self._send_json(404, {"error": "Страница не найдена"})

        def do_POST(self):
            path = self.path.rstrip("/")
            if not (path.endswith("/audio/transcriptions") or path.endswith("/transcribe")):
                self._send_json(404, {"error": "Неверный endpoint"})
                return

            try:
                length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(length)
                content_type = self.headers.get("Content-Type", "")
                
                if "multipart/form-data" in content_type:
                    audio_bytes = _parse_multipart(raw_body, content_type)
                else:
                    audio_bytes = raw_body

                if not audio_bytes:
                    self._send_json(400, {"error": "Пустые данные аудио"})
                    return
            except Exception as e:
                self._send_json(400, {"error": f"Ошибка разбора запроса: {e}"})
                return

            try:
                # Прямая обработка из оперативной памяти без записи на диск
                if audio_bytes.startswith(b"RIFF") and len(audio_bytes) > 44:
                    raw_pcm = audio_bytes[44:]
                else:
                    raw_pcm = audio_bytes
                if len(raw_pcm) % 2 != 0:
                    raw_pcm = raw_pcm[:-1]

                import numpy as np
                samples = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0

                with lock:
                    if len(samples) > 0:
                        text = engine.transcribe_wave(samples).strip()
                    else:
                        text = ""

                clean = cmd_matcher.clean(text)
                is_cmd, action = cmd_matcher.match(clean)

                self._send_json(200, {
                    "text": text,
                    "clean": clean,
                    "is_command": is_cmd,
                    "command": action if is_cmd else None
                })
            except Exception as e:
                print(f"[elektronic] Ошибка распознавания: {e}", file=sys.stderr, flush=True)
                self._send_json(500, {"error": str(e)})

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()


def main():
    args = sys.argv[1:]

    def get_flag(flag, default=None):
        if flag in args:
            idx = args.index(flag)
            val = args[idx + 1]
            del args[idx:idx + 2]
            return val
        return default

    model_dir = get_flag("--model-dir", "") or ""
    host = get_flag("--host", HOST)
    port = int(get_flag("--port", PORT))
    threads = int(get_flag("--threads", 2))

    if "--serve" in args:
        args.remove("--serve")
        serve(model_dir, host, port, threads)
        return

    if not args or args[0] in ("-h", "--help"):
        print("Использование:", file=sys.stderr)
        print("  pisar файл.wav             # распознать файл", file=sys.stderr)
        print("  pisar --serve              # запустить локальный сервер HTTP", file=sys.stderr)
        sys.exit(0 if args else 1)

    engine = giga_core.Engine(model_dir)
    for audio_path in args:
        if os.path.exists(audio_path):
            text = engine.transcribe(audio_path)
            print(text)


if __name__ == "__main__":
    main()
