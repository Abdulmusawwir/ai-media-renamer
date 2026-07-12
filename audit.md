# Audit — Known Bugs, Orphaned Code & PRD Divergences

## 1. Known Bugs

- **ExifToolSession created per asset in commit loop** (`app.py:358`) — A new ExifToolSession is opened inside the `for idx, row in selected.iterrows()` loop, defeating `-stay_open` persistence. Each iteration opens and closes a subprocess, adding ~200ms overhead per asset. Fix: create one session before the loop, close after.
- ~~**VISION_MODEL_PREFIXES included "qwen2" which matched non-vision models** (`engine.py:402`) — `qwen2` prefix matched `qwen2.5-coder` (code model), causing it to appear in the model dropdown.~~ _Fix: narrowed to `"qwen2.5vl"` and `"qwen2-vl"`._
- ~~**HW accel detection incomplete** (`engine.py:136`) — `detect_hw_accel()` only checks `cuda` (NVIDIA) and `qsv` (Intel), missing AMD AMF and macOS VideoToolbox.~~ _Fix: added `'amf'` to the detection list. macOS VideoToolbox remains missing (secondary platform, low priority)._
- ~~**Static images wrongly categorized as motion_graphics** — AI prompt lacked instruction to distinguish static images from video content.~~ _Fix: added CRITICAL OUTPUT RULES to `config.json` prompt instructing AI to never categorize static images as motion_graphics, glitch_vfx, timelapse, slow_motion, or cinemagraphs._
- ~~**AI storyboard grid description bleeds into output** — AI described the grid layout instead of content.~~ _Fix: added prompt rule: "NEVER describe the storyboard grid layout... Describe ONLY the visual content."_

## 2. Orphaned Code

- **`dashboard.py`** — Flask-based analytics dashboard that duplicates the Streamlit analytics tab in `app.py`. Not importable from any other module. Requires `flask` which is not in `requirements.txt`. _Resolution: removed._

## 3. PRD Divergences

- **Undo/rollback (impl. plan 4.2)** — Listed as out-of-scope in `prd.md` ("No rename history or undo commit feature"). Files are copied to `~/Desktop/RenamedMedia` (originals preserved), so undo is unnecessary. _Resolution: section 4.2 removed from implementation_plan.md._
- **Cloud providers untested** — Gemini, OpenAI, Anthropic, Groq, and OpenRouter are implemented but disabled in the UI (`app.py:_on_provider_switch` rejects non-ollama selections). No API keys available for testing. _Resolution: disabled until API keys and test credentials are provided._
