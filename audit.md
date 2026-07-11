# Audit — Known Bugs, Orphaned Code & PRD Divergences

## 1. Known Bugs

- **ExifToolSession created per asset in commit loop** (`app.py:358`) — A new ExifToolSession is opened inside the `for idx, row in selected.iterrows()` loop, defeating `-stay_open` persistence. Each iteration opens and closes a subprocess, adding ~200ms overhead per asset. Fix: create one session before the loop, close after.
- **HW accel detection incomplete** (`engine.py:136`) — `detect_hw_accel()` only checks `cuda` (NVIDIA) and `qsv` (Intel), missing AMD AMF and macOS VideoToolbox. CPU fallback works for all, so low severity.
- **Static images wrongly categorized as motion_graphics** — AI prompt lacks instruction to distinguish static images from video content. AI defaults to "motion_graphics" for single still frames. Fix: add prompt instruction to never assign motion-related categories to non-video assets.
- **AI storyboard grid description bleeds into output** — AI sometimes describes the 5x2 grid layout ("The asset showcases a series of frames") instead of the visual content. Fix: add prompt instruction to ignore the grid container and describe only the scene/content.

## 2. Orphaned Code

- **`dashboard.py`** — Flask-based analytics dashboard that duplicates the Streamlit analytics tab in `app.py`. Not importable from any other module. Requires `flask` which is not in `requirements.txt`. _Resolution: removed._

## 3. PRD Divergences

- **Undo/rollback (impl. plan 4.2)** — Listed as out-of-scope in `prd.md` ("No rename history or undo commit feature"). Files are copied to `~/Desktop/RenamedMedia` (originals preserved), so undo is unnecessary. _Resolution: section 4.2 removed from implementation_plan.md._
