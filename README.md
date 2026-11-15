# ClipForge

Turn long videos (gameplay streams, podcasts, vlogs) into short, captioned, vertical clips ready for TikTok, Reels and Shorts. Inspired by OpusClip.

**What it does**
- **Paste a link or upload.** Import from YouTube, TikTok, Instagram, X, Twitch, Facebook, Vimeo, Google Drive or a direct video URL (via yt-dlp), or upload a file. With *Auto-process* on, one click imports the video and starts clipping.
- **Recipes**: Viral clips, Gaming highlights, Podcast clips, Captions only, Reframe only.
- **Folders** to organise projects: create, rename, recolor, delete (projects are kept), drag a project card onto a folder to move it, search.
- **Analytics**: projects, clips, rendered minutes, virality-score distribution, daily activity, source platforms, top clips and hashtags, plus follower trends for connected accounts.
- **Social accounts**: connect YouTube, TikTok, Instagram and X with OAuth (read-only profile and stats).
- **Finds viral moments.** Two layers:
  1. *Signals* (always on, no AI needed): audio excitement spikes (explosions, crashes, screams), bursts of scene cuts (chases, chaos) and hype words in speech ("no way", "let's go", "bro"...). This works well on gameplay with little talking.
  2. *AI ranking* (optional): an LLM reads the timestamped transcript and the signal candidates. It then picks and trims clips and writes a title, a hook, a 0–100 virality score, a reason and hashtags.
- **Transcribes locally** with faster-whisper (word-level timestamps). No transcription API is needed.
- **Animated captions** burned in word by word (Bold / Neon / Boxed / Minimal styles), plus a hook title for the first 3 seconds.
- **Resizes** to 9:16, 1:1, 4:5 or 16:9 with three reframe modes: blurred background fill, crop-to-fill with an adjustable crop position (with a live crop box in the editor), or letterbox.
- **Clip editor**: change start/end, title, hook, hashtags, format, and caption style or height, then re-render.
- **Captions/resize only**: turn the whole video, or a range you mark, into one clip.
- **Excitement heat bar** on the timeline, showing where the action is and where the clips sit.

## Accounts and database (Supabase)

ClipForge uses **Supabase** for sign-in and for all its data. Project `clipforge` (ref `lmninfyrounbtwxncsfk`) holds:

| Table | What | Access |
|---|---|---|
| `projects` | each video project, its status and clips (JSON) | owner can read; server writes |
| `folders` | project folders | owner can read; server writes |
| `posts` | social posting history | owner can read; server writes |
| `social_connections` | OAuth tokens for YouTube/TikTok/Instagram/X | server only (RLS, no policies) |

