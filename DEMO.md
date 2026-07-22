# Victus — internal review & investor demo (localhost)

A complete, self-contained run of the platform on your own machine, pre-loaded
with a synthetic cohort so every feature has something real to show.

```bash
./infra/demo-up.sh     # start (builds first time, then seeds)
./infra/demo-down.sh   # stop  (--wipe to also delete the demo database)
```

| | |
| --- | --- |
| Marketing site | http://localhost:3001 |
| Clinical app | http://localhost:3000 |
| **Kiosk terminal** | http://localhost:3000/kiosk |
| API docs (Swagger) | http://localhost:8000/docs |

**Two extra demo affordances are switched on locally** (never in production):

- **TOI demo capture** — the rPPG wizard can submit a *synthetic* capture instead
  of driving the webcam. Meeting-room lighting and a missed face-lock are the
  fastest way to sink a live demo; this removes that risk. The real camera path
  still works if you want it (`localhost` is a secure context, so the browser
  grants camera access).
- **Gateway without Meta** — the API skips webhook signature checks when no app
  secret is set, and the worker prints outbound WhatsApp messages to its log
  instead of sending them. So the whole walk-up journey runs with no Meta
  account. See the Gateway section below.

**Sign in** — password for every demo account is `VictusDemo!2026`

| Role | Email |
| --- | --- |
| Clinician *(start here)* | `clinician@demo.victusdata.com` |
| Admin | `admin@demo.victusdata.com` |
| Participant | `tendai@demo.victusdata.com` |

> **All data is synthetic.** No real people, no real measurements. The platform
> runs as a **research demonstrator** — every result carries "not a medical
> device". Say this out loud early; it builds credibility rather than costing it.

> **Isolated.** Its own Docker volumes and database. It does not touch
> `~/.victus-local` or anything else on your machine.

---

## ⚠️ Read before you demo: the hypertension head is miscalibrated

The demo runs the **trained** DANN-EDL checkpoint so the trajectory and
rising-risk features work. That checkpoint has a **known defect**: the
*hypertension* head returns HIGH_RISK for a clearly normotensive person.

Verified: a healthy 25-year-old (BMI 21.2, **BP 112/70**) scores
`Obesity GREEN` and `Diabetes GREEN` — both correct and confident — but
`Hypertension RED`. Because the overall state takes the worst of the three,
**every participant shows RED overall.**

A clinically literate founder or investor will spot this immediately. Options:

- **Own it.** "The obesity and diabetes heads are well-calibrated; the
  hypertension head is over-predicting and is on the fix list before validation."
  Honest, and it demonstrates you monitor your own model quality.
- **Avoid the discrete labels** and demo the *trajectories* instead — the trends
  and the uncertainty gating behave correctly.
- **Switch to the rule-based backend** — clinically sensible GREEN/YELLOW states,
  but its uncertainty is so wide that no trend is ever called significant, so the
  trajectory and nudge features go quiet. To switch, comment out the
  `VICTUS_TRIAGE_MODEL_PATH` line in `infra/docker-compose.local.yml`, then
  `./infra/demo-up.sh`.

Fixing the hypertension head is a training task, not a platform task.

---

## The 12-minute walkthrough

### 1. The pitch surface (1 min) — http://localhost:3001
Open the marketing site. *"Predict NCD risk, prevent avoidable claims — AI
scoring plus a wellness network we own."* Then click into the app.

### 2. The clinician's morning (3 min) — sign in as **clinician**
- The **notification bell shows 3 unread**. These weren't clicked into
  existence — the platform generated them when risk started moving.
- Open them: two **risk-trend** nudges and one **contactless vital-sign** nudge.
  *"Nobody had to go looking. The system noticed the trend and came to us."*
- Click a nudge → it deep-links straight to that participant's record.

### 3. The hero story — **Tendai Moyo** (3 min)
Three check-ups over ~3 months.
- **Risk trajectory** panel: Obesity, Hypertension and Diabetes all **RISING**,
  each marked *significant*.
- The point to make: *"A change is only called real when it exceeds the model's
  own uncertainty. This one did — that's why a clinician was paged."*

### 4. The counter-example — **Farai Kanengoni** (1 min)
Two check-ups, small wobble. Trajectory reads **"Within measurement noise."**
*"Same machinery, and it deliberately says nothing. A screening tool that cries
wolf is worse than none."* This is the slide that separates you from a dashboard.

