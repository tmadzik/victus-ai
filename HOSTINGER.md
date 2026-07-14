# Deploying Victus AI on Hostinger — step‑by‑step

This puts the whole platform online at **victusdata.com** with three sub‑sites:

| URL | What it is |
| --- | --- |
| `https://www.victusdata.com` | Marketing site (the public landing page) |
| `https://app.victusdata.com` | Clinical web app (sign‑in, triage, TOI/rPPG, clinician tools) |
| `https://api.victusdata.com` | The API + database |

One command builds and starts everything; Caddy fetches free HTTPS certificates
automatically. Plan for **~20–30 minutes** end to end.

> **⚠️ Read this first — what you're sharing.** Victus AI runs as a **research
> demonstrator**. The risk models are **not clinically validated**, and the
> platform says so on every result ("Research demonstrator — NOT a medical
> device"). This deploy keeps that honest labelling **on** by design. It is a
> real, working product to show founders and investors — it is **not** cleared
> for real patient care or real patient data. Don't flip the clinical‑claims
> gate on until a validated model card exists.

---

## Which Hostinger plan you need

The platform needs **PostgreSQL** and **Python 3.12** running as real server
processes. Hostinger's shared/Business (**hPanel**) plans only offer MySQL and
can't run these — so the **whole** platform needs a **Hostinger VPS (KVM)**.

- **Recommended:** Hostinger **VPS — KVM 2** (2 vCPU, 8 GB RAM) or larger.
  KVM 1 (4 GB) works for a light demo but is tight while building images.
- When ordering, choose the **"Ubuntu 24.04 with Docker"** template (or plain
  Ubuntu 24.04 — the guide installs Docker for you).

> Shared/hPanel only? You can still host the **marketing page** there, but the
> actual app + API cannot run on it. Get the VPS for the real thing.

---

## Step 1 — Point the domain at the VPS

You need the VPS's public **IP address** (Hostinger shows it in **VPS →
Overview**). In your domain's DNS (Hostinger **Domains → DNS / Nameservers**, or
wherever `victusdata.com` is managed), add four **A records**, all pointing to
that IP:

| Type | Name | Value |
| --- | --- | --- |
| A | `@` | `<VPS_IP>` |
| A | `www` | `<VPS_IP>` |
| A | `app` | `<VPS_IP>` |
| A | `api` | `<VPS_IP>` |

DNS can take a little while to propagate. Certificates in Step 6 only succeed
once these resolve to the VPS, so do this first.

---

## Step 2 — Connect to the VPS and install Docker

From your computer (Hostinger also has a **Browser terminal** in the VPS panel):

```bash
ssh root@<VPS_IP>
```

If the Docker template wasn't used, install Docker + Compose:

```bash
curl -fsSL https://get.docker.com | sh
docker compose version   # confirm it prints a version
```

---

## Step 3 — Get the code onto the VPS

Clone the repository (or upload it — see the box below):

```bash
cd /opt
git clone <YOUR_REPO_URL> victus
cd victus
```

> **No Git remote / private repo?** From your own machine, from the project
> folder, create a tarball excluding heavy folders and copy it up:
> ```bash
> tar --exclude='**/node_modules' --exclude='**/.next' --exclude='**/.venv' \
>     --exclude='.git' -czf victus.tar.gz .
> scp victus.tar.gz root@<VPS_IP>:/opt/
> ssh root@<VPS_IP> 'mkdir -p /opt/victus && tar -xzf /opt/victus.tar.gz -C /opt/victus'
> ```

---

## Step 4 — Create the configuration

```bash
cd /opt/victus
cp infra/.env.production.example infra/.env.production
```

Generate the secrets in one shot and append them (copy‑paste this whole block):

```bash
cat >> infra/.env.production <<EOF

# --- generated $(date -u +%FT%TZ) ---
POSTGRES_PASSWORD=$(openssl rand -hex 24)
JWT_SECRET_KEY=$(openssl rand -hex 32)
INTERNAL_SERVICE_TOKEN=$(openssl rand -hex 32)
PSEUDO_SALT=$(openssl rand -hex 32)
KIOSK_ENCRYPTION_KEY=$(openssl rand -hex 32)
AUTH_SECRET=$(openssl rand -base64 48)
EOF
```

Then open `infra/.env.production` and set the two human values near the top:

```bash
nano infra/.env.production
```

