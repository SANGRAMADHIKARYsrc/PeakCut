# PeakCut Architecture

> **Note:** This document describes the codebase as understood from reading the source.
> Updated as the fork evolves.

## High-Level Flow

```
User (browser)
    │
    ▼
web/index.html ───── Plain HTML/CSS/JS, no build step
    │                 Calls /api/* endpoints
    ▼
studio/server.py ─── FastAPI routes + request gate
    │                 (auth, limits, headers, ctx)
    │
    ├─► studio/auth.py ──────── Session management, sign-in
    ├─► studio/account.py ───── User account operations
    ├─► studio/admin.py ─────── Admin dashboard + grant CLI
    │
    ├─► studio/ai.py ────────── ONLY file that talks to AI providers
    │   └─ PROVIDERS dict ───── gemini, openai, xai, groq, openrouter, anthropic, ollama, custom
    │
    ├─► studio/brain.py ─────── Prompts: clip selection, live judging, hooks, titles, caption fixes
    │   └─ _safe(), _text() ─── Sanitize untrusted transcript text
    │
    ├─► studio/jobs.py ──────── Video pipeline + fair queue
    │   │
    │   ├─► studio/media.py ──── Download (yt-dlp), probe, audio extraction
    │   ├─► studio/transcribe.py ── Speech-to-text (sherpa-onnx)
    │   │   └─ studio/asr_worker.py ── ASR worker (local or remote GPU)
    │   ├─► studio/render.py ──── Clip cutting, 9:16 layout, captions (ffmpeg + Pillow)
    │   └─► studio/posting.py ── Auto-post to YouTube, Instagram, TikTok
    │
    ├─► studio/live.py ──────── Live stream recording + clipping
    ├─► studio/creators.py ──── Workspace/creator management
    ├─► studio/usage.py ─────── AI call + token tracking
    ├─► studio/config.py ────── All settings from environment variables
    ├─► studio/ctx.py ────────── Request context (uid, bump for sync)
    ├─► studio/db.py ─────────── Database tables (SQLAlchemy core; SQLite or PostgreSQL)
    └─► studio/storage.py ────── Data folder paths
```

## Key Entry Points

| What | Where |
|---|---|
| A video enters the system | `studio/server.py` → upload or URL endpoint → `studio/jobs.py` |
| Job queue / next job | `studio/jobs.py` fair queue (CPU/RAM-aware scheduling) |
| Transcript stored | In the data folder, managed by `studio/transcribe.py` |
| Prompt sent to AI | `studio/brain.py` → `studio/ai.py` (returns parsed JSON + token counts) |
| Final 9:16 render (ffmpeg) | `studio/render.py` → `render_clip()` |
| Captions generated/styled | `studio/render.py` (ffmpeg drawtext/ASS filters + Pillow) |
| Frontend calls API | `web/index.html` → `fetch('/api/...')` |

## Important Rules

1. **`ctx.uid()`** — user identity always comes from the session, never the request body.
2. **`ctx.bump()`** — must be called after any change that affects what a user sees (page polls `/api/sync`).
3. **Accounts off** (`PEAKCUT_ACCOUNTS=0`): single built-in owner via `auth.local_user()`.
4. **Accounts on** (`PEAKCUT_ACCOUNTS=1`): full multi-user with sign-in.
5. **Short temp folders** for rendering — Windows 260-char path limit.
6. **Secrets** — read from env or `*_FILE` settings. Never commit.

## Data Storage

- **Data folder**: `./data` by default (or `PEAKCUT_DATA` env var)
  - Videos, clips, recordings, creators, settings
  - Speech models (~480 MB English, ~107 MB Arabic)
  - `ai.json` — saved AI settings from dashboard
  - `storage.json` — may point to external data location
- **Database**: SQLite locally, PostgreSQL on servers (`studio/db.py`)