Row Level Security is on for every table. Videos, transcripts and rendered clips stay on this computer in `data/projects/<id>/` (ffmpeg needs local files and they're far larger than free-tier storage).

**Setup**
1. `backend/.env` already has `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`. Add `SUPABASE_SECRET_KEY` from *Dashboard → Project Settings → API Keys → Secret keys*, then restart. It is server-only; never put it in frontend code.
2. *Authentication → URL Configuration*: set **Site URL** to `http://127.0.0.1:8000` (or your public URL) and add `http://127.0.0.1:8000/**` to **Redirect URLs**, so confirmation and reset emails come back to ClipForge.
3. Supabase's built-in email sender is rate-limited and meant for testing. For real users, add your own SMTP under *Authentication → Emails → SMTP Settings*, or turn off *Confirm email* under *Sign In / Providers → Email* for a private install.

**How sign-in works:** the browser signs in with supabase-js (email + password, confirmation and password-reset emails by Supabase). It passes the access token to `POST /api/auth/session`, which verifies it with Supabase and keeps it in an HttpOnly cookie so video files load too; supabase-js refreshes it hourly. The first account to sign in imports the projects and folders saved by older, file-based versions of ClipForge (a one-time step recorded in `data/imported_to_supabase.json`).

## Subscriptions (Stripe)

Plans are defined in `backend/app/billing.py` (`PLANS`): **Free** 3 videos/month, **Pro** $19/mo or $190/yr with 30 videos/month, **Business** $49/mo or $490/yr, unlimited. Each imported link or uploaded file counts as one video; counts reset on the 1st (UTC). Subscription state lives in the Supabase table `subscriptions`.

**Setup (test mode first)**
1. Stripe dashboard → *Developers → API keys*: put the test secret key in `backend/.env` as `STRIPE_SECRET_KEY=sk_test_...`.
2. Create the products and prices: `cd backend` then `.venv\Scripts\python scripts\stripe_setup.py` (safe to re-run; re-run after changing prices).
3. *Settings → Billing → Customer portal*: turn it on and allow cancelling and switching between the ClipForge prices.
4. Webhook: locally run `stripe listen --forward-to 127.0.0.1:8000/api/billing/webhook` (Stripe CLI) and put the printed `whsec_...` in `STRIPE_WEBHOOK_SECRET`. When deployed, add an endpoint `<PUBLIC_URL>/api/billing/webhook` for `checkout.session.completed` and `customer.subscription.*`.
5. Restart ClipForge. Test card: `4242 4242 4242 4242`, any future date, any CVC.

Upgrades also sync directly when the customer returns from Checkout, so they show up even before the webhook is configured; cancellations and renewals need the webhook. Going live: repeat with the live key (`sk_live_...`) and a live webhook endpoint served over https.

## Run it (Windows)

1. Install **Python 3.10+** and **ffmpeg**: `winget install Gyan.FFmpeg`, then restart the terminal and check `ffmpeg -version`.
2. Double-click `run.bat`. The first run creates a virtualenv and installs dependencies. It then opens http://127.0.0.1:8000.
3. On the first analysis, Whisper downloads its model (~500 MB for `small`) once.

macOS/Linux: `./run.sh`.

Optional: copy `backend/.env.example` to `backend/.env` to change the Whisper size, encoding, or a server-side LLM.

## Importing from links

Link import uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) (installed by `requirements.txt`) and needs ffmpeg to merge audio and video. Downloads are capped at `IMPORT_MAX_HEIGHT` (1080p) and `MAX_IMPORT_MINUTES` (240).
Instagram and some X/TikTok posts only download when you're logged in. Set `YTDLP_COOKIES_FROM_BROWSER=chrome` (or `edge`, `firefox`, `brave`) in `backend/.env` to reuse your browser's login.
Sites change often; if imports start failing, update yt-dlp: `backend\.venv\Scripts\pip install -U yt-dlp`.

## Connecting social accounts

Once an account is connected, press **Post** on any rendered clip, tick the accounts, write one caption and ClipForge uploads to all of them at the same time with live progress. Links to the live posts appear on the clip card and under **Social accounts → Recent posts** (stored in `data/posts.json`).

What each network allows through its API:
- **YouTube**: uploads as a Short (vertical, up to 3 min). Apps that Google hasn't audited upload as **private** until you pass the YouTube API compliance audit.
- **TikTok**: Direct Post. Apps that TikTok hasn't audited can only post as **Only me**; ClipForge falls back to that automatically and tells you. Clips must be 3 s to 10 min.
- **Instagram**: posts as a Reel (3 s to 15 min). Business or Creator accounts only.
- **X**: videos up to 140 s; captions are cut to 280 characters. Posting needs API access that includes writes and media upload (check your X API plan).

Accounts connected before posting was added need one **Reconnect** to grant the upload permission.

Each network needs a developer app created by whoever runs the server. Open **Social accounts → How to set up** in the app for step-by-step instructions and the redirect URI to copy.

| Network | `.env` keys | Notes |
|---|---|---|
| YouTube | `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` | Google Cloud OAuth "Web application" client, YouTube Data API v3 enabled |
| TikTok | `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | Login Kit; scopes `user.info.basic,user.info.profile,user.info.stats`; **https redirect required** |
| Instagram | `INSTAGRAM_APP_ID`, `INSTAGRAM_APP_SECRET` | Meta app, "Instagram API with Instagram login"; Business/Creator accounts only; **https redirect required** |
| X | `X_CLIENT_ID`, `X_CLIENT_SECRET` | OAuth 2.0 "Web App" with PKCE; scopes `tweet.read users.read offline.access` |

The redirect URI is `<PUBLIC_URL>/api/social/<youtube|tiktok|instagram|x>/callback`. For TikTok and Instagram, run a tunnel (`cloudflared tunnel --url http://127.0.0.1:8000` or ngrok) and set `PUBLIC_URL` to its https address.
Tokens are stored server-side in `data/connections.json` (git-ignored) and never sent to the browser. Stats refresh on demand and every ~6 hours when you open Analytics, which builds the follower-trend history.

