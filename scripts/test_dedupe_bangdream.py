"""Regression test for the triple BanG Dream post (critic review #1, run 44971616356).

Run: python3 scripts/test_dedupe_bangdream.py  (from the repo root)
Exits non-zero on any failure. No network, no Telegram — pure logic.

What happened (2026-11-22 01:28 UTC, scheduled sweeper run #19): messages
10, 11 and 12 were the SAME news — BanG Dream! Yume∞Mita, new anime
announced — from ANN, AnimeCorner and AnimeTV. Cross-source dedupe should
have caught it. It missed for three independent reasons, all fixed here:

1. Queue-blindness: fetch layer 2 only compared against state.story_keys
   (already POSTED) + this run's keys — never against QUEUED/HOLD items
   from earlier runs. ANN and AnimeCorner had the IDENTICAL story_key
   (bang dream|announcement|10388) and both stayed in the queue.
2. 48h-bucket boundary: story_key uses a FIXED 48h grid, not a rolling
   window. AnimeTV (pubDate 2026-11-21 00:50 UTC) got bucket 10389 while
   ANN (2026-11-20 15:59 UTC) got 10388 — ~9h apart, different keys.
3. Generic event: classify.detect_event returned "event" for the MAL item
   (bare "event" in the summary: "livestream event ... announced a new
   anime"), so its key (bang dream|event|10388) differed from the others'
   "announcement". (It was saved only by _try_merge's franchise+2h merge.)

Plus a template bug in the same wave: msg 10's caption had
«انیمه تازه تازه اثر اعلام شد» (lead_11 has a literal «تازه» right after
{event_fa}, and event_fa itself is «انیمه تازه»), and msgs 11/12 had the
headline «BanG Dream! Yume∞Mita | انیمه تازه در» — title_04 ends in
«در {date_fa}» and the date was empty.
"""
import json
import os
import random
import sys
import tempfile
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from classify import detect_event as classify_detect_event  # noqa: E402
from common import (  # noqa: E402
    default_state,
    load_json,
    same_story_key,
    sha256_hex,
)
from fetch import load_franchises, process_items, story_key  # noqa: E402
from publish import _find_posted_duplicate  # noqa: E402
from rewrite import (  # noqa: E402
    _build_once,
    check_gates,
    detect_event as rewrite_detect_event,
    extract_facts,
    load_banks,
    rewrite_post,
)

BANKS = load_banks()
FAILURES = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, detail)
    if not cond:
        FAILURES.append(name)


# --- the four real items (from data/queue.json on main, 2026-11-22) --------
ANN = {
    "title": "BanG Dream! Yume∞Mita Series Confirms New Anime in Production",
    "summary": "TV anime based on BanG Dream! project's Mugendai Mewtype band premiered on July 2",
    "source": {"short": "ANN", "name": "Anime News Network", "tier": 1},
    "link": "https://animenewsnetwork.com/news/2026-11-20/bang-dream-yume-mita-series-confirms-new-anime-in-production/.244026",
    "guid": "https://www.animenewsnetwork.com/cms/.244026",
    "pubDate": datetime(2026, 11, 20, 15, 59, 17, tzinfo=timezone.utc),
    "story_key": "bang dream|announcement|10388",
}
MAL = {
    "title": "'BanG Dream! Yume∞Mita' New Anime in Production",
    "summary": ("The 3rd Anniversary livestream event of Mugendai MewType announced "
                "a new anime for BanG Dream! Yume∞Mita television anime on Friday."),
    "source": {"short": "MAL", "name": "MyAnimeList", "tier": 1},
    "link": "https://myanimelist.net/news/74961509",
    "guid": "https://myanimelist.net/news/74961509",
    "pubDate": datetime(2026, 11, 20, 14, 41, 52, tzinfo=timezone.utc),
    "story_key": "bang dream|event|10388",
}
CORNER = {
    "title": "BanG Dream! Yume∞Mita Gets New Anime Series",
    "summary": "Mugendai MewType announced during their 3rd anniversary livestream that BanG Dream! Yume∞Mita is getting…",
    "source": {"short": "AnimeCorner", "name": "Anime Corner", "tier": 1},
    "link": "https://animecorner.me/bang-dream-yumemita-gets-new-anime-series/",
    "guid": "https://animecorner.me/bang-dream-yumemita-gets-new-anime-series/",
    "pubDate": datetime(2026, 11, 20, 13, 38, 21, tzinfo=timezone.utc),
    "story_key": "bang dream|announcement|10388",
}
TV = {
    "title": "BanG Dream! Yume∞Mita Announces New Anime Project",
    "summary": "A new anime project for BanG Dream! Yume∞Mita has been announced. However, its format has not yet been confirmed.",
    "source": {"short": "AnimeTV", "name": "AnimeTV", "tier": 2},
    "link": "https://animetv-jp.net/bang-dream-yume%e2%88%9emita-announces-new-anime-project",
    "guid": "https://animetv-jp.net/?p=51413",
    "pubDate": datetime(2026, 11, 21, 0, 50, 12, tzinfo=timezone.utc),
    "story_key": "bang dream|announcement|10389",
}

