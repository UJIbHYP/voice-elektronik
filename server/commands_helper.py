#!/usr/bin/env python3
"""Elektronic — Высокоскоростной строгий модуль сопоставления голосовых команд.

Правило: команды распознаются ТОЛЬКО В НАЧАЛЕ фразы (или при полном совпадении с commands.conf).
Случайные упоминания ключевых слов внутри обычных предложений НЕ вызывают команд!
"""
from __future__ import annotations

import os
import re
import sys

# Строгие шаблоны (ТОЛЬКО С НАЧАЛА СТРОКИ ^)
ANCHORED_PATTERNS = [
    (r"^(перезагруз.*рекавери|reboot.*recovery)\b", "reboot recovery"),
    (r"^(перезагруз.*бутлоадер|reboot.*bootloader)\b", "reboot bootloader"),
    (r"^(перезагрузи телефон|перезагрузить телефон|перезагрузка|reboot)\b", "reboot"),
    (r"^(выключи телефон|power off|shutdown)\b", "reboot -p"),
    (r"^(повысь громкость|прибавь громкость|громче|звук выше|прибавь звук)\b", "cmd media_session volume --show --adj raise"),
    (r"^(понизь громкость|убавь громкость|тише|звук ниже|убавь звук)\b", "cmd media_session volume --show --adj lower"),
    (r"^(без звука|выключи звук)\b", "cmd media_session volume --show --adj lower; cmd media_session volume --show --adj lower; cmd media_session volume --show --adj lower"),
    (r"^(максимальная громкость|громкость на максимум)\b", "cmd media_session volume --show --adj raise; cmd media_session volume --show --adj raise; cmd media_session volume --show --adj raise"),
    (r"^(включи|зажги) фонарик\b", "am broadcast -a miui.intent.action.TOGGLE_TORCH --ez miui.intent.extra.IS_ENABLE true 2>/dev/null || cmd flashlight on"),
    (r"^(выключи|погаси) фонарик\b", "am broadcast -a miui.intent.action.TOGGLE_TORCH --ez miui.intent.extra.IS_ENABLE false 2>/dev/null || cmd flashlight off"),
    (r"^(переключи фонарик|фонарик)\b", "am broadcast -a miui.intent.action.TOGGLE_TORCH --ez miui.intent.extra.IS_TOGGLE true 2>/dev/null || cmd flashlight toggle"),
    (r"^(сделай )?(скриншот|снимок экрана)\b", "input keyevent 120"),
    (r"^(заблокируй экран|выключи экран|погаси экран)\b", "input keyevent 26"),
    (r"^включи (вайфай|wi-?fi)\b", "svc wifi enable"),
    (r"^выключи (вайфай|wi-?fi)\b", "svc wifi disable"),
    (r"^включи (блютуз|bluetooth)\b", "svc bluetooth enable"),
    (r"^выключи (блютуз|bluetooth)\b", "svc bluetooth disable"),
    (r"^открой (телеграм|telegram)\b", "monkey -p org.telegram.messenger 1"),
    (r"^открой (ватсап|whatsapp)\b", "monkey -p com.whatsapp 1"),
    (r"^открой браузер\b", "am start -a android.intent.action.VIEW -d https://google.com"),
    (r"^открой камеру\b", "am start -a android.media.action.STILL_IMAGE_CAMERA"),
    (r"^(пауза|продолжить|плей)\b", "input keyevent 85"),
    (r"^(следующий трек|следующая песня)\b", "input keyevent 87"),
    (r"^(предыдущий трек|предыдущая песня)\b", "input keyevent 88"),
]


class CommandMatcher:
    def __init__(self, conf_path: str = ""):
        if not conf_path:
            moddir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            conf_path = os.path.join(moddir, "commands.conf")
        self.conf_path = conf_path
        self._mtime = 0
        self.commands: dict[str, str] = {}
        self.load()

    @staticmethod
    def clean(text: str) -> str:
        """Нормализация текста (нижний регистр, удаление пунктуации и лишних пробелов)."""
        t = text.lower()
        t = re.sub(r"[,.!?:«»\"'\-]", "", t)
        return " ".join(t.split())

    def load(self) -> None:
        """Перечитывает commands.conf если файл изменился на диске."""
        try:
            if not os.path.isfile(self.conf_path):
                return
            mtime = os.path.getmtime(self.conf_path)
            if mtime == self._mtime:
                return
            self._mtime = mtime
            cmds = {}
            with open(self.conf_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    pat, act = line.split("=", 1)
                    clean_pat = self.clean(pat)
                    cmds[clean_pat] = act.strip()
            self.commands = cmds
        except Exception:
            pass

    def match(self, raw_text: str, prefix: str = "андроид") -> tuple[bool, str]:
        """Определяет, является ли фраза голосовой командой.
        
        Команда срабатывает ТОЛЬКО если она стоит в НАЧАЛЕ фразы (или фраза совпадает с командой целиком).
        Упоминание ключевых слов в середине произвольного текста игнорируется.
        """
        self.load()
        text = self.clean(raw_text)
        if not text:
            return False, ""

        cmd_text = text

        # 1. Проверяем префикс ТОЛЬКО В САМОМ НАЧАЛЕ строки
        prefix_clean = self.clean(prefix) if prefix else ""
        prefixes = [p for p in [prefix_clean, "андроид", "android", "писарь"] if p]
        for p in prefixes:
            if cmd_text == p:
                return True, ""
            if cmd_text.startswith(p + " "):
                cmd_text = cmd_text[len(p):].strip()
                break

        if not cmd_text:
            return False, ""

        # 2. Полное совпадение с командой из commands.conf
        if cmd_text in self.commands:
            return True, self.commands[cmd_text]

        # 3. Команда из commands.conf стоит СТРОГО В НАЧАЛЕ строки
        for pat in sorted(self.commands.keys(), key=len, reverse=True):
            if cmd_text.startswith(pat + " "):
                return True, self.commands[pat]

        # 4. Строгие якорные шаблоны (ТОЛЬКО С НАЧАЛА СТРОКИ ^)
        for pat, act in ANCHORED_PATTERNS:
            if re.search(pat, cmd_text):
                return True, act

        return False, ""


def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    text = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else "андроид"
    matcher = CommandMatcher()
    is_cmd, action = matcher.match(text, prefix=prefix)
    if is_cmd and action:
        print(action)
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