## Connecting an AI model

Click **Connect AI** in the top-right.

| Option | Who pays | Setup |
|---|---|---|
| **Claude (bring your own key)** | each user | User pastes an API key from console.anthropic.com. It is stored only in their browser and sent with each analysis. The server never saves it. |
| **Custom / self-hosted** | you or user | Any OpenAI-compatible endpoint: Ollama, vLLM, LM Studio, OpenRouter, your own fine-tune. |
| **Server default** | you | Set `LLM_PROVIDER` etc. in `backend/.env`. It's used when a user hasn't connected their own. |
| **None** | free | Signals-only ranking. |

> **Why not "log in with your Claude subscription"?** Anthropic's terms (updated Feb 2026) limit Claude Free/Pro/Max subscription logins to Claude Code and Claude.ai. Third-party apps must use API keys. Building subscription login would break the terms and get users' accounts flagged. So this app uses bring-your-own API key.

### Swapping in your own LLM later
All prompting and parsing lives in `backend/app/pipeline/moments.py`. A provider only has to implement `complete(system, user) -> str`:

```python
# backend/app/llm/my_model.py
from .base import LLMProvider
class MyModel(LLMProvider):
    name = "my_model"
    def complete(self, system, user, max_tokens=4000):
        return my_inference(system, user)
```
Register it in `llm/registry.py` (`PROVIDERS["my_model"] = MyModel`) and set `LLM_PROVIDER=my_model`. If your model is served behind an OpenAI-compatible API (vLLM, SGLang, Ollama), you don't need code: just set `LLM_PROVIDER=openai_compat`.

## Project layout
```
backend/app/
  main.py              FastAPI routes + background jobs
  store.py             file-based project store (data/projects/<id>/) + folders
  social.py            OAuth + profile stats for YouTube, TikTok, Instagram, X
  analytics.py         workspace analytics
  llm/                 provider layer: anthropic, openai_compat, registry
  pipeline/
    media.py           ffmpeg/ffprobe helpers
    transcribe.py      faster-whisper, word timestamps
    signals.py         loudness + scene-cut signals
    moments.py         candidate scoring + LLM ranking
    importer.py        link import via yt-dlp
    captions.py        animated ASS captions
    render.py          cut + reframe + caption in one ffmpeg pass
frontend/              no-build HTML/CSS/JS single page app
```

## API (for automation)
- `POST /api/projects`: multipart `file` upload (optional `folder` field)
- `POST /api/projects/import`: `{url, folder, after:{mode: analyze|whole|none, analyze:{...}, render:{...}}}`
- `POST /api/projects/{id}/autorun`: same `after` body, for uploaded files; `POST .../retry-import`
- `PATCH /api/projects/{id}`: `{name, folder}` (`folder: ""` = unsorted)
- `GET/POST /api/folders`, `PATCH/DELETE /api/folders/{fid}`
- `GET /api/analytics?days=30`
- `GET /api/social`, `GET /api/social/{net}/connect`, `POST /api/social/{net}/refresh`, `DELETE /api/social/{net}`
- `POST /api/projects/{id}/analyze`: `{min_len, max_len, count, context, auto_render, render:{...}, llm:{provider, api_key, model, base_url}}`
- `GET /api/projects/{id}`: status, progress, clips
- `POST /api/projects/{id}/clips`: manual clip `{start, end, title}`
- `PATCH /api/projects/{id}/clips/{cid}`, then `POST .../render` with `{aspect, fit, crop_x, captions, caption_style, caption_position, show_hook}`
- `GET /media/{id}/clips/{file}?download=1&name=my-clip.mp4`

## Roadmap ideas
- Auto-reframe that tracks faces or the player car (MediaPipe / YOLO) instead of a fixed crop position
- Editable caption text per word, emoji and keyword highlighting
- Facecam + gameplay split layout for streams
- Scheduled posting and posting several clips in one go
- Background job queue (RQ/Celery) and user accounts for multi-user hosting

## Content note
Clip footage you own or have rights to. For GTA 6 and other games, check the publisher's video policy before you monetize.