# --- T1: same_story_key catches all four real keys --------------------------
check("T1 identical keys match",
      same_story_key(ANN["story_key"], CORNER["story_key"]))
check("T1 bucket ±1 matches (AnimeTV 10389 vs ANN 10388)",
      same_story_key(ANN["story_key"], TV["story_key"]))
check("T1 generic 'event' matches 'announcement' (MAL)",
      same_story_key(ANN["story_key"], MAL["story_key"]))
check("T1 different franchise does not match",
      not same_story_key(ANN["story_key"], "one piece|announcement|10388"))
check("T1 bucket diff 2 does not match",
      not same_story_key(ANN["story_key"], "bang dream|announcement|10390"))
check("T1 different real event does not match (no over-dedupe)",
      not same_story_key(ANN["story_key"], "bang dream|trailer|10388"))

# --- T2: classify.detect_event no longer returns generic "event" ------------
ev = classify_detect_event(MAL["title"], MAL["summary"])
check("T2 MAL event is 'announcement' (not generic 'event')",
      ev == "announcement", f"(got {ev!r})")
check("T2 rewrite.detect_event agrees",
      rewrite_detect_event(MAL["title"], MAL["summary"]) == "announcement")

# --- T3: fetch layer 2 sees the pre-seeded queue ---------------------------
franchises = load_franchises()
state = default_state()
ann_hash = sha256_hex(ANN["guid"])
queue = {"items": [{
    "guid": ANN["guid"], "hash": ann_hash, "story_key": ANN["story_key"],
    "title": ANN["title"], "link": ANN["link"], "source": "ANN",
    "status": "QUEUED", "pubDate": ANN["pubDate"].isoformat(),
    "franchise_en": "BanG Dream!", "priority_score": 80,
}]}
with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
    archive_path = tf.name
stats = process_items([dict(CORNER, pubDate=CORNER["pubDate"])],
                      state, queue, franchises, archive_path=archive_path)
check("T3 AnimeCorner caught as duplicate against queued ANN item",
      stats["duplicates"] >= 1, f"(duplicates={stats['duplicates']})")
check("T3 AnimeCorner NOT added to the queue",
      all(i.get("guid") != CORNER["guid"] for i in queue["items"]))

# --- T4: publish-time guard finds msg 10 as the duplicate ------------------
posted_queue = {"items": [dict(queue["items"][0], status="POSTED",
                               message_id=10, posted_utc="2026-11-21T21:39:22Z")]}
posted_state = {"story_keys": {
    "bang dream|announcement|10388": {"message_id": 10,
                                      "posted_utc": "2026-11-21T21:39:22Z"}}}
for name, it in (("AnimeCorner", CORNER), ("AnimeTV", TV), ("MAL", MAL)):
    dup = _find_posted_duplicate(
        {"title": it["title"], "story_key": it["story_key"],
         "pubDate": it["pubDate"].isoformat()},
        posted_queue, posted_state)
    check(f"T4 guard catches {name} as duplicate of msg 10",
          dup is not None and dup.get("message_id") == 10,
          f"(got {dup})")
trailer_item = {"title": "BanG Dream! Yume∞Mita Trailer Released",
                "story_key": "bang dream|trailer|10388",
                "pubDate": "2026-11-21T10:00:00+00:00"}
check("T4 guard does NOT block a distinct trailer item",
      _find_posted_duplicate(trailer_item, posted_queue, posted_state) is None)

