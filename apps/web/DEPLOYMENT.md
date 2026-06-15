# Deploying the clinical web app to cPanel

The clinical app (`@victus/web`) ships as a **self-contained Node.js bundle**
(Next.js standalone output, production `node_modules` included). The cPanel host
never runs `npm install` — you build locally, upload one zip, and point
Passenger at it. This mirrors the marketing site's flow
([apps/marketing/DEPLOYMENT.md](../marketing/DEPLOYMENT.md)).

> **This app is the front-end only.** It talks to the FastAPI backend
> (`apps/api`) server-to-server over HTTPS. **Deploy the API first** and have
> its public URL + `INTERNAL_SERVICE_TOKEN` ready — the web app is non-functional
> without a reachable API.

> **Host requirements:** cPanel with **"Setup Node.js App"** (CloudLinux Node.js
> Selector / Passenger) and **Node.js 20 or newer**. The app uses Auth.js
> sessions and React Server Actions, so a static docroot is **not** enough — the
> Node.js application feature is required. **HTTPS is mandatory** (the TOI/rPPG
> pathway needs camera access, which browsers only grant on secure origins).

## Domain topology

| Hostname             | Serves                       | Lives where                          |
| -------------------- | ---------------------------- | ------------------------------------ |
| `app.victusdata.com` | This clinical app            | cPanel Node.js app (this guide)      |
| `api.victusdata.com` | The FastAPI backend          | Separate deployment (`apps/api`)     |
| `www.victusdata.com` | Marketing site               | `apps/marketing` (its own guide)     |

The marketing site's **Sign In** button already points at
`https://app.victusdata.com/login`, so once this app is live over the
`app` subdomain placeholder, that link starts working.

## 1. Build the bundle (local machine)

Build on **Node 20** so the bundle matches the cPanel runtime (pinned in
`.nvmrc`):

```bash
nvm use            # selects Node 20 (per .nvmrc) — or `nvm install 20` first
corepack enable    # once per machine, activates the pinned pnpm

# From the repo root. NEXT_PUBLIC_API_BASE_URL is inlined at build time —
# set it to the real API origin BEFORE building.
NEXT_PUBLIC_API_BASE_URL=https://api.victusdata.com \
  pnpm --filter @victus/web build:cpanel
```

Output: `apps/web/dist-cpanel/victus-web-cpanel.zip`

Optional local smoke test of the exact bundle (set the runtime vars inline):

```bash
PORT=3000 \
AUTH_SECRET=dev-secret \
AUTH_URL=http://localhost:3000 \
AUTH_TRUST_HOST=true \
INTERNAL_API_BASE_URL=http://127.0.0.1:8099 \
INTERNAL_SERVICE_TOKEN=dev-internal-token \
  node apps/web/.next/standalone/app.js
# → http://localhost:3000
```

## 2. Create the Node.js app in cPanel

1. cPanel → **Setup Node.js App** → **Create Application**
   - **Node.js version:** 20.x (or newer)
   - **Application mode:** Production
   - **Application root:** e.g. `victus-app` (a folder in your home directory —
     _not_ inside `public_html`)
   - **Application URL:** `app.victusdata.com`
   - **Application startup file:** `app.js`
2. Create the app, then **Stop** it while you upload files.

## 3. Upload and extract

1. cPanel → **File Manager** → open the application root (`~/victus-app`). If you
   parked a "coming soon" placeholder on the `app` subdomain earlier, delete it
   first.
2. Upload `victus-web-cpanel.zip` and **Extract** it there. The folder should now
   contain `app.js`, `apps/`, and `node_modules/` at the top level.
3. Delete the zip after extraction.

Do **not** run "Run NPM Install" — dependencies are already bundled.

## 4. Configure environment variables

In the Node.js app screen, add the runtime environment variables. These are read
on every request — they are **not** baked into the bundle:

| Variable                 | Value                                                              |
| ------------------------ | ------------------------------------------------------------------ |
| `AUTH_SECRET`            | a long random string (`openssl rand -base64 48`) — Auth.js signing |
| `AUTH_URL`               | `https://app.victusdata.com`                                       |
| `AUTH_TRUST_HOST`        | `true` (required behind the Passenger reverse proxy)               |
| `INTERNAL_API_BASE_URL`  | server-to-server URL of the API, e.g. `https://api.victusdata.com` |
| `INTERNAL_SERVICE_TOKEN` | **must match** the API's `INTERNAL_SERVICE_TOKEN` exactly          |

> `NEXT_PUBLIC_API_BASE_URL` is **build-time** (inlined in step 1), so it is not
> set here. `PORT` is supplied automatically by Passenger — do not set it.

> The `INTERNAL_SERVICE_TOKEN` is the shared secret the web server uses to
> authenticate itself to the API. Generate it once, set the identical value on
> both the API and here. If they differ, every server action fails with 401/403.

## 5. Start and verify

1. **Start** the application in the Node.js app screen.
2. cPanel → **Domains** → enable **Force HTTPS Redirect** for `app.victusdata.com`
   (camera access for the TOI pathway requires HTTPS).
3. Open `https://app.victusdata.com`, register/sign in, and run a Pathway A
   (triage) assessment end-to-end — a successful per-disease result confirms the
   web → API → database chain is wired correctly.

## Updating the app

Re-run step 1 (remember to set `NEXT_PUBLIC_API_BASE_URL` if the API origin
changed), stop the app, delete the old `apps/` and `node_modules/` folders,
extract the new zip, start the app. Environment variables persist across updates.

## Troubleshooting

- **503 / "Web application could not be started"** — confirm the startup file is
  `app.js`, Node is ≥ 20, and `app.js` sits directly in the application root (not
  inside a subfolder created by extraction).
- **Sign-in loops / "session expired" immediately** — `AUTH_URL` must be the
  exact public HTTPS origin and `AUTH_TRUST_HOST=true` must be set; otherwise
  Auth.js rejects the proxied host.
- **Every action fails with 401/403** — `INTERNAL_SERVICE_TOKEN` here does not
  match the API's, or `INTERNAL_API_BASE_URL` is wrong/unreachable.
- **Browser calls the wrong API origin** — `NEXT_PUBLIC_API_BASE_URL` is baked in
  at build time; rebuild the bundle with the correct value.
- **Camera won't start (TOI pathway)** — the page must be served over HTTPS;
  enable Force HTTPS Redirect.
