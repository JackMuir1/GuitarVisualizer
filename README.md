# Guitar Visualizer

A real-time ambient color visualizer that listens to guitar audio through a USB audio interface and displays colors corresponding to the detected note, with Frutiger Aero-style bubble animations.

Developed pretty much entirely with claude code. CLAUDE.md and PRD.md included.

## Features

- Real-time pitch detection via aubio (YIN algorithm, < 100ms latency)
- Chromatic note-to-color mapping (12 notes → configurable colors)
- Smooth color interpolation as notes change
- Silence fade: holds last note color, then slowly fades to white
- Frutiger Aero ambient animations — bubble speed and pulse scale with amplitude
- Live config reload — edit `config.yaml` and changes apply within 1 second, no restart needed

## Setup

```bash
pip install -r requirements.txt
```

## Find Your Audio Device

```bash
python -c "import sounddevice; print(sounddevice.query_devices())"
```

Set `audio.device` in `config.yaml` to the device name or index shown.

## Run

```bash
python main.py
```

Press `Escape` or `Q` to quit.

## Configuration

All settings live in `config.yaml`. Changes are detected and applied live:

| Setting | Description |
|---|---|
| `audio.device` | USB audio device name or index (`null` = system default) |
| `detection.noise_gate_db` | Minimum dBFS to trigger note detection (default: -20) |
| `detection.confidence_threshold` | aubio confidence minimum (0.0–1.0) |
| `display.interpolation_speed` | Color lerp speed per frame (0.0–1.0) |
| `display.silence_timeout_sec` | Seconds of silence before fade-to-white begins |
| `animation.bubble_count` | Number of ambient bubbles |
| `animation.amplitude_scale` | Multiplier for amplitude-driven animation energy |
| `note_colors` | Map of note names to `#RRGGBB` hex colors |
