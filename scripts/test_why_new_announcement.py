#!/usr/bin/env python3
"""رگرسیون why/body برای انیمه تازه در برابر فصل تازه.

منتقد، بررسی شماره ۲ (۲۲ نوامبر ۲۰۲۶ — پیام‌های ۱۰ تا ۱۲، BanG Dream):
- why_new_season («قصه ادامه دارد») برای اعلامیه انیمه کاملاً تازه غلط
  است؛ فقط فصل برگشتی (فصل ۲ به بعد / دنباله) «قصه ادامه دارد».
- body_season_premiered («بخش تازه پیش‌تر پخش خود را آغاز کرده بود»)
  از کلمه «premiered» در پس‌زمینه خلاصه تغذیه می‌شد (پروژه قبلی
  Mugendai Mewtype که ۲ ژوئیه پخش شده بود)، نه از همین خبر.
اصلاح: why_new_announcement («دنیای … بزرگ‌تر می‌شود») + نگاشت مشروط
announcement + _has_premiered سخت‌گیرانه (تیتر، یا خلاصه + فصل برگشتی).

اجرا: python3 scripts/test_why_new_announcement.py (از ریشه ریپو)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from common import sha256_hex  # noqa: E402
from rewrite import (  # noqa: E402
    _eligible_bodies,
    _has_premiered,
    _is_returning_season,
    load_banks,
    rewrite_post,
)

BANKS = load_banks()
FAILURES = []


def check(name, cond, extra=""):
    print(("PASS" if cond else "FAIL"), "-", name, extra)
    if not cond:
        FAILURES.append(name)


BANGDREAM_ANN = {
    "title_en": "BanG Dream! Yume∞Mita Series Confirms New Anime in Production",
    "summary_en": "TV anime based on BanG Dream! project's Mugendai Mewtype band premiered on July 2",
    "source_name": "Anime News Network",
    "source_url": "https://animenewsnetwork.com/news/2026-11-20/bang-dream-yume-mita-series-confirms-new-anime-in-production/.244026",
    "pubDate": "2026-11-20T15:59:17+00:00",
    "category_hint": "فصل جدید",
}

FRIEREN_S2 = {
    "title_en": "Frieren: Beyond Journey's End Season 2 Announced",
    "summary_en": "The second season of Frieren: Beyond Journey's End has been announced; the first season premiered in September 2023",
    "source_name": "Anime News Network",
    "source_url": "https://animenewsnetwork.com/news/2026-11-21/frieren-second-season-announced/.244100",
    "pubDate": "2026-11-21T10:00:00+00:00",
    "category_hint": "فصل جدید",
}

TITLE_PREMIERED = {
    "title_en": "My Hero Academia: Vigilantes Anime Premiered",
    "summary_en": "The new anime premiered on April 7 with a one-hour special",
    "source_name": "Anime News Network",
    "source_url": "https://animenewsnetwork.com/news/2026-04-07/vigilantes-premiered/.244200",
    "pubDate": "2026-04-07T10:00:00+00:00",
    "category_hint": "فصل جدید",
}


def fx_of(title, summary):
    return {"title_en": title, "summary_en": summary, "event": "announcement",
            "event_fa": "انیمه تازه", "date_fa": "", "fr_fa": "اثر",
            "fr_en": "Anime", "studio_en": "", "studio_fa": "",
            "source_name": "ANN", "pubDate": "2026-11-20T15:59:17+00:00"}


# --- T1: _is_returning_season ---
for title, summary in [
    ("Frieren Season 2 Announced", ""),
    ("X Gets 2nd Season", ""),
    ("X Gets a New Season", ""),
    ("X Sequel Announced", ""),
    ("The second season of X has been announced", ""),
]:
    check(f"T1 returning: {title!r}", _is_returning_season(fx_of(title, summary)))

# --- T2: _is_returning_season منفی ---
for title, summary in [
    ("BanG Dream! Yume∞Mita Series Confirms New Anime in Production",
     "TV anime based on BanG Dream! project's Mugendai Mewtype band premiered on July 2"),
    ("X Gets New Anime Series", ""),
    ("Fall 2026 anime season preview", ""),
    ("New anime film announced", ""),
]:
    check(f"T2 brand-new: {title[:40]!r}", not _is_returning_season(fx_of(title, summary)))

# --- T3: _has_premiered ---
check("T3 BanG Dream background premiered is NOT premiered",
      not _has_premiered(fx_of(BANGDREAM_ANN["title_en"], BANGDREAM_ANN["summary_en"])))
check("T3 Frieren S2 summary premiered + returning IS premiered",
      _has_premiered(fx_of(FRIEREN_S2["title_en"], FRIEREN_S2["summary_en"])))
check("T3 title-premiered IS premiered",
      _has_premiered(fx_of(TITLE_PREMIERED["title_en"], TITLE_PREMIERED["summary_en"])))
check("T3 no premiere at all is NOT premiered",
      not _has_premiered(fx_of("X Gets New Anime Series", "A new anime was announced")))

# --- T4: بازنویسی BanG Dream — why تازه + بدون body_season_premiered ---
post = rewrite_post(BANGDREAM_ANN, seed=int(sha256_hex("https://www.animenewsnetwork.com/cms/.244026")[:8], 16))
check("T4 BanG Dream why is why_new_announcement",
      post["template_ids"]["why"] == "why_new_announcement",
      f"(got {post['template_ids']['why']})")
check("T4 BanG Dream body_season_premiered NOT selected",
      "body_season_premiered" not in post["template_ids"]["bodies"],
      f"(got {post['template_ids']['bodies']})")
check("T4 BanG Dream passes 10/10",
      len(post["gates_passed"]) == 10, f"({len(post['gates_passed'])}/10)")
check("T4 BanG Dream why says «دنیای … بزرگ‌تر می‌شود»",
      "بزرگ‌تر می‌شود" in post["caption"] and "قصه" not in post["caption"].split("چرا مهم است؟")[1])

# --- T5: بازنویسی فصل برگشتی — why_new_season حفظ می‌شود ---
post2 = rewrite_post(FRIEREN_S2, seed=int(sha256_hex("frieren-s2")[:8], 16))
check("T5 Frieren S2 why is why_new_season",
      post2["template_ids"]["why"] == "why_new_season",
      f"(got {post2['template_ids']['why']})")
check("T5 Frieren S2 body_season_premiered IS eligible",
      "body_season_premiered" in [b["id"] for b in _eligible_bodies(
          {"title_en": FRIEREN_S2["title_en"], "summary_en": FRIEREN_S2["summary_en"],
           "event": "announcement", "event_fa": "انیمه تازه", "date_fa": "",
           "fr_fa": "فریرن", "fr_en": "Frieren", "studio_en": "", "studio_fa": "",
           "source_name": "ANN", "pubDate": FRIEREN_S2["pubDate"]}, BANKS)])
check("T5 Frieren S2 passes 10/10",
      len(post2["gates_passed"]) == 10, f"({len(post2['gates_passed'])}/10)")

# --- T6: AnimeCorner BanG Dream (منبع دوم پیام ۱۱) هم why تازه می‌گیرد ---
ac = dict(BANGDREAM_ANN)
ac.update({
    "title_en": "BanG Dream! Yume∞Mita Gets New Anime Series",
    "summary_en": "The BanG Dream! franchise announced a new anime series for Yume∞Mita at a special event",
    "source_name": "Anime Corner",
    "source_url": "https://animecorner.me/bang-dream-yumemita-gets-new-anime-series",
})
post3 = rewrite_post(ac, seed=int(sha256_hex("animecorner-bangdream")[:8], 16))
check("T6 AnimeCorner BanG Dream why is why_new_announcement",
      post3["template_ids"]["why"] == "why_new_announcement",
      f"(got {post3['template_ids']['why']})")

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")
