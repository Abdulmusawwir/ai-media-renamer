# Privacy Policy — AI Media Renamer

**Last updated:** 2026-07-19

## Overview

AI Media Renamer is a local-first media management tool. All AI analysis and file operations happen on your machine. We do not upload your files, media content, or personal data to any server.

## Optional Anonymous Telemetry

When you opt in, AI Media Renamer sends **anonymous usage data** to help us fix bugs, prioritize features, and improve the app. This is entirely optional and can be changed anytime in **Settings > Telemetry**.

### What We Collect

| Event Type | Example Data | Why |
|------------|--------------|-----|
| `ai_rating` | `{outcome: "thumbs_up", profile: "cinematography", model: "qwen2.5vl:7b", provider: "ollama"}` | Measure AI suggestion quality |
| `session_complete` | `{files_analyzed: 12, files_committed: 10, profile: "general_balanced", case_style: "kebab-case"}` | Understand usage patterns |
| `error` | `{error_type: "ffmpeg_timeout", model: "gpt-4o", provider: "openai"}` | Fix bugs and reliability issues |
| `opt_in` / `opt_out` | `{}` | Respect your preferences |
| `app_version` | `{version: "v1.3.0", os: "win32", arch: "AMD64"}` | Compatibility tracking |

### What We NEVER Collect

| Data | Why We Don't Collect It |
|------|--------------------------|
| File names or paths | Reveals your folder structure, project names, and content subjects |
| AI prompts or responses | Could contain copyrighted content or personal information |
| Thumbnails or video frames | Your actual media content |
| Original vs. renamed filenames | Reveals content semantics |
| IP addresses | Personally identifiable |
| Hostnames or usernames | Personally identifiable |
| API keys or tokens | Security risk |
| Free-text error messages | Could echo file paths or content |

### How Data Is Processed

1. Events are queued locally in `%APPDATA%/ai-media-renamer/telemetry.jsonl`
2. On app exit (or every 50 events), events are sent via HTTPS to **PostHog** (US region)
3. PostHog stores events with a **1-year retention** period
4. Each install gets a random UUID — not tied to any external identifier
5. Session IDs reset every app launch

### How to Opt Out

1. Open **Configuration** tab in the app
2. Toggle **"Send anonymous usage data"** to off
3. A final `opt_out` event is sent, then no more data is transmitted

Your local telemetry buffer (`telemetry.jsonl`) is deleted after successful upload.

### How to Delete Your Data

- **Local buffer:** Delete `%APPDATA%/ai-media-renamer/telemetry.jsonl`
- **Install ID:** Delete `%APPDATA%/ai-media-renamer/.install_id` — a new random UUID will be generated
- **PostHog data:** Contact us at the GitHub repository to request deletion

## Data Security

- **In transit:** All telemetry data is sent over HTTPS (TLS 1.3)
- **At rest:** The local telemetry file contains no PII — just event types and config names
- **No tracking:** We do not use cookies, fingerprinting, or cross-session tracking
- **No third-party analytics:** We use PostHog as our sole analytics provider

## Changes to This Policy

We will update this document when the telemetry schema changes. All changes are tracked in the project's git history.

## Contact

For privacy questions or data deletion requests, open an issue at:
https://github.com/Abdulmusawwir/ai-media-renamer/issues