- `ACME_EMAIL=` → your email (Let's Encrypt sends expiry reminders here).
- Confirm the domains say `victusdata.com` (they do by default).

> The later duplicate keys win, so the generated secrets at the bottom override
> the `CHANGE_ME` placeholders above. Leave the SMTP/WhatsApp blocks blank for
> now — they're optional. **Never commit this file.**

---

## Step 5 — Build and start the platform

```bash
docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.production up -d --build
```

First run builds three images and can take **5–15 minutes**. When it returns,
check everything is up:

```bash
docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.production ps
```

You want `postgres`, `api`, `web`, `marketing`, and `caddy` all **running**
(the API applies its database migrations automatically on start).

---

## Step 6 — Verify HTTPS and the sites

Give Caddy a minute to obtain certificates, then:

```bash
curl -s https://api.victusdata.com/healthz     # → {"status":"ok"}
curl -s https://api.victusdata.com/readyz       # → {"status":"ready"}  (DB reachable)
```

Open in a browser:
- `https://www.victusdata.com` — the marketing site.
- `https://app.victusdata.com` — the clinical app sign‑in page.

> If a site shows a certificate warning, DNS (Step 1) probably hasn't propagated
> yet — wait and reload. Watch Caddy if needed:
> `docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.production logs -f caddy`

---

## Step 7 — Create the demo accounts

So investors can click straight in:

```bash
API_URL=https://api.victusdata.com ./infra/seed-demo.sh
```

It prints two logins (a **clinician** and a **patient**, shared demo password).
Sign in at `https://app.victusdata.com`:

- **Patient** → run a **Pathway A** symptom/tape‑measure triage, and an
  **in‑browser TOI/rPPG** camera capture (needs HTTPS — Step 6 gives you that).
- **Clinician** → participant search, the **/research** console, longitudinal
  **risk & vital‑sign trajectories**, and the **rising‑risk nudges**.

---

## What to tell people you're showing

- **Two screening pathways.** A questionnaire/anthropometric triage (Pathway A)
  and a **contactless camera vital‑sign** capture (Pathway B / rPPG) — plus a
  walk‑up **Mobile Clinic Gateway** kiosk rail.
- **Uncertainty‑aware.** Every result carries the model's own confidence;
  trends are only flagged "real" when they beat that measurement noise.
- **Governance built in.** Consent, data‑subject access/erasure, audit trail,
  and maker‑checker approvals — the things a health deployment is judged on.
- **Honest by design.** It presents as a **research demonstrator**; the
  clinical‑claims gate stays closed until a model is validated.

---

## Everyday operations

```bash
cd /opt/victus
CMD="docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.production"

$CMD logs -f api          # follow API logs
$CMD ps                   # status
$CMD restart web          # restart one service
$CMD down                 # stop everything (data is preserved in volumes)
$CMD up -d --build        # apply code changes / restart

# Back up the database:
docker exec -t $($CMD ps -q postgres) pg_dump -U victus victus > backup-$(date +%F).sql
```

**Update to newer code:** `git pull` (or re‑upload), then re‑run the `up -d
--build` line — migrations re‑apply automatically.

---

## Optional extras

- **Trained model instead of the rule‑based backend.** The image ships the
  torch‑free **rule‑based** per‑disease backend (same response shape, small
  image). To run the trained checkpoint, add `torch` to the API image and set
  `VICTUS_TRIAGE_MODEL_PATH` — realistic only on a larger VPS.
- **WhatsApp capture rail.** Off by default (nothing to run). To enable, add
  the WhatsApp tokens to `infra/.env.production`, add
  `opencv-python-headless` to `apps/api/requirements-cpanel.txt`, rebuild, and
  start with `--profile whatsapp`.
- **Marketing "request a pilot" emails.** Fill the `SMTP_*` / `LEAD_NOTIFY_*`
  block in `infra/.env.production` and restart `marketing`.

---

## If something's wrong

| Symptom | Likely cause / fix |
| --- | --- |
| Cert warning / site won't load over HTTPS | DNS not propagated yet (Step 1). Wait, reload; check `logs -f caddy`. |
| `readyz` not "ready" | DB still starting or migrations running. `logs -f api`; wait ~30s and retry. |
| Clinical actions fail with 401/403 | `INTERNAL_SERVICE_TOKEN` differs between `api` and `web` — it must be one value in `.env.production`. Re‑`up -d`. |
| Out of memory during build | Use KVM 2 (8 GB), or add swap: `fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`. |
| API won't boot, mentions a placeholder secret | A secret still says `CHANGE_ME`. Regenerate (Step 4) and `up -d`. |
