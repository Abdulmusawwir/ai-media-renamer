# Privacy Policy — AI Media Renamer

**Last updated:** 2026-08-16

## Overview

AI Media Renamer is a **fully local** media management tool. All AI analysis, file operations, and data processing happen entirely on your machine. **No user data is collected, stored, or transmitted to any external service.**

## What We Do Not Collect

| Data | Why |
|------|-----|
| File names, paths, or content | Your media stays on your machine |
| AI prompts or responses | Could contain copyrighted or personal information |
| Thumbnails, video frames, or audio | Your actual media content is never uploaded |
| Usage analytics or telemetry | We have no analytics or telemetry system |
| IP addresses, hostnames, or usernames | No tracking of any kind |
| API keys or tokens | Security risk — never collected |

## Data Security

- **No data leaves your machine** — AI calls go directly from your app to your local runtime (llama.cpp or Ollama); no network request is ever made for analysis
- **No API keys, no keychain** — since v1.7.0 the app has no cloud providers and stores no API keys, so there is nothing to leak
- **Loopback-only by default** — the web server binds to `127.0.0.1`, so it is not reachable from your local network unless you explicitly enable LAN exposure in Configuration
- **No cookies, fingerprinting, or tracking**
- **No third-party analytics or telemetry services**
- **Logs** are written locally to `%APPDATA%/ai-media-renamer/logs/`, are never transmitted, and strip absolute paths by default (`redact_paths`); secrets are masked everywhere they could appear

## Changes to This Policy

All changes are tracked in the project's git history.

## Contact

For privacy questions, open an issue at:
https://github.com/Abdulmusawwir/ai-media-renamer/issues
