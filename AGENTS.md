# AGENTS.md — Anime News Channel («اخبار دنیای انیمه»)

Read this file FIRST before touching anything. It is the single source of
truth for any agent working on this repo. The repo is PUBLIC: this file
contains ZERO secrets — no tokens, keys, passwords, private keys, wallet
addresses, or account IDs. Secret NAMES are fine; values are never written.

## 1. What this project is

A Persian-language Telegram news channel about the anime world,
`@animekhabarfa`, fully automated on **GitHub + Cloudflare only** — no
other service, no paid service, no AI at runtime, no server. A
Cloudflare Worker detects fresh news every 1 minute from 7 verified RSS
sources in the Worker (Fandom Post is currently uncovered — blocked with a stable HTTP 403 from both Cloudflare and GitHub runner egress IPs since 2026-11-21; it stays in `scripts/fetch.py` so each sweeper run re-tests it; see §7), triggers GitHub Actions with `repository_dispatch`, and Actions
rewrites the news in Persian (template bank, no LLM), renders a V3 cover
with Pillow (Playwright is only a documented fallback), and publishes it
to the channel with `sendPhoto`.

- Observability: the Worker's status endpoint (`GET /`) reads
  `meta:last_tick` from KV, which is written ONLY at the top of each hour,
  when fresh news arrives, or when a tick errors — never per tick (a
  per-tick write would cost 1,440 KV writes/day against the 1,000/day
  free limit). A `last_tick` up to ~1 hour old in quiet periods is
  NORMAL and does not mean the cron stopped; verify liveness with
  `wrangler tail` instead (confirmed live 2026-11-21 06:53 UTC: two
  consecutive ticks, errors=0).

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
  `workflow_dispatch`: priority score, Persian rewrite, 10 quality gates,
  Pillow cover (Playwright only as fallback), `sendPhoto`, then commit
  `state.json` + `queue.json` + `archive.jsonl` via
  `scripts/merge_state.py` (union merge + `merge -s ours`, never rebase —
  see §8, 2026-11-22 phantom posts).
- `sweeper.yml` — cron `*/15 * * * *`: publishes items the Worker or
  dispatch missed; also the keepalive. Its commit step also uses
  `scripts/merge_state.py` (same anti-race rule as publish.yml). The publish step runs
  unconditionally (the old `if: secrets...` skip-guard was REMOVED in
  commit 3082e75 on 2026-11-21 — `secrets` is not a valid context in
  `if:` and the guard silently killed every sweeper run for ~14 hours;
  both secrets are set, verified 2026-11-21, and publish.py fails loudly
  if they ever go missing, same alarm behaviour as publish.yml). An empty
  queue alone never fails `publish.py` (it returns posted=0); only
  missing secrets raise SystemExit, before the queue is even loaded.
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
  30-day `seen`; (2) story key (franchise + event type + 48h bucket),
  compared TOLERANTLY (`same_story_key` in `common.py`: bucket ±1 also
  matches, and the generic events `event`/`other` act as wildcards —
  added 2026-11-22 after one story posted 3 times; the reveal events
  `announcement`/`date`/`trailer` also match each other — added
  2026-11-22 after msgs 15/17 duplicated the same Elite season-5 story
  with three different event types; `casting` stays separate, it is
  usually a distinct news beat); layer 2 also checks
  the keys of QUEUED/HOLD items already in the queue, not only posted
  ones; (3) title similarity Jaccard/SequenceMatcher ≥ 0.85 in a 7-day
  window. At publish time, `publish_one` also runs a last-line guard
  (`_find_posted_duplicate`): if the same story was already posted, the
  item is marked POSTED and never sent. Before sending, `publish_one`
  re-reads the remote state (`sync_remote_state` in `common.py`): a run
  whose checkout is stale (another run posted in the meantime) sees the
  fresh posted records instead of re-posting. State is merged as a union,
  never rebased — `scripts/merge_state.py` owns the commit step in both
  workflows (see §8, 2026-11-22 phantom posts). First complete version
  publishes; later sources are appended (`editMessageCaption`, only if
  the first post is < 2h old and the second source is Tier 1, max 3
  sources). A materially new fact from a second source → a separate
  «🔄 به‌روزرسانی» post linking the first.
