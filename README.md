# Elektronic Android

Local Russian voice dictation and voice command control for Android using Magisk.

This module allows you to:
- Convert speech to text using the GigaAM v3 model (ONNX) completely offline.
- Control your device via voice commands by holding the volume-down button.

**Based on:** [giga-pisar](https://github.com/moznoazachem/giga-pisar)

---

## Features

### Voice Dictation
- Speech-to-text recognition via the local GigaAM v3 model.
- Automatic text insertion into the active input field or copy to clipboard.
- Two working modes: local server and CLI.

### Voice Commands
- Device control via voice commands with the prefix `android` (e.g., "android, reboot phone").
- Supported commands include:
  - Reboot and power off
  - Volume and flashlight control
  - Screenshots and screen lock
  - Media player control
  - App launching (Telegram, WhatsApp, Calculator, etc.)
  - System checks: root status, CPU temperature, battery state, and more

### Adding Your Own Commands

To add custom voice commands, edit the **commands.conf** file.

Command format:

```
phrase_or_regex = shell_command
```

Examples:

```
reboot phone = reboot
turn on flashlight = cmd flashlight on
open telegram = monkey -p org.telegram.messenger 1
```

1. Open the **commands.conf** file in a text editor.
2. Add new commands in the format `phrase = command`.
3. Save the file.
4. Reboot the device or restart the daemon.

**Note:** The command prefix (e.g., "android") can be changed in **giga.conf** (`COMMAND_PREFIX`).

---

## Installation

1. Make sure Magisk is installed on your device.
2. Download the module ZIP file.
3. Install via Magisk Manager: **Module → Install from storage**.
4. Reboot the device.

---

## Configuration

The main configuration parameters are in the **giga.conf** file. You can adjust:
- Activation key (default — volume down).
- Key hold duration for activation.
- Recording method (auto, app_process, tinycap).
- Recognition mode (local_server, local_cli, remote).
- Haptic feedback and auto-paste on/off.

---

## Module Structure

- **bin/** — Module scripts for operation and audio processing.
- **server/** — Python server for speech recognition.
- **model/** — GigaAM v3 model (ONNX files).
- **commands.conf** — List of supported voice commands.
- **service.sh** — Runs at boot to initialize the module.

---

## Usage

1. Hold the volume-down button to activate recording.
2. Speak text or a command, e.g., "android, open Telegram".
3. After releasing the button, the text will be inserted or the command executed.

---

## Support and Debugging

- Logs are available at: `/data/local/tmp/giga_pisar.log`.
- Enable debug logging in **giga.conf** (`DEBUG_LOG=1`).

---

## Authors

- moznoazachem
- dot_mir

---

## License

This module uses the GigaAM v3 model and code from the [giga-pisar](https://github.com/moznoazachem/giga-pisar) project. Please refer to the upstream repository for license details.