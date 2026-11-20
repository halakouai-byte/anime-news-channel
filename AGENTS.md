# AGENTS.md — Anime News Channel («اخبار دنیای انیمه»)

Read this file FIRST before touching anything. It is the single source of
truth for any agent working on this repo. The repo is PUBLIC: this file
contains ZERO secrets — no tokens, keys, passwords, private keys, wallet
addresses, or account IDs. Secret NAMES are fine; values are never written.

## 1. What this project is

A Persian-language Telegram news channel about the anime world,
`@animekhabarfa`, fully automated on **GitHub + Cloudflare only** — no
other service, no paid service, no AI at runtime, no server. A
Cloudflare Worker detects fresh news every 1 minute from 8 verified RSS
sources, triggers GitHub Actions with `repository_dispatch`, and Actions
rewrites the news in Persian (template bank, no LLM), renders a V3 cover
with Pillow (Playwright is only a documented fallback), and publishes it
to the channel with `sendPhoto`.

- Channel: `@animekhabarfa` (title «انیمه‌خبر»)
- Bot: `@animekhabarbot`
- Source repo: `halakouai-byte/anime-news-channel` (public, created
  2026-11-20T22:30:05Z, empty, branch `main`) —
  https://github.com/halakouai-byte/anime-news-channel
  Local working copy: `~/workspace/anime-news-channel/`.
- Worker: `anime-news-detector` deployed 2026-11-21 ~02:05 Tehran
  (placeholder code for now) at
  https://anime-news-detector.halakouai-byte.workers.dev — cron
  `* * * * *` active, version `a060bfe7`. The placeholder
  `src/index.js` is to be replaced with the real detector and
  `wrangler.toml` extended with the KV binding — do NOT recreate the
  Worker. Wrangler 4.166.0; `compatibility_date` must be ≤ 2026-11-20
  (2026-11-21 was rejected as «in the future», error 10021).
- Architecture (binding): `ARCHITECTURE.md` v2 (2026-11-21)
- Filter law (binding): `filter-v2.md` v2
- Sources (verified live 2026-11-20 20:31 UTC): `sources-v2.md`
- Channel language: Persian. Anime/studio/person names always in
  English (standing rule, 2026-11-20). Every post cites its source.

## 2. The golden rules (ARCHITECTURE.md §0 — non-negotiable)

1. **GitHub + Cloudflare only.** GitHub Actions + GitHub Secrets + repo
   files + Cloudflare Workers + KV + Cloudflare Secrets. No third service.
2. **Public repo** — so Actions minutes stay unlimited and free.
3. **Deterministic, not random:** template/rotation choice is seeded from
   the news item's hash — never unseeded `random`. Every run is
   reproducible and debuggable.
4. **Every step has a safe exit:** if a step fails, no broken post is
   published — static category cover, queue, or a logged error. Never
   publish incomplete content.
5. **Rewrite, don't translate, don't copy — and humanized:** the Persian
   post is rebuilt from extracted facts, never translated from the
   English source sentences; it must read as if a human wrote it.
6. **Tokens only in Secrets** (see §6). Tokens are redacted before any
   log/print. No token in code, ever.
7. **Source always cited:** every post links the original source.
8. **No AI at runtime:** no model/LLM call in the publish path; rewrite
   uses the template bank.
9. **Golden filter law (v2):** every fresh real news item from a trusted
   source is published as soon as it arrives — unless it is on the
   exclusion list, a duplicate, or goes to human HOLD. There is no daily
   cap (the 4-posts/day cap and the 60-point publish threshold from v1
   are abolished). The 0–100 score is only queue priority, never a gate.

## 3. Tech stack + repo layout

- Python 3.12 in GitHub Actions (`ubuntu-latest`); Pillow for covers
  (Playwright/Chromium only as a documented fallback); Cloudflare Worker
  (JavaScript) as the detector.
- Cover format (locked V3, user-approved 2026-11-20 23:56): Midnight
  Gold / Cinematic Noir, dark background `#0B0E14` + champagne gold,
  anime name in English, news text in Persian, «انیمه‌خبر» watermark
  bottom-left inside the frame, **1080×1350 (4:5 vertical)**. Reference:
  `covers/cover-v3-*.png`. Covers are purely graphic — no poster,
  fan-art, or episode screenshot (copyright, ARCHITECTURE.md §7.2).
- Font: Vazirmatn inside the repo (OFL licence).