- Breaking (closed list, 5 items, `filter-v2.md` §5): immediate, 5-min
  gap, 🔴 label, exempt from the circuit breaker — but a
  sensitive breaking item STILL goes to HOLD. «Breaking» never
  overrides «sensitive». There is no night silence (user decision,
  locked 2026-11-21). More than 3 breaking items in a day is an
  audit warning, not a cap.
- 10 quality gates before publish (caption 600–850 chars, headline
  ≤ 70 chars, no placeholders, limited English, < 25% 5-gram similarity
  with the source summary, < 60% similarity with the last 30 posts,
  lead-template freshness max 3 uses in 7 days, specific «چرا مهم
  است؟», numbers/dates from the source, event-vs-source consistency,
  no doubled word in one line — gate 10, added 2026-11-22 after msg 10
  printed «انیمه تازه تازه اثر اعلام شد»).
  3 gate failures → human HOLD.
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
  Fandom Post, Siliconera, Honey's Anime, Anime Herald) — 7 polled by the
  Worker every 1–5 minutes; Fandom Post is blocked with a stable HTTP 403
  from BOTH egresses (Cloudflare AND GitHub runner IPs — directly
  observed in sweeper runs 44874121944 and 44878770507) and currently has
  NO coverage from either path. It STAYS in `scripts/fetch.py` (manager
  decision): the error is graceful, each sweeper run re-tests the feed,
  and coverage resumes automatically if the block ever lifts. Crunchyroll
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
- 2026-11-21 ~07:10 Tehran — Fandom Post REMOVED from Worker polling
  (manager decision, option B): stable HTTP 403 from Cloudflare egress
  IPs for 3.5+ hours (verified 00:11–03:35 UTC; same feed returns 200
  from other IPs). Worker now polls 7 feeds; `sources-v2.md` §6 and
  `worker/README.md` updated in the same commit. CORRECTION (same day,
  ~10:40 Tehran): the GitHub runner is ALSO blocked (403 directly
  observed in sweeper runs 44874121944 and 44878770507) — option B's
  premise ("the sweeper covers it") was wrong; Fandom Post currently has
  NO coverage from either path. Manager decision: DO NOT remove it from
  `scripts/fetch.py` — the error is graceful and each run re-tests it;
  reactivate only if another egress is found. See `sources-v2.md` §7.
- 2026-11-21 ~21:25 Tehran — FIRST REAL POST LIVE (run 44932633874,
  workflow_dispatch, head 285491a, dry OFF, max_posts 2): message_id 6,
  «Haite Kudasai, Takamine-san» (MAL), cover attached (first live
  cover-attach test PASSED). Run was CANCELLED at 18:10:24Z — only 1 post
  went out; the 2nd post (after the 15-min gap) never fired. state.json:
  posts_total 1, posted_message_ids [6].
