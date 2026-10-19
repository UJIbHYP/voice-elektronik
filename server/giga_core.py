#!/usr/bin/env python3
"""Ядро Электроника: распознавание речи моделью GigaAM v3 в формате ONNX на Android.

Локальный инференс без интернета на базе ONNX Runtime.
Адаптировано для Android: поддержка прямого чтения 16 кГц WAV без необходимости наличия ffmpeg.
Оптимизировано: кэширование вычислений предиктора в жадном декодере RNN-T (ускорение декодирования в 3+ раза).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

SAMPLE_RATE = 16000
MODEL_NAME = "v3_e2e_rnnt"

MAX_CHUNK = 24.0        # предел одного прохода модели — 25 секунд
SILENCE_DB = -35        # порог тишины для нарезки
SILENCE_MIN = 0.3       # минимальная длина паузы, секунды
MAX_SYMBOLS_PER_FRAME = 3   # столько букв максимум с одного кадра


# ─────────────────────────── признаки звука ───────────────────────────

def _hz_to_mel(freq):
    return 2595.0 * np.log10(1.0 + freq / 700.0)


def _mel_to_hz(mels):
    return 700.0 * (10.0 ** (mels / 2595.0) - 1.0)


def _mel_filterbank(n_freqs, f_min, f_max, n_mels, sample_rate):
    all_freqs = np.linspace(0, sample_rate // 2, n_freqs)
    m_pts = np.linspace(_hz_to_mel(f_min), _hz_to_mel(f_max), n_mels + 2)
    f_pts = _mel_to_hz(m_pts)

    f_diff = f_pts[1:] - f_pts[:-1]
    slopes = f_pts[np.newaxis, :] - all_freqs[:, np.newaxis]
    down = -slopes[:, :-2] / f_diff[np.newaxis, :-1]
    up = slopes[:, 2:] / f_diff[np.newaxis, 1:]
    return np.maximum(0.0, np.minimum(down, up))


class Features:
    """Превращает звуковую волну в лог-мел-спектрограмму для энкодера."""

    def __init__(self, cfg: dict):
        pre = cfg["preprocessor"]
        self.sample_rate = int(pre.get("sample_rate", SAMPLE_RATE))
        self.n_mels = int(pre["features"])
        self.n_fft = int(pre.get("n_fft", self.sample_rate // 40))
        self.win_length = int(pre.get("win_length", self.sample_rate // 40))
        self.hop_length = int(pre.get("hop_length", self.sample_rate // 100))
        self.center = bool(pre.get("center", True))

        n = np.arange(self.win_length)
        self.window = (0.5 - 0.5 * np.cos(2.0 * np.pi * n / self.win_length)).astype(np.float32)

        self.fb = _mel_filterbank(
            n_freqs=self.n_fft // 2 + 1,
            f_min=0.0,
            f_max=self.sample_rate / 2.0,
            n_mels=self.n_mels,
            sample_rate=self.sample_rate,
        ).astype(np.float32)

    def out_len(self, n_samples: int) -> int:
        if self.center:
            return n_samples // self.hop_length + 1
        return max(0, (n_samples - self.win_length) // self.hop_length + 1)

    def __call__(self, wav: np.ndarray) -> np.ndarray:
        x = np.asarray(wav, dtype=np.float32)
        if self.center:
            pad = self.n_fft // 2
            x = np.pad(x, (pad, pad), mode="reflect")

        n_frames = max(0, (len(x) - self.n_fft) // self.hop_length + 1)
        idx = np.arange(self.n_fft)[np.newaxis, :] + \
            self.hop_length * np.arange(n_frames)[:, np.newaxis]
        frames = (x[idx] * self.window[np.newaxis, :]).astype(np.float32)

        spec = (np.abs(np.fft.rfft(frames, n=self.n_fft, axis=1)) ** 2).astype(np.float32)
        mel = spec @ self.fb
        mel = np.log(np.clip(mel, 1e-9, 1e9))
        return mel.T[np.newaxis, :, :].astype(np.float32)


# ─────────────────────────── работа с аудио ───────────────────────────

def read_wav(path: str) -> np.ndarray:
    """Читает 16-битный моно wav стандартной библиотекой Python без ffmpeg."""
    channels, framerate = 1, SAMPLE_RATE
    data = b""
    try:
        with wave.open(path, "rb") as w:
            channels = w.getnchannels()
            framerate = w.getframerate()
            nframes = w.getnframes()
            data = w.readframes(nframes)
    except Exception:
        pass

    # Если WAV-заголовок содержал 0 кадров или файл не закрыт до конца
    if len(data) == 0:
        try:
            with open(path, "rb") as raw:
                raw_bytes = raw.read()
                if raw_bytes.startswith(b"RIFF") and len(raw_bytes) > 44:
                    data = raw_bytes[44:]
                else:
                    data = raw_bytes
        except Exception:
            pass

    if len(data) == 0:
        return np.array([], dtype=np.float32)

    if len(data) % 2 != 0:
        data = data[:-1]

    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0

    # Если стерео — усредняем каналы в моно
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)

    # Базовый ресемплинг если не 16кГц
    if framerate != SAMPLE_RATE and len(samples) > 0:
        new_len = int(len(samples) * SAMPLE_RATE / framerate)
        samples = np.interp(
            np.linspace(0, len(samples), new_len, endpoint=False),
            np.arange(len(samples)),
            samples
        ).astype(np.float32)

    return samples


def find_model_dir(extra: str = "") -> str:
    """Ищет папку с файлами модели GigaAM v3."""
    candidates = [
        extra,
        os.environ.get("PISAR_MODEL_DIR", ""),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "model"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "model"),
        "/data/adb/modules/giga_pisar_android/model",
        "/data/local/tmp/giga_model",
        os.path.expanduser("~/.giga/model"),
    ]
    for path in candidates:
        if path and os.path.exists(os.path.join(path, f"{MODEL_NAME}.yaml")):
            return os.path.abspath(path)
    raise FileNotFoundError(
        "Модель GigaAM v3 не найдена. Укажите папку модели через PISAR_MODEL_DIR или запустите install_model.sh."
    )


class Engine:
    """Движок распознавания GigaAM v3 ONNX."""

    def __init__(self, model_dir: str = "", threads: int = 0):
        import onnxruntime as rt
        import yaml
        from sentencepiece import SentencePieceProcessor

        self.model_dir = find_model_dir(model_dir)
        yaml_path = os.path.join(self.model_dir, f"{MODEL_NAME}.yaml")
        with open(yaml_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        self.cfg = cfg

        opts = rt.SessionOptions()
        opts.graph_optimization_level = rt.GraphOptimizationLevel.ORT_ENABLE_ALL
        opts.intra_op_num_threads = threads or min(4, os.cpu_count() or 4)
        opts.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL
        opts.log_severity_level = 3

        def sess(suffix):
            path = os.path.join(self.model_dir, f"{MODEL_NAME}_{suffix}.onnx")
            return rt.InferenceSession(path, providers=["CPUExecutionProvider"], sess_options=opts)

        self.enc, self.pred, self.joint = sess("encoder"), sess("decoder"), sess("joint")

        tok = os.path.join(self.model_dir, f"{MODEL_NAME}_tokenizer.model")
        if not os.path.exists(tok):
            tok = cfg.get("decoding", {}).get("model_path", "")
        if not tok or not os.path.exists(tok):
            raise FileNotFoundError(f"Токенизатор не найден в {self.model_dir}")

        self.sp = SentencePieceProcessor()
        self.sp.load(tok)

        self.blank_id = len(self.sp)
        self.pred_hidden = int(cfg["head"]["decoder"]["pred_hidden"])
        self.pred_layers = int(cfg["head"]["decoder"]["pred_rnn_layers"])
        self.features = Features(cfg)

    def transcribe_wave(self, wav: np.ndarray) -> str:
        """Распознавание массива сэмплов (до 24-25 секунд)."""
        if len(wav) == 0:
            return ""
        feats = self.features(wav)
        lens = np.array([self.features.out_len(len(wav))], dtype=np.int64)

        enc_out = self.enc.run(
            [n.name for n in self.enc.get_outputs()],
            {n.name: v for n, v in zip(self.enc.get_inputs(), [feats, lens])},
        )
        enc_features = enc_out[0]
        enc_len = int(np.asarray(enc_out[1]).reshape(-1)[0])
        return self.sp.decode(self._decode_rnnt(enc_features, enc_len))

    def _decode_rnnt(self, enc_features: np.ndarray, enc_len: int) -> list:
        dtype = np.float32
        enc_features = np.asarray(enc_features, dtype=dtype, order="C")

        pred_names = [n.name for n in self.pred.get_outputs()]
        joint_names = [n.name for n in self.joint.get_outputs()]
        pred_in = [n.name for n in self.pred.get_inputs()]
        joint_in = [n.name for n in self.joint.get_inputs()]

        hyp = []
        label = np.array([[self.blank_id]], dtype=np.int64)
        h = np.zeros((self.pred_layers, 1, self.pred_hidden), dtype=dtype)
        c = np.zeros((self.pred_layers, 1, self.pred_hidden), dtype=dtype)

        # Вычисляем начальное предсказание предиктора для blank_id
        pred_feed = {pred_in[0]: label, pred_in[1]: h, pred_in[2]: c}
        g, h, c = self.pred.run(pred_names, pred_feed)
        g_trans = g.swapaxes(1, 2)

        joint_feed = {joint_in[0]: None, joint_in[1]: g_trans}

        total = enc_features.shape[2]
        for t in range(min(enc_len, total)):
            f = enc_features[:, :, t:t + 1]
            joint_feed[joint_in[0]] = f
            for _ in range(MAX_SYMBOLS_PER_FRAME):
                out = self.joint.run(joint_names, joint_feed)
                k = int(out[0][:, 0, 0, :].argmax(axis=-1)[0])

                if k == self.blank_id:
                    break
                hyp.append(k)
                label[0, 0] = k
                pred_feed[pred_in[0]] = label
                pred_feed[pred_in[1]] = h
                pred_feed[pred_in[2]] = c
                g, h, c = self.pred.run(pred_names, pred_feed)
                g_trans = g.swapaxes(1, 2)
                joint_feed[joint_in[1]] = g_trans
        return hyp

    def transcribe(self, path: str) -> str:
        """Распознавание файла любого поддерживаемого формата."""
        # Если это стандартный wav — читаем напрямую без внешних утилит
        try:
            samples = read_wav(path)
            duration = len(samples) / SAMPLE_RATE
            if duration <= MAX_CHUNK:
                return self.transcribe_wave(samples).strip()
        except Exception:
            pass

        # Если файл длинный или не wav, и есть ffmpeg — используем нарезку
        if shutil.which("ffmpeg"):
            with tempfile.TemporaryDirectory() as tmp:
                wav_tmp = os.path.join(tmp, "converted.wav")
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", path,
                     "-ac", "1", "-ar", str(SAMPLE_RATE), wav_tmp],
                    check=True
                )
                samples = read_wav(wav_tmp)
                # Разбиваем на чанки по MAX_CHUNK секунд
                chunk_samples = int(MAX_CHUNK * SAMPLE_RATE)
                parts = []
                for i in range(0, len(samples), chunk_samples):
                    chunk = samples[i:i + chunk_samples]
                    part_text = self.transcribe_wave(chunk)
                    if part_text:
                        parts.append(part_text)
                return " ".join(parts).strip()

        # Резервный вариант: прямое чтение
        samples = read_wav(path)
        return self.transcribe_wave(samples[:int(MAX_CHUNK * SAMPLE_RATE)]).strip()