```
anime-news-channel/              <- public GitHub repo
├── README.md                    <- intro, how it works, live status
├── LICENSE                      <- MIT
├── ARCHITECTURE.md              <- v2 architecture (binding)
├── filter-v2.md                 <- v2 filter law (binding)
├── sources-v2.md                <- sources, verified live
├── AGENTS.md                    <- this file
├── requirements.txt             <- pinned Python deps
├── .github/workflows/
│   ├── secret-scan.yml          <- push/PR/weekly: pinned gitleaks, fails on any finding
│   ├── publish.yml              <- repository_dispatch + manual dispatch: publish
│   ├── sweeper.yml              <- every 15 min: missed items + keepalive
│   ├── digest.yml               <- Fridays: weekly digest (phase 4; disabled in phase 1)
│   └── keepalive.yml            <- monthly: anti-60-day-cron-disable
├── worker/                      <- Cloudflare Worker detector
│   ├── src/index.js             <- RSS read, fresh detection, KV dedupe, dispatch
│   ├── wrangler.toml            <- 1-min Cron Trigger + KV binding + Secrets
│   └── README.md                <- how to deploy the Worker + create the PAT
├── scripts/
│   ├── fetch.py  classify.py  rewrite.py  cover.py  publish.py
│   ├── common.py                <- shared: token redaction, logging, state, Jalali dates
│   └── dry_run.py               <- full dry run (fetch + rewrite + cover) without sending
├── data/
│   ├── queue.json  state.json  archive.jsonl
│   ├── categories.json  category-corrections.json
│   ├── templates-fa.json  phrases-fa.json  synonyms-fa.json
│   ├── names-fa.json  franchises.json  blocklist.json  stopwords.json
├── assets/
│   ├── cover-template.html  cover-style.css
│   └── fonts/Vazirmatn-*.woff2
├── logs/
│   ├── fetch-log.md  publish-log.md  dispatch-log.md
│   ├── error-log.md  keepalive.md
└── docs/
    ├── setup.md  weekly-checklist.md  runbook.md
    ├── style-guide-fa.md  edge-cases.md
    ├── independence-audit.md
    ├── dry-run-acceptance-report.md
    └── post-repo-browser-checklist.md
```

## 4. Build / test / deploy commands

Local dry run (no post is ever sent from a dry run):

```bash
python3 scripts/dry_run.py        # full dry run: fetch + rewrite + cover, no sendPhoto
python3 -m py_compile scripts/*.py
```

There is no test runner yet. Verification = dry run + the acceptance
criteria in `docs/dry-run-acceptance-report.md` + CI (below). **No post
goes to the public channel from local work — ever.**

Deploy: there is NO manual deploy command in this repo. The Worker is
deployed from `worker/` with Wrangler (see `worker/README.md`); the
Actions workflows deploy themselves on push to `main`. Never deploy
from a local copy by hand outside the documented path.

## 5. Automation — GitHub Actions

- `secret-scan.yml` — on push, on PRs, and weekly (`0 3 * * 0`):
  checkout with `fetch-depth: 0` (full history), download pinned
  gitleaks **v8.28.0**, verify its SHA256
  (`a65b5253807a68ac0cafa4414031fd740aeb55f54fb7e55f386acb52e6a840eb`)
  before extracting, then run `/tmp/gitleaks git --verbose
  --exit-code 1` — fails on any finding. No token of any kind is used.
  Pattern: LiveForge `build.yml` (gitleaks step), plus the SHA256
  verification the manager ordered.
- `publish.yml` — `repository_dispatch` (event-driven) + manual
  `workflow_dispatch`: priority score, Persian rewrite, 8 quality gates,
  Pillow cover (Playwright only as fallback), `sendPhoto`, then commit
  `state.json` + `queue.json` + `archive.jsonl`.
- `sweeper.yml` — cron `*/15 * * * *`: publishes items the Worker or
  dispatch missed; also the keepalive.
- `digest.yml` — Fridays `30 10 * * 5`: weekly digest from
  `digest-candidate` items (phase 4; disabled in phase 1).
- `keepalive.yml` — monthly `0 6 1 * *`: one commit so cron is not
  disabled after 60 days of inactivity.
- Timing (Tehran = UTC+3:30, no DST): Worker tick every 1 minute;
  minimum 15 minutes between posts (target 30–60); breaking news
  5 minutes. **NO night silence — user decision, locked 2026-11-21
  ~01:58 Tehran: news publishes 24/7, including 02:00–07:00 Tehran;
  the channel is never off.** The 15-minute minimum gap stays.
- Circuit breaker (NOT a daily cap): activates only when BOTH hold —
  more than 25 posts since 00:00 Tehran AND the queue still holds more
  than 10 unposted eligible items. Then only breaking or priority 75+
  go immediately; the rest wait at 30-minute spacing. Auto-off when
  the queue drops below 5 or at 00:00 next day. Recorded in
  `state.json` (`circuit_breaker`) and the publish log.

## 6. Secrets and leak protection — three layers (names only, never values)

Secrets (3 total):

