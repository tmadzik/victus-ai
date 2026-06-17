# Deploying the marketing site to cPanel

The marketing site ships as a **self-contained Node.js bundle** (Next.js
standalone output, production `node_modules` included). The cPanel host never
runs `npm install` — you build locally, upload one archive, and point Passenger at
it.

> **Host requirements:** cPanel with **"Setup Node.js App"** (CloudLinux
> Node.js Selector / Passenger) and **Node.js 20 or newer**. The pilot-request
> form is a server action, so a plain static-file docroot is **not** enough —
> the Node.js application feature is required.

## Domain topology (one-time)

Two hostnames, two independent deployments:

| Hostname                | Serves                     | Lives where                                               |
| ----------------------- | -------------------------- | --------------------------------------------------------- |
| `www.victusdata.com`    | This marketing site        | cPanel Node.js app (this guide)                           |
| `victusdata.com` (apex) | 301 redirect → `www`       | cPanel redirect (SEO — the site's canonical URL is `www`) |
| `app.victusdata.com`    | The Victus AI clinical app | Separate deployment from the app repo — **reserve only**  |

The marketing site's canonical origin is `https://www.victusdata.com` (set in
`src/lib/site.ts`), so apex traffic must funnel to `www` to avoid duplicate-URL
SEO penalties.

**Set this up before deploying:**

1. **`www` for the marketing app** — handled in step 2 below (the Node.js app's
   _Application URL_ is `www.victusdata.com`). If `www` isn't already a
   subdomain, create it under cPanel → **Domains** first.
2. **Apex → www redirect** — cPanel → **Domains** → **Redirects**: permanent
   (301) redirect from `victusdata.com` to `https://www.victusdata.com`.
3. **`app` subdomain** — cPanel → **Domains** → **Create A New Domain** →
   `app.victusdata.com`. The clinical app is deployed from its own repository,
   so for now park the subdomain with the bundled placeholder: upload
   `apps/marketing/parking/index.html` to the subdomain's document root (it's a
   single self-contained "coming soon" file — no build step, no dependencies).
   The marketing **Sign In** button already links to
   `https://app.victusdata.com/login` via the build-time `NEXT_PUBLIC_APP_URL`;
   it will start working once the real app is deployed over the placeholder.

> Auth cookies are scoped strictly to `app.victusdata.com` — never set a
> cookie on the parent `.victusdata.com` domain, or the marketing site would
> start carrying session state it must not have.

## 1. Build the bundle (local machine)

Build on **Node 20** so the bundle matches the cPanel runtime. The repo pins it
via `.nvmrc`:

```bash
nvm use            # selects Node 20 (per .nvmrc) — or `nvm install 20` first
corepack enable    # once per machine, activates the pinned pnpm

# From the repo root. NEXT_PUBLIC_APP_URL is inlined at build time —
# set it to the real app subdomain before building.
NEXT_PUBLIC_APP_URL=https://app.victusdata.com \
  pnpm --filter @victus/marketing build:cpanel
```

Output: `apps/marketing/dist-cpanel/victus-marketing-cpanel.tar.gz`

> Shipped as `.tar.gz`, not `.zip`: cPanel's malware scanner (ClamAV +
> Sanesecurity "Foxhole") false-positives on any zip containing JavaScript
> (`Foxhole.JS_Zip_*`), which a Node bundle always trips. A tarball avoids it
> and cPanel extracts it identically.

The same bundle also runs locally for a final smoke test:

```bash
PORT=3001 node apps/marketing/.next/standalone/app.js
# → http://localhost:3001
```

> This site uses no `next/image` runtime optimisation and generates its OG
> image at build time, so the bundle carries no platform-specific native code
> that runs on the server — a macOS-built bundle runs correctly on Linux
> cPanel. Building on Node 20 keeps the build major aligned with the host.

> **Optional CI fallback.** A dormant `.github/workflows/release-marketing.yml`
> can build the same tarball on Linux (on a published Release, or via
> **Actions → Run workflow**) if you ever want to build off-machine. It is not
> required for this deploy flow.

