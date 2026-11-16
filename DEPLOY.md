# Deploying ClipForge on Cloudflare

This guide runs ClipForge entirely on Cloudflare, with no server of your own:

```
Browser ──> Cloudflare Worker ──┬── frontend files (Workers Static Assets, served from the edge)
                                └── /api/*, /media/* ──> Durable Object ──> Container (the Python app:
                                                                            ffmpeg, Whisper, yt-dlp)
Browser <── uploads / playback via signed links ──> R2 bucket <── the Container reads + writes media
                       Supabase (sign-in + database) · Stripe (billing) · Groq (speech-to-text)
```

**Why a Container and not just a Worker:** a Worker runs JavaScript only, but ClipForge needs Python, ffmpeg, Whisper and yt-dlp. A Cloudflare Container runs the app's normal Docker image, started and stopped by the Worker.

**How it behaves**
- **One container serves everyone.** The app keeps job progress in memory, so all requests go to the same container.
- **Sleeping:** the container sleeps about 10–15 minutes after the last request and wakes on the next one. Waking takes roughly 10–30 seconds, during which the app shows *"ClipForge is starting up"*.
- **Running jobs keep it awake.** Imports, analyses, renders and posting continue even if the user closes the tab.
- **The container's disk is wiped when it sleeps**, which is why every video, thumbnail, transcript and clip lives in the R2 bucket.

## What it costs

| Piece | Cost |
|---|---|
| **Workers Paid plan** (required for Containers) | $5/month. Includes 25 GiB-hours of memory, 375 vCPU-minutes and 200 GB-hours of container disk each month, plus 10 M Worker requests. |
| Container time beyond that | Memory about $0.009 per GiB-hour, CPU about $0.072 per vCPU-hour (billed only while busy), disk about $0.00025 per GB-hour. You pay only while it's awake. |
| R2 | free up to 10 GB, then $0.015/GB-month; downloads free |
| Supabase / Stripe / Groq | free tier / per payment / about $0.04 per hour of audio |
| Custom domain (optional) | about $10/year; `*.workers.dev` is free |

**Example:** with the default `standard-2` container (1 vCPU, 6 GiB RAM) awake about 2 hours a day, expect roughly **$5 + $5 = $10/month**. Left awake 24/7, it would be closer to $50/month. The sleep behaviour is what keeps it cheap.