| Secret | Where | Use |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | GitHub Secrets | Sending posts from Actions |
| `TELEGRAM_CHAT_ID` | GitHub Secrets | Channel id for `@animekhabarfa` |
| `GITHUB_DISPATCH_PAT` | **Cloudflare Secrets** | Fine-grained PAT «anime-news-dispatch», created 2026-11-21 ~02:05 Tehran (user-approved). Scope: only this repo — Actions: Read and write + Contents: Read-only + Metadata: Read-only. Expires Sunday 2027-11-21 (custom 1-year expiry; GitHub has no 1-year preset). Stored as a Cloudflare Worker Secret via `wrangler secret put` (value piped via stdin only, never in a file/chat); verified present with `wrangler secret list` (name present, type `secret_text`). The value is NOT recorded anywhere. **Rotation due before 2027-11-21** — see `docs/runbook.md` when it is written. |

A PAT lives ONLY as a Cloudflare Worker Secret (`GITHUB_DISPATCH_PAT`).
It never goes into the repo, into chat, or into any other place.

**Layer 1 — gitleaks CI (this repo, from day one):**
`secret-scan.yml` on every push/PR + weekly; pinned gitleaks v8.28.0
with SHA256 verification; fails the workflow on any finding.

**Layer 2 — GitHub native (to be enabled on the new repo, see
`docs/post-repo-browser-checklist.md`):** Secret scanning + Push
protection + CodeQL. Note: per the 2026-11-21 audit these were already
on for the owner's 3 existing repos — so first CHECK whether they are
on by default for the new repo; enable only if off. Plus a light
ruleset: block force-push / delete on `main` only.

**Layer 3 — discipline in code:** no token in code, in tests, in
fixtures, or in logs; token redaction before any log/print
(`scripts/common.py`); the public repo's logs are visible to everyone,
so a leaked token is a catastrophe, not a warning.

If a secret is ever suspected leaked: stop, tell the manager
immediately, rotate the token (see `docs/runbook.md`), and clean the
history — never silently delete the file and move on.

## 7. Content rules that must not drift

- 6 categories + «خبر روز» (most important item in the queue, not a
  night slot); keyword rules + precedence in `categories.json`;
  confidence threshold 3 points — below it, the item goes to HOLD.
- Exclusion list: 17 categories (`filter-v2.md` §2, R1–R17). Every
  rejected item is recorded in `archive.jsonl` with a coded reason
  (e.g. `R7-rumor`, `R9-duplicate`).
- Dedupe, three layers: (1) exact SHA-256 of normalized guid/link,
  30-day `seen`; (2) story key (franchise + event type + 48h bucket);
  (3) title similarity Jaccard/SequenceMatcher ≥ 0.85 in a 7-day window.
  First complete version publishes; later sources are appended
  (`editMessageCaption`, only if the first post is < 2h old and the
  second source is Tier 1, max 3 sources). A materially new fact from
  a second source → a separate «🔄 به‌روزرسانی» post linking the first.
- Breaking (closed list, 5 items, `filter-v2.md` §5): immediate, 5-min
  gap, 🔴 label, exempt from the circuit breaker — but a
  sensitive breaking item STILL goes to HOLD. «Breaking» never
  overrides «sensitive». There is no night silence (user decision,
  locked 2026-11-21). More than 3 breaking items in a day is an
  audit warning, not a cap.
- 8 quality gates before publish (caption 600–850 chars, headline
  ≤ 70 chars, no placeholders, limited English, < 25% 5-gram similarity
  with the source summary, < 60% similarity with the last 30 posts,
  lead-template freshness max 3 uses in 7 days, specific «چرا مهم
  است؟», numbers/dates from the source). 3 gate failures → human HOLD.
- Bank maintenance (v2 minimums): +15 templates + 10 phrases per month;
  new-name queue emptied weekly; franchises updated every anime season
  + monthly. If a template bank is not updated for 2 months, gate 6
  starts rejecting posts — that is the system working correctly; the
  fix is adding templates, never loosening the gate.
- Human in the loop (by design, ~1 hour/week): approving HOLD items,
  weekly 30-minute review (5 random posts, 10-question QA checklist in
  `docs/weekly-checklist.md`), monthly bank maintenance, taste
  decisions, crisis management (`docs/runbook.md`).