## 2. Create the Node.js app in cPanel

1. cPanel → **Setup Node.js App** → **Create Application**
   - **Node.js version:** 20.x (or newer)
   - **Application mode:** Production
   - **Application root:** e.g. `victus-marketing` (a folder in your home
     directory — _not_ inside `public_html`)
   - **Application URL:** the domain/subdomain for the site
     (`www.victusdata.com`)
   - **Application startup file:** `app.js`
2. Create the app, then **Stop** it while you upload files.

## 3. Upload and extract

1. cPanel → **File Manager** → navigate to the application root
   (`~/victus-marketing`).
2. Upload `victus-marketing-cpanel.tar.gz` and **Extract** it there (cPanel
   File Manager extracts `.tar.gz` natively; or over SSH:
   `tar -xzf victus-marketing-cpanel.tar.gz`). The folder should now contain
   `app.js`, `apps/`, and `node_modules/` at the top level.
3. Delete the archive after extraction.

Do **not** run "Run NPM Install" in the Node.js app screen — dependencies are
already bundled.

## 4. Configure environment variables

In the Node.js app screen, add the runtime environment variables:

| Variable            | Value                                                   |
| ------------------- | ------------------------------------------------------- |
| `SMTP_HOST`         | `mail.victusdata.com` (your cPanel mail server)         |
| `SMTP_PORT`         | `465` (SSL) — or `587` with `SMTP_SECURE=false`         |
| `SMTP_SECURE`       | `true` for 465, `false` for 587                         |
| `SMTP_USER`         | a cPanel mailbox, e.g. `noreply@victusdata.com`         |
| `SMTP_PASS`         | that mailbox's password                                 |
| `LEAD_NOTIFY_TO`    | where pilot requests land, e.g. `pilots@victusdata.com` |
| `LEAD_NOTIFY_FROM`  | sender identity, e.g. `noreply@victusdata.com`          |
| `CRM_WEBHOOK_URL`   | _(optional)_ CRM/Zapier/Make inbound webhook URL        |
| `CRM_WEBHOOK_TOKEN` | _(optional)_ bearer token sent with the webhook         |

Create the two mailboxes first under cPanel → **Email Accounts** if they don't
exist. At least one channel (SMTP or webhook) **must** be configured —
otherwise leads are only written to the application log (`stderr`, visible in
the Node.js app screen / Passenger log).

`PORT` is supplied automatically by Passenger — do not set it.

## 5. Start and verify

1. **Start** the application in the Node.js app screen.
2. Open the site — check the homepage, `/privacy`, `/sitemap.xml`.
3. Submit a test pilot request with a real email; confirm the notification
   arrives at `LEAD_NOTIFY_TO` (and in the CRM if the webhook is set).
4. Force HTTPS: cPanel → **Domains** → enable _Force HTTPS Redirect_ (the app
   already sends HSTS headers).

## Updating the site

Re-run step 1, stop the app, delete the old `apps/` and `node_modules/`
folders, extract the new archive, start the app. Environment variables persist
across updates.

## Troubleshooting

- **503 / "Web application could not be started"** — check the startup file is
  `app.js` and Node is ≥ 20 (`node -v` shown in the app screen).
- **Form succeeds but no email arrives** — check the Passenger log for
  `[pilot-request] channel failure(s)`. Usual causes: wrong mailbox password,
  or the host requires port 587 with `SMTP_SECURE=false`.
- **Styles load but images 404** — the archive was extracted into a subfolder;
  `app.js` must sit directly in the application root.
- **"Sign In" points to the wrong place** — `NEXT_PUBLIC_APP_URL` is baked in
  at build time; rebuild the bundle with the correct value.
- **Upload blocked: `Sanesecurity.Foxhole.JS_Zip_*` "virus"** — a false
  positive from cPanel's scanner on zips containing JavaScript. Use the
  `.tar.gz` artifact (the default) instead of a `.zip`; if you still have a
  zip, re-run `pnpm build:cpanel` to produce the tarball, or upload over SSH.