Check current rates on the [Containers pricing page](https://developers.cloudflare.com/containers/pricing/).

## What you need on your PC

- **Node.js 20+** (you have it).
- **Docker Desktop, running.** `wrangler deploy` builds the app image with it; check with `docker info`. Use the default Linux containers on x86-64, because Cloudflare runs `linux/amd64` images.
- The project's **Python venv**, `backend\.venv`, made by `run.bat`, for the bucket setup script.
- A Cloudflare account, plus the Supabase project, Stripe, and a Groq key.

---

## 1. Turn on Workers Paid

Cloudflare dashboard → **Workers & Pages → Plans** → **Workers Paid** ($5/month). Containers are not available on the free plan.

## 2. Create the R2 bucket

1. Dashboard → **R2 Object Storage**, and activate it if asked.
2. **Create bucket**, name it `clipforge-media`, and keep it **private** (no public access).
3. **R2 → Manage API tokens → Create API token**:
   - **Permissions:** Object Read & Write
   - **Bucket:** only `clipforge-media`
   - Copy the **Access Key ID**, **Secret Access Key** and **S3 endpoint** (`https://<account-id>.r2.cloudflarestorage.com`).

## 3. Log in and install

In PowerShell:

```powershell
cd C:\Users\<you>\Downloads\clipforge\clipforge\cloudflare
npm install
npx wrangler login          # opens the browser; allow access
npx wrangler whoami         # note your account and workers.dev subdomain
```

## 4. Fill in the settings

```powershell
copy secrets.env.example secrets.env
notepad secrets.env
```

Fill in every value:

- **`PUBLIC_URL`:** `https://clipforge.<your-subdomain>.workers.dev`, using the subdomain from `wrangler whoami` or the dashboard under *Workers & Pages → Overview → Subdomain*. If you'll use a custom domain (step 9), put that here instead.
- **`SUPABASE_SECRET_KEY`:** a fresh secret key from Supabase → *Project Settings → API Keys*.
- **The five `S3_` values** from step 2.
- **`GROQ_API_KEY`** and **`STRIPE_SECRET_KEY`** (`sk_test_...` for now). Leave `STRIPE_WEBHOOK_SECRET` empty until step 7.

`secrets.env` is git-ignored. Never commit it.

To change the container size, edit `CONTAINER_INSTANCE` in [cloudflare/wrangler.jsonc](cloudflare/wrangler.jsonc): `standard-1`, `standard-2` (default), `standard-3` or `standard-4`. Bigger renders faster and costs more per awake hour.

## 5. Set the bucket's CORS rule

Browsers upload straight to R2, so the bucket must accept requests from your site:

```powershell
cd ..\backend
.venv\Scripts\python scripts\bucket_setup.py --env-file ..\cloudflare\secrets.env
cd ..\cloudflare
```

It checks the R2 keys and sets the rule. If it says *Could not set CORS automatically*, paste the rule it prints into **R2 → clipforge-media → Settings → CORS Policy**.

## 6. Deploy

Docker Desktop must be running.

```powershell
npx wrangler deploy        # builds the Docker image (first time ~5–10 min), uploads Worker + image
npm run secrets            # uploads secrets.env as Worker secrets
```

`wrangler deploy` prints your URL. **Wait a few minutes after the first deploy** while Cloudflare provisions the container, then open the URL. The first page load is instant (static files); signing in wakes the container.

Check status:
- `npx wrangler containers list`
- Dashboard → **Workers & Pages → Containers** (logs and metrics)
- `npx wrangler tail` for live Worker logs

## 7. Point Supabase and Stripe at it

**Supabase:** **Authentication → URL Configuration**.
- **Site URL:** your `PUBLIC_URL`
- **Redirect URLs:** add `<PUBLIC_URL>/**`
- For real users, set up SMTP under **Authentication → Emails**. The built-in sender is for testing only.

**Stripe** (test mode first):
1. Create the products and prices once from your PC: `cd ..\backend` then `.venv\Scripts\python scripts\stripe_setup.py`. It uses `STRIPE_SECRET_KEY` from `backend\.env`, so put the same key there.
2. **Developers → Webhooks → Add endpoint:**
   - URL: `<PUBLIC_URL>/api/billing/webhook`
   - Events: `checkout.session.completed`, `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`
3. Put the signing secret (`whsec_...`) in `secrets.env` as `STRIPE_WEBHOOK_SECRET`, then run `npm run secrets` again.
4. **Settings → Billing → Customer portal:** turn it on.

Changing secrets doesn't need a redeploy. The container restarts with the new values the next time it's idle.

## 8. Social accounts (optional)

Register `<PUBLIC_URL>/api/social/<youtube|tiktok|instagram|x>/callback` in each network's developer console, add the keys to `secrets.env` (see README → *Connecting social accounts*), and run `npm run secrets`.

## 9. Custom domain (optional)

1. Add the domain to Cloudflare (**Add a site**, Free plan, change nameservers), or buy it in **Domain Registration**.
2. **Workers & Pages → clipforge → Settings → Domains & Routes → Add → Custom domain**, for example `clip.example.com`.
3. Set `PUBLIC_URL=https://clip.example.com` in `secrets.env`, then run `npm run secrets`.
4. Re-run the bucket script from step 5 so the CORS rule allows the new address.
5. Update the Supabase URLs, the Stripe webhook and the social redirect URIs to the new address.

## 10. Check that it works

- [ ] Sign up, confirm the email, sign in. The first request after a sleep takes a few seconds.
- [ ] Upload a video **larger than 100 MB**: the bar reaches 100%, then "Checking video".
- [ ] Import a YouTube link
- [ ] Analyze, then **close the tab**. Come back 10 minutes later: the clips are rendered.
- [ ] Play a clip, download one, and use **Download all**
- [ ] R2 shows files under `projects/<id>/`
- [ ] Test-card upgrade (`4242 4242 4242 4242`); the Stripe webhook shows a 200 response

---

## Everyday commands (in `cloudflare\`)

| Task | Command |
|---|---|
| Deploy code changes (app or Worker) | `npx wrangler deploy` |
| Change settings / keys | edit `secrets.env`, then `npm run secrets` |
| Live logs | `npx wrangler tail`, or dashboard → Containers → Logs |
| Container status | `npx wrangler containers list` |
| Roll back the Worker | `npx wrangler rollback` |

After a deploy, the running container switches to the new version **the next time it's idle**. It never restarts in the middle of a job.

## Troubleshooting

- **`wrangler deploy` says the Docker CLI could not be launched:** start Docker Desktop and wait until `docker info` works.
- **"ClipForge is starting up" for more than a minute:** check dashboard → **Containers → Logs**. Usually a secret is missing or wrong, for example a Supabase key, which makes the app fail at startup.
- **Errors right after the first deploy:** wait a few minutes; Cloudflare is still provisioning the container.
- **Uploads fail right away ("storage said 403" or a network error):** the R2 CORS rule doesn't match `PUBLIC_URL`. Re-run step 5 with the exact URL, without a trailing slash.
- **Jobs show "ClipForge restarted while this video was being processed":** the container was replaced or crashed mid-job, for example from running out of memory on long videos. Press *Try again*. If it keeps happening, use `standard-3` and make sure `GROQ_API_KEY` is set, so transcription doesn't run on the container's CPU.
- **Instagram or private-post imports fail:** the container has no logged-in browser. Upload those videos as files instead.

## Limits to know about

- **One container serves all users,** so jobs from different people share its CPU. That's fine for a small user base. More would need a job queue and several containers, which the app doesn't have yet.
- **Wake-up delay:** the first request after a sleep takes about 10–30 seconds.
- **Uploads:** up to about 5 GB per file (`MAX_UPLOAD_MB` caps it lower if you like). Link imports have no size limit beyond `MAX_IMPORT_MINUTES`.
- **Snapshots, scaling to many containers, and a persistent Whisper model cache** are not used. With Groq set, the local Whisper model is only downloaded if Groq fails.

---

## Running it on your own server instead

`docker-compose.cloudflare.yml` runs the same app on any Linux server behind a Cloudflare Tunnel, and `docker-compose.yml` runs it behind Caddy. Both keep media in R2 when the `S3_*` settings are in `backend/.env`.

On the server: install Docker, clone the repo, create `backend/.env` from `cloudflare/secrets.env.example`, put `COMPOSE_FILE=docker-compose.cloudflare.yml` and `TUNNEL_TOKEN=...` in `.env` (tunnel from *Zero Trust → Networks → Tunnels*, hostname pointing at `http://app:8000`), then run `docker compose up -d --build`.