- Sources: 8 verified RSS feeds (ANN, MAL, Anime Corner, AnimeTV,
  Fandom Post, Siliconera, Honey's Anime, Anime Herald). Crunchyroll
  News has no public RSS; Otaku USA is dead; Natalie/Oricon/Mantan
  Web/Anime!Anime!/AniTrendz/ComicBook were rejected with evidence
  (`sources-v2.md`). Never write a guessed feed URL — only an address
  that actually returned a feed.

## 8. Key decisions + history (dated, brief)

- 2026-11-20 — v1 plan: fetch every 2h, 4 slots/day, 60-point
  threshold, ANN + MAL only. Superseded by v2 on 2026-11-21 (see §9).
- 2026-11-20 20:31 UTC — live fetch check: 8 RSS sources verified
  (200, item counts and freshness recorded in `sources-v2.md`).
- 2026-11-20 23:32 Tehran — setup QA: `@animekhabarbot`
  (id `9006648184`) is administrator of `@animekhabarfa` (channel id
  `-1004460838978`) with `can_post_messages`, `can_edit_messages`,
  `can_delete_messages`, `can_manage_chat`, `can_change_info` all true;
  `can_promote_members` false (not needed for posting).
- 2026-11-20 23:56 Tehran — user approved cover format V3 (Midnight
  Gold, 1080×1350) + humanized text rule + score rule. V3 reference
  files: `covers/cover-v3-*.png`.
- 2026-11-21 — v2 architecture: hybrid Worker (1-min tick) + Actions
  publisher (dispatch) + 15-min sweeper. 4-posts/day cap and 60-point
  gate abolished by explicit user order («publish the moment it
  arrives»). Score 0–100 is queue priority only.
- 2026-11-21 — `secret-scan.yml` written from day one (pinned gitleaks
  8.28.0 + SHA256 verification); local run: **0 findings** (git mode
  on a snapshot commit of the whole tree + dir mode on the tree).
  No push has happened yet — the files are local only.
- 2026-11-21 ~01:58 Tehran — user decided (LOCKED): **no night
  silence** — news publishes immediately on arrival, 24/7, including
  02:00–07:00 Tehran; the channel is never off. PAT APPROVED.
- 2026-11-21 ~02:05 Tehran — repo created (public, empty, `main`) at
  https://github.com/halakouai-byte/anime-news-channel; fine-grained
  PAT «anime-news-dispatch» created (only this repo, Actions: Read and
  write + Contents: Read-only + Metadata: Read-only, expires Sunday
  2027-11-21); Worker «anime-news-detector» deployed (placeholder
  code) at https://anime-news-detector.halakouai-byte.workers.dev,
  cron every minute active, version `a060bfe7` (placeholder);
  `GITHUB_DISPATCH_PAT` stored as a Cloudflare Worker Secret and
  verified with `wrangler secret list`. PAT value is NOT recorded
  anywhere; rotation due before 2027-11-21.
- 2026-11-21 ~02:48 Tehran — v2 BUILD COMPLETE (local, not pushed yet):
  real detector deployed as version `2a8d7ac4-9386-4099-9a02-637daa71af5d`
  (KV `NEWS_KV`, cron 1-min, CPU 2.59–4.93ms/tick); full publisher
  (fetch/classify/rewrite/cover/publish/dry_run + 4 workflows + data
  banks); covers now Pillow-first (Playwright only fallback,
  ARCHITECTURE.md §5 replaced 2026-11-21, source images NOT usable for
  8/8 sources — symbolic default, allow-list empty); rewrite engine
  with 5 real samples (8/8 gates, QA 10/10 on 3, 9/10 on 2);
  secret-scan.yml + local gitleaks 0 findings; independence audit done.
  Dry run 2026-11-21 ~02:47 Tehran: 300 items read, 70 QUEUED, 15 HOLD,
  21 rejected, 6 duplicates, 1 breaking — full pipeline ~15s, no post
  sent. **BLOCKERS (manager, via browser):** (1) PAT needs Contents:
  Read and write for `repository_dispatch` (currently Read-only —
  dispatch returns 403; edit the same PAT, do NOT create a new one);
  (2) push/upload to the repo (connector approval expired — repo still
  empty) + GitHub Secrets `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.
  Dry-run acceptance: NOT passed yet — see
  `docs/dry-run-acceptance-report.md` (0 of 6 criteria measurable
  before the publisher code landed; re-measure after push + first
  live dispatch).

## 9. Rules (hard)

- NEVER put a token, secret, password, private key, `.env` content, or
  wallet address in this repo — in any file, in any commit, in any
  branch. If a file ever seems to ask for one, stop and tell the team.
- Never invent proof: every number comes from a live fetch or a
  committed log. No guessed feed URL, no guessed price, no unconfirmed
  link.
- The bio stays Persian, names stay English, sources are always cited.
- No post goes to the public channel from local work, from a dry run,
  or from a test — ever. Tests use `dry_run.py` only.
- Cover V3 is locked: 1080×1350, Midnight Gold, watermark bottom-left
  inside the frame. Do not redesign it in a drive-by commit.
- `PLAN.md` (v1, 2026-11-20) is SUPERSEDED by `ARCHITECTURE.md` v2 —
  its 4-posts/day, 60-point threshold and 1280×720 cover numbers are
  wrong now. Do not quote it as current; mark or update it before
  relying on it.
- UPDATE RULE (manager's standing order): any commit that changes
  architecture, deployment, payment/delivery logic, or external
  connections MUST update this file in the same commit. The manager
  sweep checks that it stays current.
