# Guitar Visualizer — Product Requirements Document

## Project Overview

Guitar Visualizer is a Python desktop application that listens to real-time audio from a USB audio interface connected to a Mac, detects the pitch of notes being played on a guitar/amp, and displays a full-screen ambient color visualizer tied to the detected note. The aesthetic is calm and meditative — inspired by the Frutiger Aero style (glossy, bubbly, translucent, organic) — with animations that respond to the loudness and sustain of the playing.

**Primary user:** A guitarist who wants an immersive, reactive visual experience while playing, starting on Mac, with a future deployment target of Raspberry Pi.

---

## Feature List (Behavioral Terms)

### 1. Real-Time Audio Capture
The app captures audio from a user-specified USB audio input device at low latency. It continuously reads audio in small buffers and feeds them to the pitch detection pipeline.

### 2. Pitch Detection with Noise Gate
The app detects the dominant pitch in the incoming audio. A configurable noise gate (in dBFS) filters out background noise and quiet strums — only audio above the threshold triggers note detection. Default is tuned for loud, sustained notes from a guitar amp.

### 3. Note-to-Color Mapping (Chromatic Wheel)
Each of the 12 chromatic notes maps to a color. The default mapping follows a chromatic color wheel:

| Note | Color       | Hex       |
|------|-------------|-----------|
| C    | Red         | #FF0000   |
| C#   | Red-Orange  | #FF4500   |
| D    | Orange      | #FF8C00   |
| D#   | Yellow      | #FFD700   |
| E    | Yellow-Green| #9ACD32   |
| F    | Green       | #00C800   |
| F#   | Teal        | #00CED1   |
| G    | Cyan        | #00BFFF   |
| G#   | Blue        | #1E90FF   |
| A    | Indigo      | #4B0082   |
| A#   | Violet      | #8A2BE2   |
| B    | Magenta     | #FF00FF   |

The mapping is stored in the config file and can be changed without restarting.

### 4. Smooth Color Interpolation
When a new note is detected, the background color smoothly interpolates (lerps) from the current color to the target note color. Interpolation speed is configurable.

### 5. Silence Behavior
When no note above the noise gate threshold is detected for a configurable duration, the screen slowly interpolates from the last detected note's color toward white. This communicates musical silence without an abrupt visual cut.

### 6. Ambient Animations (Frutiger Aero Style)
Translucent, glossy bubble-like shapes float across the screen at all times. Their behavior responds to audio:
- **Loud / high amplitude:** faster pulse/ripple effects, larger bubbles, more energetic movement
- **Quiet / low amplitude or silence:** slow, gentle drift, smaller bubbles, meditative pace

The overall aesthetic is calm but with popping, saturated colors — glossy and organic, not geometric or harsh.

### 7. Live Config Reload
The app watches a `config.yaml` file for changes. When the file is saved, the app reloads settings (noise gate, color mapping, timeouts, interpolation speed, audio device) without requiring a restart.

---

## Technical Requirements

### Stack
- **Language:** Python 3.11+
- **Display:** Pygame (fullscreen window)
- **Audio capture:** `sounddevice`
- **Pitch detection:** YIN algorithm implemented directly in numpy (no C extension dependency)
- **Config:** YAML (`PyYAML`)
- **Config file watching:** `watchdog`
- **Platform:** macOS (primary), Raspberry Pi OS (future target)

### Audio
- Sample rate: 44100 Hz
- Buffer size: 1024 samples (~23ms per buffer)
- Channels: Mono
- Audio device: configurable by device name or index in config

### Performance
- End-to-end latency target: < 100ms (audio in → color change on screen)
- Frame rate: 60 FPS target for animations

---

## UI/UX Parameters

- **Window:** Fullscreen, no chrome, no on-screen controls
- **Aesthetic:** Frutiger Aero — soft glows, translucent layered bubbles, smooth gradients, organic shapes
- **Color:** Full-screen solid base color with the note's hue, overlaid with semi-transparent animated bubble layers
- **Animations:** Continuously running; amplitude modulates speed and scale
- **No text on screen during normal operation**

---

## Config File (`config.yaml`) Parameters

```yaml
audio:
  device: null          # null = system default, or device name/index
  sample_rate: 44100
  buffer_size: 1024

detection:
  noise_gate_db: -20    # dBFS threshold; signals below this are ignored
  confidence_threshold: 0.6  # aubio pitch confidence minimum

display:
  fps: 60
  interpolation_speed: 0.05   # lerp factor per frame (0.0–1.0)
  silence_timeout_sec: 3.0    # seconds before fade-to-white begins
  silence_fade_speed: 0.002   # lerp factor toward white per frame

animation:
  bubble_count: 12
  bubble_min_radius: 30
  bubble_max_radius: 120
  amplitude_scale: 1.0        # multiplier for amplitude-driven effects

note_colors:
  C:  "#FF0000"
  C#: "#FF4500"
  D:  "#FF8C00"
  D#: "#FFD700"
  E:  "#9ACD32"
  F:  "#00C800"
  F#: "#00CED1"
  G:  "#00BFFF"
  G#: "#1E90FF"
  A:  "#4B0082"
  A#: "#8A2BE2"
  B:  "#FF00FF"
```

---

## Per-Feature Acceptance Criteria

### Feature 1 — Audio Capture
- [ ] App opens the configured audio device on startup
- [ ] Falls back to system default if device not found, with a console warning
- [ ] Audio is captured continuously in non-blocking mode with no gaps or buffer overruns under normal use

### Feature 2 — Pitch Detection & Noise Gate
- [ ] Notes above the noise gate threshold produce a detected pitch within 100ms
- [ ] Audio below the noise gate produces no note output
- [ ] Detected pitch maps to a chromatic note name (C, C#, D … B)
- [ ] Noise gate value is read from config and reloads live

### Feature 3 — Note-to-Color Mapping
- [ ] Each of 12 chromatic notes maps to a distinct color per config
- [ ] Changing a color in `config.yaml` and saving it updates the mapping within 1 second without restarting
- [ ] Invalid hex values in config log a warning and fall back to the previous valid color

### Feature 4 — Color Interpolation
- [ ] Background color smoothly transitions from current to target color over multiple frames
- [ ] Interpolation speed is controlled by `interpolation_speed` in config
- [ ] No visual popping or hard cuts between notes

### Feature 5 — Silence Behavior
- [ ] After `silence_timeout_sec` of no detected note, color begins fading toward white
- [ ] Fade is smooth, controlled by `silence_fade_speed`
- [ ] If a new note is detected during the fade, it snaps back to interpolating toward the new note color

### Feature 6 — Ambient Animations
- [ ] Translucent bubbles float across the screen at all times
- [ ] Bubble speed, size, and pulse rate scale with current audio amplitude
- [ ] Aesthetic matches Frutiger Aero style: glossy, soft-edged, layered
- [ ] Animations run at target FPS regardless of note detection state

### Feature 7 — Live Config Reload
- [ ] App detects changes to `config.yaml` within 1 second of the file being saved
- [ ] All config parameters reload without restarting the app
- [ ] Malformed YAML logs an error to console and keeps the previous config active
