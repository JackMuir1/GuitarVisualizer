# CLAUDE.md — Guitar Visualizer

See [PRD.md](./PRD.md) for full product requirements, feature list, and acceptance criteria.

---

## Stack & Key Libraries

| Concern          | Library / Tool         |
|------------------|------------------------|
| Display          | `pygame`               |
| Audio capture    | `sounddevice`          |
| Pitch detection  | YIN algorithm (numpy)  |
| Config format    | YAML via `PyYAML`      |
| Config watching  | `watchdog`             |
| Python version   | 3.11+                  |

---

## File Structure

```
Guitar_Visualizer/
├── CLAUDE.md
├── PRD.md
├── README.md
├── config.yaml              # Live-reloadable user config
├── requirements.txt
├── main.py                  # Entry point: init and game loop
└── src/
    ├── audio.py             # Audio capture and pitch detection
    ├── color.py             # Note-to-color mapping and interpolation
    ├── config_loader.py     # Config loading, validation, file watching
    ├── animation.py         # Bubble/ambient animation rendering
    └── visualizer.py        # Pygame display and main render loop
```

---

## Code Conventions

### Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions and variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- No abbreviations except well-known ones (`fps`, `db`, `hz`)

### Imports
- Standard library first, then third-party, then local — separated by blank lines
- Local imports use relative paths within `src/`: `from src.color import ColorMapper`
- No wildcard imports (`from x import *`)

### Style
- Type hints on all function signatures
- Keep functions short and single-purpose
- No inline comments unless the logic is non-obvious; prefer clear naming
- Config values are never hardcoded — always read from the config object

### Error Handling
- Audio device errors: log warning, fall back to default, do not crash
- Config parse errors: log error, retain previous valid config, do not crash
- All other unexpected exceptions: log with traceback, attempt graceful shutdown

---

## Dev Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
python main.py

# Run with a specific config file (future flag)
python main.py --config config.yaml
```

---

## Always Do

- Read config values through the `ConfigLoader` object — never open `config.yaml` directly in feature code
- Keep audio processing and rendering on separate threads/callbacks to minimize latency
- Use `aubio`'s YIN algorithm for pitch detection (lowest latency)
- Lerp all visual transitions — never set colors or positions with a hard cut
- Target 60 FPS in the Pygame loop; decouple audio callback timing from frame rate
- Log meaningful warnings when config values are invalid or out of expected range
- Use `yaml.safe_load()` exclusively — never bare `yaml.load()`
- Validate and clamp all config values to expected types and ranges before use
- Validate audio buffer shape and dtype in the callback before passing to aubio

## Never Do

- Never block the audio callback thread with rendering or file I/O
- Never hardcode note colors, thresholds, or timing values in source code
- Never crash on a missing or malformed `config.yaml` — always fall back gracefully
- Never add on-screen UI controls — the visualizer is always fullscreen and control-free
- Never use `time.sleep()` in the main render loop
- Never commit `config.yaml` with personal device settings — keep it as the default template
- Never call `yaml.load()` without a Loader — always use `yaml.safe_load()`
- Never eval, exec, or dynamically import anything from config values
- Never trust audio buffer dimensions without checking shape and dtype first
