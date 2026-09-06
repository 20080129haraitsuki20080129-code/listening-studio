# Deploying

**Not currently deployed.** This app runs locally — see `./start.sh` in the
README. What follows is kept because everything it needs is already built
(OAuth sign-in, ownership, rate limits, S3-compatible storage, a Dockerfile),
so deploying later is configuration rather than code.

Everything below is free and none of it asks for a card.

```
Netlify            Hugging Face Spaces          Supabase
(Next.js)   ---->  (FastAPI + Kokoro)   ---->   (PostgreSQL + Storage)
```

Kokoro needs PyTorch and about 1GB of memory, so the backend has to be a real
container. That rules out Netlify Functions, Vercel and every other serverless
tier for the backend -- only the frontend goes there.

**The Space has to be public for other people to use the app, and a public
Space shows its source.** The frontend stays private on GitHub either way. If
the backend source must stay private too, this stack is not the one -- a VM
(Oracle Always Free, and others) keeps it private but wants a card for identity
verification.

## 1. Supabase — database and audio storage

Free plan, no card. 500MB database, 500MB file storage, up to 2 projects.

1. Create a project and note the database password.
2. **Use a pooler connection string, not the direct one.** Direct connections
   are IPv6-only on newer projects and most hosts cannot reach them. Take the
   **Session pooler** string from Connection settings -- the transaction pooler
   breaks prepared statements, which SQLAlchemy relies on.
3. Storage → create a bucket named `listening-audio`, keep it private.
4. Storage → S3 access keys → generate one.

```bash
DATABASE_URL=postgresql+psycopg://postgres.<ref>:<password>@<pooler-host>:5432/postgres
STORAGE_BACKEND=s3
S3_BUCKET=listening-audio
S3_ENDPOINT_URL=https://<ref>.supabase.co/storage/v1/s3
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_REGION=<project region, e.g. ap-northeast-1>
```

Leave `S3_PUBLIC_BASE_URL` unset so the bucket stays private and the API serves
the bytes.

> A free project **pauses after 7 days without traffic** and has to be resumed
> by hand, and a free Space sleeps after 48 hours idle. A scheduled ping to
> `/health` keeps both awake, since the health check opens a database
> connection — a GitHub Actions cron or any free uptime monitor will do. This
> repository does not ship one, because it is currently run locally.

## 2. Sign-in — Google and/or X

Both are free to register. Configure at least one, or the app runs open to
anyone who finds the URL.

- Google: <https://console.cloud.google.com/apis/credentials>
  Authorised redirect URI: `https://<space>.hf.space/api/v1/auth/google/callback`
- X: <https://developer.x.com/en/portal/dashboard>
  Callback URI: `https://<space>.hf.space/api/v1/auth/x/callback`
  X does not release an email address at this scope, which is expected.

```bash
SESSION_SECRET=$(openssl rand -hex 32)
```

## 3. Hugging Face Space — the backend

Free CPU tier: 2 vCPU, 16GB RAM, no card. Create a **Docker** Space and push
this `backend/` directory to it.

A Space is configured by YAML at the top of its `README.md`, so prepend this to
the copy that lands in the Space:

```markdown
---
title: Listening Studio API
emoji: 🎧
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---
```

Set the variables below as **secrets**, not plain variables -- plain ones are
visible on a public Space.

```bash
APP_ENV=production
SESSION_SECRET=...
COOKIE_SECURE=true
COOKIE_SAMESITE=none          # the frontend is on another origin
FRONTEND_BASE_URL=https://<your-site>.netlify.app
DATABASE_URL=...
STORAGE_BACKEND=s3
S3_...=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

`APP_ENV=production` makes the server refuse to start if `SESSION_SECRET` is
still the default or shorter than 32 characters, or if `COOKIE_SECURE` is off.

Two things about the free tier worth knowing: the Space **sleeps after 48 hours
idle** and takes a cold start to wake, and its **disk does not survive a
restart** -- which is exactly why audio goes to Supabase rather than local
disk. A scheduled ping covers the sleeping; the storage setting covers the
disk.

## 4. Netlify — the frontend

Free plan, no card. Connect the private GitHub repository; the repository stays
private.

- Base directory: `frontend`
- Environment: `NEXT_PUBLIC_API_BASE_URL=https://<space>.hf.space/api/v1`

That value is baked in at build time, so changing it needs a rebuild.

## Checks after deploying

```bash
curl https://<space>.hf.space/api/v1/health
curl https://<space>.hf.space/api/v1/auth/status   # auth_required must be true
```

If `auth_required` is `false`, no provider is configured and **anyone with the
URL can use the instance**.

Then open the Netlify site, sign in, and generate something. The first render
after a cold start is slower while the model loads.


## What stops the instance being abused

A public URL on a free tier can be drained by one person in an afternoon, so
three things guard it, all free:

**Sign-in is mandatory in production.** The server refuses to start under
`APP_ENV=production` with no identity provider configured, because the instance
would otherwise be open to anyone who found the URL. It also refuses a default
or short `SESSION_SECRET`, and refuses cookies that are not marked secure.

**Rate limits** cap the paths that cost something: 60 renders an hour and 60
writes a minute per signed-in account, both configurable.

```bash
RATE_LIMIT_RENDERS_PER_HOUR=60   # 0 disables
RATE_LIMIT_WRITES_PER_MINUTE=60
```

Rendering is what burns CPU, storage and the monthly egress allowance, so it
is capped per account rather than per IP -- switching networks does not reset
it. Reads are not capped.

The limiter keeps its state in memory, which is exact for one process and is
what this runs as: the model sits in memory, so there is one worker by design.
Two workers would need a shared store.

**Ownership** means one account cannot read or delete another's projects, so
the worst a signed-in stranger can do is spend their own allowance.

## What none of this prevents

**A public Space shows its own source.** There is no free, card-free way to run
a container with private source that is also reachable by other people. The
choice is: accept a public backend (nothing secret is in it -- every credential
comes from environment variables, and the git history has been scanned), pay
or verify a card for a VM, or run it from your own machine over a tunnel and
keep it on.