- 2026-11-21 ~21:31 Tehran — CONTENT ERROR in post 6 (critic finding):
  the source (MAL 74961851) says the manga ENDS serialization (Feb issue
  of Gangan Joker, end of a nearly 8-year run) but the published caption
  claimed a NEW anime adaptation was announced, produced by Crunchyroll.
  Root cause: `detect_event` read the summary's background («A 12-episode
  television anime adaptation ... aired in Spring 2025. Crunchyroll...»)
  as the event («adaptation»), and `body_studio`/`why_adaptation` turned
  background entities into the news's actors. The 8 structural gates
  passed it — none checked event-vs-source consistency. FIXED the same
  night (local, for the browser commit; test `scripts/test_rewrite_msg6.py`
  ALL PASSED): new event `manga_ending` (ending keywords checked FIRST in
  `detect_event`; the summary-level «adaptation» check no longer accepts a
  bare «adaptation» — only forward-looking phrasing); `body_studio` +
  `body_manga_origin` only for new-production events; new why
  `why_manga_ending` + safe title/lead allowlist for endings; 9th gate
  `event_consistency` (ending-source + fresh-adaptation claim → FAIL, and
  vice versa); `detect_category` word-boundary fix («LIDENFILMS» no longer
  triggers «فیلم») + `manga_ending` → «مانگا و اقتباس»; `why_specific`
  now accepts `event_fa` as a marker — this also fixes the systematic
  announcement HOLDs (Oshi No Ko 85 + BanG Dream 80 were HOLDed for
  missing `why_specific` in run 44932633874; both re-test 9/9 with the
  fix). The wrong caption was corrected in place via `editMessageCaption`
  (message_id 6 kept; verified live on t.me/s). Known follow-up (not
  fixed here): the event taxonomy has no «license» event — a Yen Press
  license announcement defaults to «announcement» → «انیمه تازه».