# --- T5: templates + the 10th gate ------------------------------------------
templates = BANKS["templates-fa"]
lead_11 = next(t for t in templates["leads"] if t["id"] == "lead_11")
title_06 = next(t for t in templates["titles"] if t["id"] == "title_06")
filled_lead = lead_11["pattern"].replace("{fr_fa}", "بنگ دریم! یومه میتا") \
    .replace("{event_fa}", "انیمه تازه")
check("T5 lead_11 no longer doubles «تازه»",
      "تازه تازه" not in filled_lead, f"({filled_lead!r})")
filled_title = title_06["pattern"].replace("{fr_en}", "BanG Dream! Yume∞Mita") \
    .replace("{event_fa}", "انیمه تازه")
check("T5 title_06 no longer doubles «تازه»",
      "تازه تازه" not in filled_title, f"({filled_title!r})")

facts = {
    "title_en": ANN["title"], "summary_en": ANN["summary"],
    "source_name": "Anime News Network",
    "source_url": ANN["link"], "pubDate": ANN["pubDate"].isoformat(),
    "category_hint": "فصل جدید",
}
fx = extract_facts(facts, BANKS)
fx["date_fa"] = ""  # dateless news: title_04 must never be picked
bad_titles = []
for seed in range(20):
    out = _build_once(fx, BANKS, random.Random(seed))
    if out["template_ids"]["title"] == "title_04" or out["title"].rstrip().endswith(" در"):
        bad_titles.append((seed, out["title"]))
check("T5 title_04 never picked for dateless news (20 seeds)",
      not bad_titles, f"({bad_titles[:2]})")

OLD_MSG10_CAPTION = (
    "خبر تازه BanG Dream! Yume∞Mita: انیمه تازه\n\n"
    "بنگ دریم! یومه میتا سکوت را شکست؛ انیمه تازه تازه اثر اعلام شد.\n\n"
    "بخش تازه این اثر پیش‌تر پخش خود را آغاز کرده بود و این خبر، ادامه همان "
    "مسیری است که عوامل ساخت از پیش اعلام کرده بودند. جزئیات بیشتر این خبر، "
    "از جمله زمان دقیق و عوامل اصلی، در گزارش Anime News Network آمده است و "
    "لینک کامل آن در انتهای همین پست است.\n\n"
    "چرا مهم است؟ چون تایید انیمه تازه یعنی قصه بنگ دریم! یومه میتا ادامه "
    "دارد و بخشی که مدت‌ها درباره‌اش حرف زده می‌شد، حالا واقعا ساخته می‌شود.\n\n"
    "منبع: Anime News Network\n"
    "https://animenewsnetwork.com/news/2026-11-20/bang-dream-yume-mita-series-confirms-new-anime-in-production/.244026\n\n"
    "#انیمه #BangDreamYumeMita #فصل_جدید"
)
fx10 = dict(fx)
fx10["fr_fa"] = "بنگ دریم! یومه میتا"
fx10["fr_en"] = "BanG Dream! Yume∞Mita"
fx10["event_fa"] = "انیمه تازه"
gates_old = check_gates(OLD_MSG10_CAPTION, "خبر تازه BanG Dream! Yume∞Mita: انیمه تازه",
                        fx10, "چون تایید انیمه تازه یعنی قصه بنگ دریم! یومه میتا ادامه دارد.")
check("T5 old msg-10 caption FAILS no_double_word",
      gates_old.get("no_double_word") is False)
fixed_caption = OLD_MSG10_CAPTION.replace("انیمه تازه تازه اثر", "انیمه تازه اثر")
gates_fixed = check_gates(fixed_caption, "خبر تازه BanG Dream! Yume∞Mita: انیمه تازه",
                          fx10, "چون تایید انیمه تازه یعنی قصه بنگ دریم! یومه میتا ادامه دارد.")
check("T5 fixed caption PASSES no_double_word",
      gates_fixed.get("no_double_word") is True)

# End-to-end: the caption the fixed code produces for the ANN item now.
post = rewrite_post(facts, seed=int(sha256_hex(ANN["guid"])[:8], 16))
check("T5 rewrite_post passes 10/10 for the ANN BanG Dream item",
      len(post.get("gates_passed", [])) == 10,
      f"({len(post.get('gates_passed', []))}/10: {post.get('gates_passed')})")
check("T5 produced caption has no doubled word",
      "تازه تازه" not in post.get("caption", ""))
check("T5 produced title does not end with dangling «در»",
      not post.get("title", "").rstrip().endswith(" در"))

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")