### 5. The loop closing — **Chipo Nyathi** (1 min)
Obesity trajectory **FALLING**, significant. *"She went into a programme at a
facility we own, and the curve bent. That's the outcome we get paid for."*

### 6. Contactless capture — **Kudzai Tafara** (2 min)
- **Vital-sign trajectory**: resting heart rate 60 → 97 bpm, **RISING**.
- *"No cuff, no strip, no phlebotomist — a camera. That's what makes screening a
  whole member base affordable."*
- **Live demo (optional, strong):** as the *participant*, run a real rPPG capture
  in the browser. Camera works because `localhost` counts as a secure context.

### 6b. The Mobile Clinic Gateway — the walk-up rail (4 min) ⭐

This is the strongest sequence in the demo: a stranger with no account, no app
and no appointment gets a screened, encrypted result on their own phone.

Open the terminal screen on a second tab — **http://localhost:3000/kiosk** —
then in a terminal window run:

```bash
python3 infra/demo-gateway.py
```

It walks the real journey and narrates each step:

1. **Terminal opens a session** → a QR code carrying a single-use code.
2. **They scan it** → WhatsApp opens pre-filled; sending it binds their phone to
   that terminal. *"No app install. No account. Their existing WhatsApp."*
3. **Consent is taken in the chat**, not on the kiosk — so the record of consent
   lives with the participant, in their language.
4. **Capture** → *"Only derived signals leave the terminal. No frames are ever
   stored."*
5. **The worker** runs the rPPG pipeline, seals the result (AES-256-GCM) and
   mints a **one-time 4-digit code**.
6. It prints **the two WhatsApp messages** the participant would receive: a
   secure portal link and the code.

**Open the printed link, enter the code.** They see their vitals. Then make the
security point: the link is **single-use** (reload it — "already viewed"),
expires in 24h, and locks out after 5 wrong codes.

Finally: sign in as the **clinician** and search the participant — the clinical
record arrived independently of the participant's copy.

> Everything above is the production code path. The only stand-in is Meta: the
> API skips webhook signature checks when no app secret is configured, and the
> worker prints the messages rather than sending them. Say that out loud — it's
> a stronger position than pretending.

### 7. Urgent referral — **Adaeze Okonkwo** (30 s)
RED with a **safety override**. *"A red-flag symptom bypasses the model
completely and escalates. The AI is never the last line of defence."*

### 8. Governance (2 min) — sign in as **admin**
Consent records, data-subject access & erasure, the audit trail, and two-person
approval on sensitive actions. *"This is what a payer's compliance team asks
about on day one — and it's built in, not a roadmap item."*

---

## The cohort at a glance

| Participant | What it demonstrates |
| --- | --- |
| **Tendai Moyo** | Risk rising → fires the clinician nudge + upward trajectory |
| **Chipo Nyathi** | Risk falling → the intervention bent the curve |
| **Farai Kanengoni** | Stable → change stays inside noise, nothing flagged |
| **Blessing Sibanda** | Borderline → the uncertain case worth confirming |
| **Kudzai Tafara** | Contactless rPPG capture → rising vital-sign trend |
| **Adaeze Okonkwo** | Red-flag symptom → deterministic urgent referral |

Re-seed at any time: `API_URL=http://localhost:8000 python3 infra/seed-demo-data.py`
(idempotent — it skips accounts and histories that already exist).

---

## If something goes wrong

| Symptom | Fix |
| --- | --- |
| `docker: not running` | Start OrbStack / Docker Desktop, then `./infra/demo-up.sh` |
| A page won't load | `docker compose -f infra/docker-compose.prod.yml -f infra/docker-compose.local.yml --env-file infra/.env.local ps` |
| Want a clean slate | `./infra/demo-down.sh --wipe` then `./infra/demo-up.sh` |
| Camera blocked | Use `http://localhost:3000` exactly — not `127.0.0.1`, not your LAN IP |
| Port already in use | Stop the other service, or edit the ports in `infra/docker-compose.local.yml` |

**Before the call:** run `./infra/demo-up.sh` ~10 minutes early, sign in as the
clinician once to warm the pages, and have this file open on a second screen.
