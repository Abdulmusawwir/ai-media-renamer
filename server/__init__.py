"""AI Media Renamer - v2 FastAPI backend package.

Wraps ``engine.py`` (the pure importable core) behind a REST + WebSocket API
so a future React frontend can drive the app over HTTP. The server must never
duplicate engine business logic; it only orchestrates engine functions.
"""

__version__ = "2.0.0"