- 2026-11-21 ~21:46 Tehran — RUN 44932633874 CANCELLED BY TIMEOUT
  (critic finding, proven by the job's own step timings): the publish job
  (`timeout-minutes: 15`) was killed at 18:10:24Z, 15m16s in — the
  «Publish queue to Telegram» step ran 14m58s and was cancelled mid-sleep
  (`publish.py` paces posts with a 15-min `time.sleep` between them, so a
  2-post run needs ~17 min). Only post 1 (message_id 6) went out; the
  `if: always()` commit step still saved state (posts_total 1, commit
  3966f4a). FIX (local, for the browser commit, same bundle as the msg-6
  rewrite fix): `timeout-minutes: 60` in BOTH `publish.yml` (15 → 60) and
  `sweeper.yml` (10 → 60 — the sweeper runs the same publish.py with the
  same gap, so its 10-min timeout had the identical defect, worse). The
  15-min gap itself is NOT shortened — it is a deliberate product rule
  (audience pacing). 60 covers up to ~4 posts with headroom.
- 2026-11-21 ~22:22 Tehran — RUN 44936475145 (publish #3) SUCCESS:
  18:36:40Z → 18:52:06Z (~15.5 min, no cancellation — the 60-min timeout
  fix works). posts_total 3, posted_message_ids [6, 7, 8]. New posts (live
  verified on t.me/s): msg 7 «The Reincarnated Elf Left on a Journey to
  Master His Magic» (AnimeTV, 65, فصل جدید, new cast + trailer) and msg 8
  «New Oishinbo TV Anime Set to Premiere on January 4, 2027» (AnimeTV, 65,
  فصل جدید). Both captions correct, no event inversion. Queue after run:
  60 QUEUED, 17 HOLD, 4 POSTED, 1 STALE (82 total). Note: queue shows 4
  POSTED but only 3 message_ids — the 4th («Shin Oishinbo» MAL) is the same
  Oishinbo story marked POSTED by cross-source dedupe (publish.py:342); no
  phantom post. Both new posts are ~45h old at publish time (backlog
  catch-up, inside the 48h freshness window).
- 2026-11-21 ~22:25 Tehran — HOLD RE-TEST BUG + LICENSE EVENT (critic
  finding, run 44936475145): Oshi No Ko 85 + BanG Dream 80 stayed HOLD
  (`gates_failed:why_specific`) even though they pass 9/9 with the fixed
  code — because `publish.py` only read QUEUED/APPROVED items and never
  re-evaluated HOLD items. FIX (local, for the browser commit; test
  `scripts/test_hold_retest.py` ALL PASSED): new `is_pending()` — HOLD
  items with `hold_reason` starting `gates_failed` are re-tested every run
  (publish_one re-runs the 9 gates; pass → posts, fail → stays HOLD);
  human HOLDs (`low-confidence`, 13 items) are NOT re-tested. CAUGHT WHILE
  TESTING: the Oshi No Ko caption that would have posted was a SECOND
  inversion — «Bungo Stray Dogs در راه است؛ انیمه تازه» + «از روی مانگایی
  ساخته می‌شود» for a Yen Press LICENSE announcement (no anime announced).
  FIX in the same bundle: new event `license` (detect_event «licens» in
  title/summary, checked before the adaptation fallthrough), event_fa
  «لایسنس تازه», category «مانگا و اقتباس», new why `why_license` +
  preferred map, neutral title/lead allowlist (same safe sets as
  manga_ending), `event_consistency` now also fails license-source +
  fresh-anime claim (and vice versa), «لایسنس» added to why_specific
  markers. New caption: «Bungo Stray Dogs خبرساز شد: لایسنس تازه» (9/9).
  The old wrong caption FAILS the new gate (proven in the test). HOLD
  items older than 72h are REJECTED by fetch.py — the 4 gates_failed HOLDs
  must post by ~Nov 23 or they are lost.
- 2026-11-21 ~00:40 Tehran — SWEEPER DEAD ALL DAY (manager sweep
  finding): every Sweeper run since 07:39 UTC failed workflow validation
  before any job started — `if: secrets.TELEGRAM_BOT_TOKEN != '' ...` is
  INVALID ("Unrecognized named-value: 'secrets'" — the `secrets` context
  cannot be used in `if:` conditions). Introduced by commit e9089f5
  ("fix: sweeper skips publish cleanly while Telegram secrets are
  unset"); runs #1–#2 (before it) ran fine, #3–#17 all failed with no
  duration, and no scheduled run was created after the last push at
  20:09 UTC. The channel's only posts that day came from manual publish
  runs (#2, #3) — the 15-min sweeper + keepalive never ran. FIX (same
  commit as this entry): both `secrets`-based `if:` conditions removed
  from sweeper.yml (the guard is obsolete — both secrets are set,
  verified 2026-11-21 — and publish.py fails loudly if they ever go
  missing, same alarm behaviour as publish.yml). Verify with a manual
  Sweeper dispatch right after this commit; the next scheduled tick then
  resumes automatically.
- 2026-11-22 ~01:28 UTC — SCHEDULER BACK + TRIPLE POST (run 44971616356,
  schedule, success, 15 min): the first scheduled sweeper run since
  06:08 UTC Nov 21 posted messages 11 + 12 — but all three (msgs 10, 11,
  12) were the SAME BanG Dream! Yume∞Mita new-anime story from ANN,
  AnimeCorner, AnimeTV. Root cause (critic finding, proven in code +
  queue records): (1) fetch layer 2 never compared against QUEUED/HOLD
  keys from earlier runs (ANN + AnimeCorner had the IDENTICAL story_key
  `bang dream|announcement|10388`); (2) the fixed 48h bucket splits a
  story at the grid boundary (AnimeTV `...|10389`, ~9h after ANN);
  (3) classify returned generic `event` for the MAL item (bare `event`
  in its summary matched before `announcement`). FIX (local, for the
  browser commit; test `scripts/test_dedupe_bangdream.py` ALL PASSED):
  `same_story_key` in `common.py` (bucket ±1 + generic-event wildcard),
  layer 2 also checks `queued_story_keys`, bare `event` removed from
  classify's patterns, publish-time guard `_find_posted_duplicate` in
  `publish_one` (marks a duplicate POSTED instead of sending it).
  TEMPLATE BUGS in the same wave: msg 10's caption had «انیمه تازه تازه
  اثر اعلام شد» (lead_11's literal «تازه» after {event_fa} «انیمه تازه»)
  and msgs 11/12 had the headline «... | انیمه تازه در» (title_04 with an
  empty {date_fa}). FIX in the same bundle: lead_11 + title_06 lose
  their literal «تازه», title_04 is excluded when there is no date, and
  a 10th gate `no_double_word` fails any caption with an adjacent
  repeated word in one line. NOTE: the double-«تازه» is in msg 10, not
  msg 11 as first reported — verified from the live t.me/s page.
  posts_total 7, posted_message_ids [6, 7, 8, 9, 10, 11, 12].
- 2026-11-22 ~10:20 UTC — PHANTOM POSTS 15 + 16 (manager sweep finding):
  two messages live on Telegram with NO repo record. Msg 15 (AnimeCorner
  Elite S5, 08:48:25Z) + msg 16 (MAL 74967203 AGAIN = same item as msg 13,
  09:03:26Z) came from sweeper run 45003688383: it waited ~11 min on the
  shared concurrency group (`anime-news-publish`, cancel-in-progress:
  false) for publish run 45003298273, then checked out its trigger-time
  SHA 6eaa4e8 (pre-26b8fd8) — stale state, no record of 13/14. Its step-7
  commit failed in 1s (exit 128, git fatal — rebase conflict vs 26b8fd8;
  the exact log line is admin-only, 403). Run 45010375302 (10:01) then
  re-posted the same AnimeCorner item as msg 17 — it could not know about
  msg 15. FIX (local, for the browser commit; test
  `scripts/test_race_phantom.py` ALL PASSED): (1) `same_story_key` reveal
  family — `announcement`/`date`/`trailer` match each other (`casting`
  stays separate); (2) `sync_remote_state` in `common.py` — fetch + merge
  the remote state before fetch and before each send; (3)
  `scripts/merge_state.py` replaces `pull --rebase` in both workflows'
  commit steps (union merge + `merge -s ours` + push retry). Re-publish
  risk now zero (scan of all 105 queue items: 0 match a posted
  story/hash). NOTE: archive.jsonl on main still has NO rows for msgs
  15/16 (lost with the sweeper's runner) — a historical record gap, not
  a re-post risk. Deletion of the duplicate msgs 15/16 is the manager's
  decision (management chat), not the team's.

## 9. Rules (hard)

- GitHub read/write split (PERMANENT, user-stated, 2026-11-21): READS
  (HEAD, files, commits, repo status, logs) ONLY via the GitHub
  connector. WRITES (push, commit, branch, anything that changes the
  repo or site) NEVER via the connector — and never by this team
  directly. All writes go via the browser, done by the manager (Muse
  in the «مدیر» chat). This team prepares the write (files + exact
  commit message) and hands it to the manager; it never uses a
  connector write tool and never sends a write approval card to the
  user.
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

## 10. Harsh critic (permanent role)

Owner order, 2026-11-21 (via the manager): this team has a permanent
harsh-critic member. Its only job is to constantly review the repo, the
detector Worker, and the channel `@animekhabarfa` against the long strict
checklist in `qa/critic-role.md` (31 items, scored 0–10 each, evidence
only — no guessing; untested = 0). It reports the scores and the specific
fixes to the manager; the team applies the fixes so the project keeps
improving and expanding, and gradually becomes independent of the
manager.

- The critic is READ-ONLY (GitHub connector reads only; never writes,
  never a write-approval card). Fixes are prepared locally and handed to
  the manager for the browser commit, per the read/write split rule (§9).
- Loop: the shared daily cron `team-critic-review-daily` (~09:27 Tehran,
  all 4 teams, report to the management chat). No separate cron for this
  team.
- First full review: 2026-11-21 ~21:34 Tehran — **173/300 (58%)**.
  Full scores in `qa/critic-role.md`. Top-5 fixes are listed there;
  review #1's code/doc fixes were prepared locally in the same change as
  this section (publish.py 48h freshness re-check, rewrite.py
  why_continuation, templates-fa.json lead_05, PLAN.md superseded banner,
  setup-qa-report.md §3 correction, README feeds line, ARCHITECTURE.md
  §5.1 Playwright/static-cover correction).
