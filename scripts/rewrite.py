#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rewrite.py — موتور بازنویسی فارسی قالبی (template-based) کانال «اخبار دنیای انیمه».

بدون AI در runtime، بدون API خارجی، بدون توکن.
فقط قالب + بانک عبارت + جمله‌سازی قانون‌محور، قطعی و قابل تکرار:
انتخاب قالب با seed از هش خبر انجام می‌شود، نه random بدون بذر.

واسط:
    rewrite_post(facts: dict, seed: int) -> dict
    facts: title_en, summary_en, source_name, source_url, pubDate, category_hint
    خروجی: {"title", "caption", "category", "hashtags", "gates_passed",
             "template_ids", "is_breaking", "franchise_en", "new_name"}

ساختار پست (ARCHITECTURE.md §4.2): تیتر اختصاصی (≤۷۰ کاراکتر، نام انگلیسی
اثر) + لید یک‌جمله‌ای + بدنه ۲ تا ۳ جمله با حقایق + «چرا مهم است؟» دقیقاً
یک جمله خاصِ همین خبر + منبع + لینک + ۲ تا ۳ هشتگ. طول کپشن ۶۰۰–۸۵۰ کاراکتر.

۱۰ دروازه کیفی (ARCHITECTURE.md §4.3 / filter-v2.md §7.1) در check_gates
پیاده شده است؛ ۳ بار رد شدن → HOLD انسانی (تصمیم انتشار با لایه بالاتر است).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"

FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
EN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

MONTHS_FA = {
    "January": "ژانویه", "February": "فوریه", "March": "مارس",
    "April": "آوریل", "May": "مه", "June": "ژوئن", "July": "ژوئیه",
    "August": "اوت", "September": "سپتامبر", "October": "اکتبر",
    "November": "نوامبر", "December": "دسامبر",
}
MONTHS_EN = {v: k for k, v in MONTHS_FA.items()}

GENERIC_WHY = (
    "طرفداران منتظر بودند", "برای طرفداران مهم است", "خبر مهمی است",
    "همه منتظرش بودند", "این خبر برای طرفداران مهم است",
)

CATEGORIES_FA = (
    "فصل جدید", "فیلم", "تریلر", "استودیو", "مانگا و اقتباس", "رویداد", "خبر روز",
)

# ---------------------------------------------------------------- بانک‌ها

_BANKS: dict | None = None


def load_banks() -> dict:
    """خواندن هر ۵ فایل بانک از data/ (با کش در حافظه)."""
    global _BANKS
    if _BANKS is None:
        banks = {}
        for name in ("templates-fa", "phrases-fa", "synonyms-fa", "names-fa", "franchises"):
            path = DATA / f"{name}.json"
            with open(path, encoding="utf-8") as fh:
                banks[name] = json.load(fh)
        _BANKS = banks
    return _BANKS


def fa_num(value) -> str:
    """عدد به ارقام فارسی."""
    return str(value).translate(FA_DIGITS)


def seed_from_facts(facts: dict) -> int:
    """seed قطعی از هش خبر (عنوان + لینک)."""
    raw = (facts.get("title_en", "") + "|" + facts.get("source_url", "")).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16)


# ------------------------------------------------------- استخراج حقایق

def _section_names(banks: dict, *sections: str) -> dict:
    names = {}
    for section in sections:
        names.update(banks["names-fa"].get(section, {}) or {})
    return names


def _longest_in(text_low: str, names: dict) -> str | None:
    """طولانی‌ترین نام بانک که در متن آمده (case-insensitive)."""
    for en in sorted(names, key=len, reverse=True):
        if len(en) < 3:
            continue
        if en.lower() in text_low:
            return en
    return None


def extract_franchise(title: str, summary: str, banks: dict):
    """نام اثر — دو مرحله‌ای (نقد ۳، پیام ۸: تیتر «Shin-Ei Animation» بود
    چون «Shin-Ei Animation» با ۱۷ حرف، طولانی‌تر از «Oishinbo» با ۸ حرف
    بود — در حالی که «Oishinbo» در بانک هم بود؛ طولانی‌ترین تطابق در هر
    جای متن، نام پس‌زمینه خلاصه را بر نام تیتر ترجیح می‌داد):
    ۱) نام‌های انیمه/مانگا در تیتر؛ ۲) همان‌ها در خلاصه؛
    ۳) استودیو/پلتفرم/شخص فقط وقتی هیچ نام انیمه‌ای نیست — و آن‌وقت
    new_name=True است (نام واقعی اثر در بانک نیست و باید اضافه شود).
    وگرنه عبارت گیومه‌دار در تیتر؛ وگرنه None.
    """
    anime = _section_names(banks, "anime", "manga_lightnovel")
    other = _section_names(banks, "studios", "platforms", "people")
    title_low = (title or "").lower()
    summary_low = (summary or "").lower()
    best = _longest_in(title_low, anime) or _longest_in(summary_low, anime)
    if best:
        return best, anime[best], False
    best = _longest_in(f"{title_low}\n{summary_low}", other)
    if best:
        return best, other[best], True
    quoted = re.search(r"[\"'‘’“”]([^\"'‘’“”]{3,80})[\"'‘’“”]", title)
    if quoted:
        return quoted.group(1).strip(), quoted.group(1).strip(), True
    return None, None, True


def extract_studio(title: str, summary: str, banks: dict):
    studios = banks["names-fa"].get("studios", {})
    hay_low = f"{title}\n{summary}".lower()
    for en in sorted(studios, key=len, reverse=True):
        if en.lower() in hay_low:
            return en, studios[en]
    return None, None


def extract_date(title: str, summary: str):
    """تاریخِ خبر — فقط تاریخی که تاریخِ خودِ خبر است، نه پس‌زمینه.

    تاریخ در تیتر = تاریخ خبر. در خلاصه فقط وقتی تاریخ خبر است که با
    فعل آینده/اعلام همراه باشد (will premiere / premieres / announced for)؛
    «premiered on October 2» گذشته است و تاریخ خبر نیست، پس نادیده گرفته
    می‌شود تا بدنه به‌اشتباه آن را تاریخ آینده جا نزند.
    روز طوری خوانده می‌شود که «January 2027» به «۲۰ ژانویه» تبدیل نشود.
    """
    months = "|".join(MONTHS_FA)

    def _fmt(month, day, year=None):
        out = f"{fa_num(day)} {MONTHS_FA[month]}"
        if year:
            out += f" {fa_num(year)}"
        return out

    m = re.search(rf"\b({months})\s+(\d{{1,2}})(?!\d)(?:\s*,?\s*(\d{{4}}))?", title)
    if m:
        return _fmt(m.group(1), m.group(2), m.group(3))
    m = re.search(rf"\b({months})\s+(\d{{4}})", title)
    if m:
        return f"{MONTHS_FA[m.group(1)]} {fa_num(m.group(2))}"
    m = re.search(r"\b(20\d{2})\b", title)
    if m:
        return fa_num(m.group(1))
    future = re.search(
        rf"(will premiere|premieres|premiering|announced for|set for|slated for)"
        rf"[^.;]{{0,80}}?\b({months})\s+(\d{{1,2}})(?!\d)(?:\s*,?\s*(\d{{4}}))?",
        summary, re.I)
    if future:
        return _fmt(future.group(2), future.group(3), future.group(4))
    future = re.search(
        rf"(will premiere|premieres|announced for)[^.;]{{0,80}}?\b({months})\s+(\d{{4}})",
        summary, re.I)
    if future:
        return f"{MONTHS_FA[future.group(2)]} {fa_num(future.group(3))}"
    return None


def extract_season(title: str, summary: str):
    """شماره فصل/بخش از تیتر/خلاصه، فقط اگر در منبع باشد."""
    text = f"{title} {summary}"
    m = re.search(r"[Ss]eason\s+(\d+)", text)
    if m:
        return fa_num(m.group(1))
    words = {"second": "۲", "third": "۳", "fourth": "۴", "fifth": "۵", "sixth": "۶"}
    m = re.search(r"\b(second|third|fourth|fifth|sixth)\s+(season|part)\b", text, re.I)
    if m:
        return words[m.group(1).lower()]
    m = re.search(r"\b(\d+)(?:st|nd|rd|th)\s+[Pp]art\b", text)
    if m:
        return fa_num(m.group(1))
    return None


def detect_event(title: str, summary: str) -> str:
    """نوع رویداد — اول از تیتر (خبر اصلی)، بعد از خلاصه.

    «premiered on July 2» در خلاصه، پس‌زمینه است نه خبر؛ پس «پخش» فقط وقتی
    رویداد است که در تیتر باشد یا در خلاصه با فعل آینده آمده باشد.

    Critic fix 2026-11-21 (review #1, content error msg 6): پایانِ یک اثر
    خودش خبر است و باید اول بررسی شود. خلاصه خبر پایان معمولاً اقتباس
    انیمه‌ایِ قدیمی را به‌عنوان پس‌زمینه می‌آورد («A 12-episode television
    anime adaptation ... aired in Spring 2025»)؛ بدون این بررسیِ اول،
    چکِ «adaptation» در خلاصه پس‌زمینه را رویداد می‌خواند و پست ادعا می‌کند
    اقتباس تازه‌ای اعلام شده است.
    """
    tl = title.lower()
    if any(k in tl for k in ("ends serialization", "end of serialization",
                             "ends its serialization", "manga ends",
                             "manga to end", "manga will end",
                             "final chapter", "final volume")):
        return "manga_ending"
    # Critic fix 2026-11-21 (review #1, run 44936475145): لایسنس (مثلاً
    # «Yen Press Licenses ...») خودش یک رویداد است، نه اعلام انیمه تازه.
    # بدون این شاخه، خبر لایسنس به «announcement» → «انیمه تازه» می‌افتاد و
    # کپشن می‌گفت انیمه تازه‌ای اعلام شده (همان کلاس خطای پیام ۶).
    if "licens" in tl:
        return "license"
    if "gets tv anime" in tl or "anime adaptation" in tl or "anime announced" in tl:
        return "adaptation"
    if "film" in tl or "movie" in tl:
        return "announcement"
    if "season" in tl and ("premier" in tl or "announce" in tl):
        return "date" if "premier" in tl else "announcement"
    if "new anime" in tl or "confirms" in tl:
        return "announcement"
    if "cast" in tl:
        return "casting"
    if any(k in tl for k in ("trailer", "teaser", "promo")):
        return "trailer"
    if "premier" in tl:
        return "date"
    text = f"{title} {summary}".lower()
    if any(k in text for k in ("manga will end", "will end in the",
                               "ends serialization")):
        return "manga_ending"
    if "licens" in text:
        return "license"
    if "cast" in text:
        return "casting"
    if any(k in text for k in ("will premiere", "premieres", "premiere date")):
        return "date"
    # Critic fix 2026-11-21: bare "adaptation"/"anime adaptation" removed —
    # it matched background ("an anime adaptation aired in Spring 2025").
    # Only a forward-looking adaptation announcement counts here.
    if any(k in text for k in ("gets tv anime", "anime adaptation announced",
                               "anime adaptation confirmed",
                               "will get an anime adaptation",
                               "new anime adaptation")):
        return "adaptation"
    if "box office" in text or "box-office" in text:
        return "box_office"
    if any(k in text for k in ("trailer", "teaser", "promo video", "character pv")):
        return "trailer"
    if any(k in text for k in ("award", "wins")):
        return "award"
    if any(k in text for k in ("event", "festival", "expo")):
        return "event"
    return "announcement"


def detect_category(title: str, summary: str, event: str, hint: str | None) -> str:
    """دسته‌بندی قانون‌محور (۶ دسته + خبر روز). hint معتبر بر بقیه مقدم است."""
    if hint in CATEGORIES_FA:
        return hint
    # Critic fix 2026-11-21 (review #1, msg 6): رویداد پایان مانگا دسته‌اش
    # «مانگا و اقتباس» است — نه «فیلم» (که کلمه «film» داخل نام استودیو
    # LIDENFILMS در خلاصه آن را فعال می‌کرد) و نه «فصل جدید» (که کلمه
    # «anime» در پس‌زمینه خلاصه آن را فعال می‌کرد).
    if event == "manga_ending":
        return "مانگا و اقتباس"
    # Critic fix 2026-11-21 (review #1, run 44936475145): لایسنس هم دسته‌اش
    # «مانگا و اقتباس» است (انتشار رسمی مانگا/ناول برای بازار تازه).
    if event == "license":
        return "مانگا و اقتباس"
    text = f"{title} {summary}".lower()
    # Critic fix 2026-11-21: «film»/«movie» با مرز کلمه — «LIDENFILMS»
    # نباید دسته «فیلم» را فعال کند.
    if re.search(r"\bfilms?\b|\bmovies?\b|box office", text):
        return "فیلم"
    if any(k in text for k in ("season", "new anime in production", "premier",
                               "second season", "gets 5th part", "part 2")):
        return "فصل جدید"
    if any(k in text for k in ("gets tv anime", "anime adaptation", "manga ends",
                               "manga gets", "light novel")):
        return "مانگا و اقتباس"
    if event == "trailer":
        return "تریلر"
    if any(k in text for k in ("studio", "merger", "acquires", "partnership")):
        return "استودیو"
    if event in ("event", "award"):
        return "رویداد"
    if "anime" in text:
        return "فصل جدید"
    return "رویداد"


def pubdate_fa(pubdate: str) -> str | None:
    """pubDate انگلیسی → «۲۰ نوامبر ۲۰۲۶» با ارقام فارسی."""
    if not pubdate:
        return None
    m = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})",
                  pubdate)
    full = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
            "May": "May", "Jun": "June", "Jul": "July", "Aug": "August",
            "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"}
    if m:
        return f"{fa_num(m.group(1))} {MONTHS_FA[full[m.group(2)]]} {fa_num(m.group(3))}"
    return None


def extract_facts(facts: dict, banks: dict) -> dict:
    title = facts.get("title_en", "") or ""
    summary = facts.get("summary_en", "") or ""
    fr_en, fr_fa, new_name = extract_franchise(title, summary, banks)
    studio_en, studio_fa = extract_studio(title, summary, banks)
    event = detect_event(title, summary)
    date_fa = extract_date(title, summary)
    season = extract_season(title, summary)
    syn = banks["synonyms-fa"]
    event_fa = syn.get("event_fa", {}).get(event, "خبر تازه")
    if event == "announcement" and season:
        event_fa = f"فصل {season}"
    elif event == "date" and season:
        event_fa = f"پخش فصل {season}"
    elif event == "casting":
        event_fa = "معرفی صداپیشه‌های تازه"
    elif event == "adaptation":
        event_fa = "اقتباس انیمه‌ای تازه"
    elif event == "manga_ending":
        # Critic fix 2026-11-21 (review #1, msg 6): رویداد تازه — پایان
        # سریال‌سازی مانگا. بدون این شاخه، event_fa پیش‌فرض «خبر تازه» بود
        # و تیتر هیچ نشانی از پایان نداشت.
        event_fa = "پایان سریال‌سازی"
    elif event == "license":
        # Critic fix 2026-11-21 (review #1, run 44936475145): رویداد تازه —
        # لایسنس (انتشار رسمی اثر برای بازار تازه، مثلاً Yen Press).
        event_fa = "لایسنس تازه"
    elif event == "trailer":
        event_fa = "تریلر تازه"
    elif event == "announcement":
        event_fa = "انیمه تازه"
    franchise = next((f for f in banks["franchises"]["franchises"]
                      if f["name_en"].lower() == (fr_en or "").lower()), None)
    if not franchise and fr_en:
        franchise = next((f for f in banks["franchises"]["franchises"]
                          if f["name_en"].lower() in (fr_en or "").lower()
                          or (fr_en or "").lower() in f["name_en"].lower()), None)
    is_breaking = bool(
        franchise and franchise.get("breaking_eligible")
        and event in ("announcement", "trailer", "date")
    )
    return {
        "title_en": title, "summary_en": summary,
        "source_name": facts.get("source_name", "") or "",
        "source_url": facts.get("source_url", "") or "",
        "pubDate": facts.get("pubDate", "") or "",
        "fr_en": fr_en, "fr_fa": fr_fa, "new_name": new_name,
        "studio_en": studio_en, "studio_fa": studio_fa,
        "event": event, "event_fa": event_fa,
        "date_fa": date_fa, "season": season,
        "category": detect_category(title, summary, event, facts.get("category_hint")),
        "is_breaking": is_breaking,
        "franchise": franchise,
    }


# ------------------------------------------------------- جمله‌سازی

def _fill(pattern: str, ctx: dict) -> str:
    out = pattern
    for key, val in ctx.items():
        out = out.replace("{" + key + "}", val or "")
    return re.sub(r"\s+", " ", out).strip()


def _has_placeholder(text: str) -> bool:
    return bool(re.search(r"\{[a-z_]+\}|\[…\]|___", text))


_SEASON_RETURN_RE = re.compile(
    r"season\s+([2-9]|1[0-9])\b|2nd season|3rd season|[4-9]th season|"
    r"second season|third season|fourth season|fifth season|"
    r"sixth season|seventh season|eighth season|ninth season|"
    r"new season\b|\bsequel\b",
    re.IGNORECASE,
)


def _is_returning_season(fx: dict) -> bool:
    """آیا خبر از فصل برگشتی (فصل ۲ به بعد / دنباله) است، نه انیمه کاملاً
    تازه؟ فقط نشانه‌های صریح شماره فصل / دنباله قبول‌اند — «season» تنها
    کافی نیست (فصل پخش هم season است) و «new anime» فصل برگشتی نیست.
    منتقد، ۲۲ نوامبر ۲۰۲۶ — پیام‌های ۱۰ تا ۱۲: ‏why_new_season‏ («قصه ادامه
    دارد») برای اعلامیه انیمه کاملاً تازه غلط بود."""
    text = f"{fx['title_en']} {fx['summary_en']}".lower()
    return bool(_SEASON_RETURN_RE.search(text))


def _date_fa_parts(date_fa: str | None) -> tuple[str | None, str | None]:
    """date_fa فارسی («۴ ژانویه ۲۰۲۷» / «آوریل ۲۰۲۷» / «۲۰۲۷») را به
    (ماه انگلیسی، سال) برمی‌گرداند؛ برای سنجش تاریخ «premiered» با تاریخ
    همین آیتم (نقد ۳، پیام ۱۸)."""
    if not date_fa:
        return None, None
    month_en = None
    for en, fa in MONTHS_FA.items():
        if fa in date_fa:
            month_en = en
            break
    year = None
    m = re.search(r"\d{4}", date_fa.translate(EN_DIGITS))
    if m:
        year = m.group(0)
    return month_en, year


def _premiered_date_matches(fx: dict) -> bool:
    """آیا تاریخی که به «premiered» در خلاصه چسبیده، همان date_fa همین
    آیتم است؟ «premiered on July 2, 2025» برای بخشی که date_fa آن
    «آوریل ۲۰۲۷» است، پس‌زمینه است — نه پخش همین بخش (نقد ۳، پیام ۱۸:
    خلاصه MAL می‌گفت بخش قبلی Tougen Anki پخش شده و بدنه از همان کلمه،
    «بخش تازه پیش‌تر پخش خود را آغاز کرده بود» ساخت؛ در حالی که قوس تازه
    هنوز پخش نشده بود). بدون date_fa یا بدون تاریخِ چسبیده به «premiered»،
    گارد رد می‌کند (محافظه‌کارانه: از دست‌رفتن یک قالب، بهتر از ادعای
    غلط است)."""
    month_fa, year_fa = _date_fa_parts(fx.get("date_fa"))
    if not year_fa:
        return False
    text = (fx.get("summary_en") or "").lower()
    months = "|".join(m.lower() for m in MONTHS_FA)
    for m in re.finditer(r"premiered", text):
        window = text[m.start():m.start() + 90]
        dm = re.search(
            rf"\b({months})\s+(\d{{1,2}})(?:\s*,\s*|\s+)(\d{{4}})"
            rf"|\b({months})\s+(\d{{4}})"
            rf"|\b(20\d{{2}})\b",
            window)
        if not dm:
            continue
        if dm.group(1):  # ماه + روز + سال
            if dm.group(3) != year_fa:
                continue
            if month_fa and dm.group(1).capitalize() != month_fa:
                continue
            return True
        if dm.group(4):  # ماه + سال
            if dm.group(5) != year_fa:
                continue
            if month_fa and dm.group(4).capitalize() != month_fa:
                continue
            return True
        if dm.group(6) == year_fa:  # فقط سال
            return True
    return False


def _has_premiered(fx: dict) -> bool:
    """«پخش آغاز شده» فقط وقتی درست است که پخش مال همین خبر باشد — نه
    پس‌زمینه خلاصه (منتقد، ۲۲ نوامبر ۲۰۲۶ — پیام ۱۰: خلاصه ANN می‌گفت پروژه
    قبلی Mugendai Mewtype «premiered on July 2» و body_season_premiered از
    همان کلمه، «بخش تازه پیش‌تر پخش خود را آغاز کرده بود» ساخت؛ در حالی که
    خبر، اعلامیه انیمه کاملاً تازه بود). پس: «premiered» در تیتر، یا در
    خلاصه + نشانه فصل برگشتی + تاریخِ چسبیده به «premiered» همان date_fa
    همین آیتم باشد (نقد ۳، پیام ۱۸)."""
    title = (fx["title_en"] or "").lower()
    text = f"{fx['title_en']} {fx['summary_en']}".lower()
    if "premiered" in title:
        return True
    return ("premiered" in text and _is_returning_season(fx)
            and _premiered_date_matches(fx))


def _eligible_bodies(fx: dict, banks: dict):
    """بدنه‌ها فقط وقتی انتخاب می‌شوند که حقیقتشان در منبع باشد.

    Critic fix 2026-11-21 (review #1, msg 6): body_studio («ساخت این بخش
    تازه بر عهده {studio} است») و body_manga_origin («... چشم‌به‌راه نسخه
    انیمه») فقط وقتی درست‌اند که خبر، یک تولید/اقتباس تازه باشد. برای
    رویداد پایان (manga_ending) استودیوی پس‌زمینه خلاصه (مثلاً Crunchyroll
    که فقط پخش‌کننده اقتباس قدیمی بود) نباید به «تهیه‌کننده بخش تازه»
    تبدیل شود — پس هر دو فقط برای رویدادهای تولید تازه واجدند.
    """
    text = f"{fx['title_en']} {fx['summary_en']}".lower()
    has_date_month = bool(fx["date_fa"]) and any(
        m in fx["date_fa"] for m in MONTHS_FA.values())
    _new_production = fx["event"] in ("adaptation", "announcement", "date",
                                      "trailer", "casting")
    has = {
        "date": bool(fx["date_fa"]),
        "date_month": has_date_month,
        "cast": "cast" in text,
        "visual": any(k in text for k in ("visual", "key visual", "teaser visual")),
        "trailer": any(k in text for k in ("trailer", "promo", " pv ")),
        # Critic fix 2026-11-22 (review #2): «premiered» پس‌زمینه خلاصه
        # (پروژه قبلی) نباید body_season_premiered را واجد کند — فقط پخشِ
        # همین خبر (_has_premiered: تیتر، یا خلاصه + فصل برگشتی).
        "premiered": _has_premiered(fx),
        "manga": any(k in text for k in ("manga", "light novel")) and _new_production,
        "studio": bool(fx["studio_en"]) and _new_production,
        "event_live": any(k in text for k in ("livestream", "anniversary", "event")),
        # بسته بانک ۲۰۲۶-۱۱-۲۳: فصل برگشتی (فصل ۲ به بعد / دنباله) — فقط
        # نشانه‌های صریح شماره فصل / دنباله (مثل بدنه why_sequel).
        "returning": _is_returning_season(fx),
    }
    has_date_month = bool(fx["date_fa"]) and any(
        m in fx["date_fa"] for m in MONTHS_FA.values())
    need = {
        "body_source_date": "date", "body_premiere": "date_month", "body_cast": "cast",
        "body_staff_visual": "visual", "body_trailer": "trailer",
        "body_season_premiered": "premiered", "body_manga_origin": "manga",
        "body_studio": "studio", "body_anniversary": "event_live",
        "body_more_detail": None, "body_wait": None, "body_franchise_context": None,
        # بسته بانک ۲۰۲۶-۱۱-۲۳: بدنه‌های بلند (۱۵۰–۲۰۰ حرف) برای اینکه خبرهای
        # کوتاه به کف ۶۰۰ حرف کپشن برسند — بدون شل‌کردن هیچ گیت.
        "body_patience_long": None, "body_source_follow_long": None,
        "body_franchise_wait_long": None, "body_calendar_long": None,
        "body_trailer_long": "trailer", "body_cast_long": "cast",
        "body_visual_long": "visual", "body_premiere_long": "date_month",
        "body_sequel_long": "returning", "body_studio_long": "studio",
    }
    out = []
    for b in banks["templates-fa"]["bodies"]:
        key = need.get(b["id"])
        if key is None or has.get(key):
            out.append(b)
    return out


def _why_templates(fx: dict, banks: dict):
    text = f"{fx['title_en']} {fx['summary_en']}".lower()
    has = {
        "date": bool(fx["date_fa"]),
        "cast": "cast" in text,
        "trailer": any(k in text for k in ("trailer", "promo", " pv ")),
        "adaptation": any(k in text for k in ("adaptation", "gets tv anime")),
        "manga": "manga" in text,
        "license": "licens" in text,
        "visual": any(k in text for k in ("visual", "key visual")),
        "studio": bool(fx["studio_en"]),
        # Critic fix 2026-11-22 (review #2): مثل بدنه — «premiered»
        # پس‌زمینه نباید why_continuation («ادامه مستقیم قصه‌ای که از پیش
        # آغاز کرده بود») را واجد کند.
        "premiered": _has_premiered(fx),
        # بسته بانک ۲۰۲۶-۱۱-۲۳: فصل برگشتی — برای why_sequel.
        "returning": _is_returning_season(fx),
    }
    need = {
        "why_premiere_date": "date", "why_new_season": None, "why_cast": "cast",
        # Critic fix 2026-11-22 (review #2): «چرا»ی مخصوص اعلامیه انیمه
        # کاملاً تازه — «دنیای … بزرگ‌تر می‌شود»، نه «قصه ادامه دارد».
        "why_new_announcement": None, "why_trailer": "trailer", "why_adaptation": "manga",
        "why_adaptation_generic": "adaptation",
        "why_visual_staff": "visual", "why_date_set": "date",
        "why_first_look": None, "why_studio": "studio",
        "why_continuation": "premiered",
        # Critic fix 2026-11-21 (review #1, msg 6): «چرا»ی مخصوص پایان مانگا.
        "why_manga_ending": "manga",
        # Critic fix 2026-11-21 (review #1, run 44936475145): «چرا»ی مخصوص
        # لایسنس — نه why_adaptation/why_new_season که از لایسنس، «انیمه تازه
        # در راه است» می‌ساختند.
        "why_license": "license",
        # بسته بانک ۲۰۲۶-۱۱-۲۳: «چرا»های بلند برای تریلر/کست/ویژوال/دنباله.
        "why_trailer_long": "trailer", "why_cast_long": "cast",
        "why_visual_long": "visual", "why_sequel": "returning",
    }
    out = []
    for w in banks["templates-fa"]["why"]:
        key = need.get(w["id"])
        if key is None or has.get(key):
            out.append(w)
    return out


def _hashtag(fr_en: str | None, category: str, banks: dict) -> list[str]:
    tags = ["#انیمه"]
    if fr_en:
        short = fr_en.split(":")[0].strip()
        slug = re.sub(r"[^A-Za-z0-9]+", " ", short).strip().title().replace(" ", "")
        slug = re.sub(r"[^A-Za-z0-9]", "", slug)
        if slug:
            tags.append(f"#{slug}")
    cat_tag = banks["franchises"].get("categories", {}).get(category)
    if cat_tag and cat_tag not in tags:
        tags.append(cat_tag)
    return tags[:3]


def _build_once(fx: dict, banks: dict, rng: random.Random):
    """یک بار ساخت کامل پست با انتخاب‌های قطعیِ rng."""
    templates = banks["templates-fa"]
    phrases = banks["phrases-fa"]
    ctx = {
        "fr_fa": fx["fr_fa"] or "این اثر",
        "fr_en": fx["fr_en"] or "Anime",
        "event_fa": fx["event_fa"],
        "date_fa": fx["date_fa"] or "",
        "source_fa": fx["source_name"],
        "studio_fa": fx["studio_fa"] or "",
        "opener": rng.choice(phrases["openers"]),
        "fact_date": (
            f"پخش اثر از {fx['date_fa']} آغاز می‌شود"
            if fx["date_fa"] and any(m in fx["date_fa"] for m in MONTHS_FA.values())
            else (f"اثر برای {fx['date_fa']} اعلام شده است" if fx["date_fa"] else "")
        ),
        "why_fact": fx["date_fa"] or fx["event_fa"],
    }
    # تیتر: اولین قالبِ ≤۷۰ کاراکتر (نام انگلیسی اثر همیشه در تیتر است)
    # Critic fix 2026-11-21 (review #1, msg 6): برای رویداد پایان فقط
    # قالب‌های خنثی (اعلام/تایید) مجازند — قالب‌های «برمی‌گردد / در راه است /
    # مسیر تازه / خبر خوب / صبر جواب داد» برای پایان نادرست‌اند (تست T1 اول
    # لید «برگشته است» را برای پایان مانگا تولید کرد).
    # Critic fix 2026-11-21 (review #1, run 44936475145): همان محدودیت برای
    # لایسنس — «در راه است / برگشته است» برای لایسنس هم نادرست است.
    _ending_safe_titles = {"title_01", "title_03", "title_05", "title_07",
                           "title_08", "title_10"}
    _ending_safe_leads = {"lead_02", "lead_03", "lead_12", "lead_13",
                          "lead_15", "lead_16"}
    _titles = templates["titles"]
    _leads = templates["leads"]
    if fx["event"] in ("manga_ending", "license"):
        _titles = [t for t in _titles if t["id"] in _ending_safe_titles] or _titles
        _leads = [l for l in _leads if l["id"] in _ending_safe_leads] or _leads
    # Critic fix 2026-11-22 (run 44971616356 — پیام‌های ۱۱ و ۱۲): قالب
    # title_04 («{fr_en} | {event_fa} در {date_fa}») وقتی تاریخ ندارد، تیتر
    # را با «در»ِ آویزان تمام می‌کند («BanG Dream! Yume∞Mita | انیمه تازه
    # در»). بدون تاریخ، این قالب مجاز نیست.
    if not fx["date_fa"]:
        _titles = [t for t in _titles if t["id"] != "title_04"] or _titles
    title = None
    title_id = None
    shuffled_titles = _titles[:]
    rng.shuffle(shuffled_titles)
    for t in shuffled_titles:
        cand = _fill(t["pattern"], ctx)
        if len(cand) <= 70 and not _has_placeholder(cand):
            title, title_id = cand, t["id"]
            break
    if title is None:
        title = f"{ctx['fr_en']} | {ctx['event_fa']}"
        title = title[:70]
        title_id = "title_fallback"
    # لید
    lead_tpl = rng.choice(_leads)
    lead = _fill(lead_tpl["pattern"], ctx)
    # بدنه: ۲ جمله واجد شرایط (سوم فقط اگر کپشن کوتاه ماند)
    bodies = _eligible_bodies(fx, banks)
    specific = [b for b in bodies if b["id"] not in ("body_more_detail", "body_wait", "body_franchise_context")]
    generic = [b for b in bodies if b["id"] in ("body_more_detail", "body_wait", "body_franchise_context")]
    # دروازه ۱۱ (پیام ۲۷، Hidan no Aria، ۲۳ نوامبر ۲۰۲۶): other هیچ قالب
    # تاریخی ندارد — همه قالب‌های تاریخی یک مجموعه‌اند. پیش‌تر other فقط
    # body_premiere و body_source_date را کنار می‌گذاشت، نه body_premiere_long
    # را (بسته بانک ۲۳ نوامبر)؛ پس همان قالب دوبار (body_premiere_long × ۲)
    # یا دو قالب با جمله هم‌پوشان (body_premiere + body_premiere_long — جمله
    # اولی پیشوند دومی است) در بدنه می‌آمد و جمله بلند دوبار تکرار می‌شد.
    date_ids = ("body_premiere", "body_source_date", "body_premiere_long")
    date_bodies = [b for b in specific if b["id"] in date_ids]
    other = [b for b in specific if b["id"] not in date_ids]
    rng.shuffle(date_bodies)
    rng.shuffle(other)
    rng.shuffle(generic)
    # تاریخ خبر (مهم‌ترین حقیقت) حتماً در بدنه می‌آید؛ دو بدنه تاریخی با هم نه
    body_tpls = (date_bodies[:1] + other + generic)[:2]
    body = " ".join(_fill(b["pattern"], ctx) for b in body_tpls)
    # چرا مهم است؟ — یک جمله خاص همین خبر
    why_tpls = _why_templates(fx, banks)
    preferred = {
        "adaptation": ["why_adaptation", "why_adaptation_generic", "why_visual_staff"],
        "casting": ["why_cast", "why_cast_long", "why_visual_staff", "why_visual_long"],
        "date": ["why_premiere_date", "why_date_set"],
        "trailer": ["why_trailer", "why_trailer_long", "why_visual_long"],
        # Critic fix 2026-11-21 (review #1, msg 6): برای پایان مانگا فقط
        # why_manga_ending — نه why_adaptation (که از کلمه «adaptation» در
        # پس‌زمینه خلاصه تغذیه می‌شد و می‌گفت اقتباس تازه می‌آید).
        "manga_ending": ["why_manga_ending"],
        # Critic fix 2026-11-21 (review #1, run 44936475145): برای لایسنس
        # فقط why_license — نه why_new_season (که می‌گفت «قصه ادامه دارد و
        # بخشی که مدت‌ها درباره‌اش حرف زده می‌شد، حالا واقعا ساخته می‌شود»).
        "license": ["why_license"],
        # Critic fix 2026-11-21 (review #1, item 14): why_continuation از
        # announcement حذف شد — «ادامه مستقیم قصه‌ای که از پیش آغاز کرده بود»
        # برای اعلامیه تولید کاملاً تازه غلط است.
        # Critic fix 2026-11-22 (review #2): برای اعلامیه انیمه کاملاً تازه
        # why_new_season («قصه ادامه دارد») هم غلط است (پیام‌های ۱۰–۱۲) —
        # فقط وقتی فصل برگشتی است why_new_season؛ وگرنه why_new_announcement
        # («دنیای … بزرگ‌تر می‌شود»).
        "announcement": (["why_new_season", "why_sequel"] if _is_returning_season(fx)
                         else ["why_new_announcement"]),
        "box_office": ["why_first_look"],
    }.get(fx["event"], [])
    rng.shuffle(why_tpls)
    why_tpls.sort(key=lambda w: 0 if w["id"] in preferred else 1)
    why_tpl = why_tpls[0] if why_tpls else templates["why"][0]
    why = _fill(why_tpl["pattern"], ctx)
    # بستن جمله «چرا مهم است؟» با برچسب مشخص
    why_line = f"چرا مهم است؟ {why}"
    note = ""
    pub_fa = pubdate_fa(fx["pubDate"])
    if pub_fa:
        # بسته بانک ۲۰۲۶-۱۱-۲۳: چند note بلندتر (۹۰–۱۲۰ حرف) به‌جای یک جمله
        # ثابت ~۵۰ حرفی — پل طولی برای کپشن‌های ۵۵۰–۵۹۹ حرفی (rewrite_post
        # وقتی کپشن زیر ۶۰۰ است، همین note را می‌گذارد).
        notes = templates.get("notes") or []
        if notes:
            ctx["pub_fa"] = pub_fa
            note = _fill(rng.choice(notes)["pattern"], ctx)
        else:
            note = f"این خبر را {fx['source_name']} در {pub_fa} منتشر کرد."
    hashtags = _hashtag(fx["fr_en"], fx["category"], banks)
    caption = (
        f"{title}\n\n{lead}\n\n{body}\n\n{why_line}\n\n"
        f"منبع: {fx['source_name']}\n{fx['source_url']}\n\n{' '.join(hashtags)}"
    )
    template_ids = {
        "title": title_id, "lead": lead_tpl["id"],
        "bodies": [b["id"] for b in body_tpls], "why": why_tpl["id"],
    }
    return {
        "title": title, "caption": caption, "lead": lead, "body": body,
        "why": why, "note": note, "hashtags": hashtags,
        "template_ids": template_ids,
    }


# ------------------------------------------------------- ۱۰ دروازه کیفی

def _ngram_similarity(a: str, b: str, n: int = 5) -> float:
    """شباهت 5-gram کاراکتری پس از نرمال‌سازی (برای فارسی/انگلیسی نزدیک صفر است)."""
    def grams(s: str):
        s = re.sub(r"\s+", " ", s.lower())
        s = re.sub(r"[^\w ]", "", s, flags=re.UNICODE)
        return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}
    ga, gb = grams(a), grams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def _word_similarity(a: str, b: str) -> float:
    wa = set(re.findall(r"\w+", a.lower()))
    wb = set(re.findall(r"\w+", b.lower()))
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _has_repeated_sentence(caption: str, min_len: int = 40) -> bool:
    """یک جمله بلند (≥ ۴۰ حرف) دوبار در یک کپشن آمده است؟ — دروازه ۱۱.

    پیام ۲۷ (Hidan no Aria، ۲۳ نوامبر ۲۰۲۶): جمله body_premiere_long دوبار
    پشت سر هم در بدنه آمد. جمله‌ها با «.»، «!»، «؟»، «؛» و خط تازه جدا
    می‌شوند؛ عبارت‌های کوتاه (< ۴۰ حرف) شمرده نمی‌شوند تا تکرارهای طبیعی
    (نام اثر، «خبر تازه») خطا نخورند. لینک منبع از شمارش کنار گذاشته می‌شود.
    """
    text = re.sub(r"https?://\S+", "", caption)
    segs = [re.sub(r"\s+", " ", s).strip()
            for s in re.split(r"[.!؟؛\n]+", text)]
    seen = set()
    for s in segs:
        if len(s) >= min_len:
            if s in seen:
                return True
            seen.add(s)
    return False


def check_gates(caption: str, title: str, fx: dict, why: str,
                recent_posts: list | None = None,
                template_usage: dict | None = None,
                template_ids: dict | None = None) -> dict:
    """هر ۱۱ دروازه را می‌سنجد؛ خروجی {gate_id: bool}."""
    gates: dict[str, bool] = {}
    gates["length"] = 600 <= len(caption) <= 850 and len(title) <= 70
    gates["no_placeholder"] = not _has_placeholder(caption)
    # سازگاری رویداد با منبع (دروازه ۹ — منتقد، بررسی #۱، خطای پیام ۶):
    # اگر منبع از پایان می‌گوید، کپشن نباید ادعای اقتباس/پخش تازه کند —
    # و برعکس، اگر منبع اعلام اقتباس تازه است، کپشن نباید از پایان بگوید.
    # این دروازه همان شکافی را می‌بندد که ۸ دروازه ساختاری ندیدند: وارونگی
    # رویداد (پایان مانگا → «اقتباس انیمه‌ای تازه اعلام شد»).
    _src = f"{fx['title_en']} {fx['summary_en']}".lower()
    _ending_src = any(k in _src for k in (
        "ends serialization", "end of serialization", "final chapter",
        "final volume", "will end", "manga ends", "concludes"))
    _adapt_src = any(k in _src for k in (
        "gets tv anime", "anime adaptation announced", "new anime adaptation"))
    _license_src = "licens" in _src
    _claims_adapt = any(k in caption for k in (
        "اقتباس انیمه‌ای تازه", "انیمه تازه"))
    _claims_end = any(k in caption for k in (
        "پایان سریال‌سازی", "تمام می‌شود", "به پایان رسید"))
    _claims_license = "لایسنس" in caption
    gates["event_consistency"] = not (
        (_ending_src and _claims_adapt) or (_adapt_src and _claims_end)
        # Critic fix 2026-11-21 (review #1, run 44936475145): منبع لایسنس +
        # ادعای انیمه تازه = وارونگی (Yen Press Licenses → «انیمه تازه اعلام
        # شد»)؛ و برعکس، منبع اقتباس تازه + ادعای لایسنس هم ناسازگار است.
        or (_license_src and _claims_adapt) or (_adapt_src and _claims_license))
    gates["no_placeholder"] = not _has_placeholder(caption)
    # انگلیسی محدود: فقط نام اثر/استودیو/منبع + لینک + هشتگ مجاز است
    allowed = set()
    for name in (fx.get("fr_en"), fx.get("studio_en"), fx.get("source_name")):
        if name:
            allowed.update(re.findall(r"[A-Za-z]+", name))
    body_no_url = re.sub(r"https?://\S+", "", caption)
    body_no_tags = re.sub(r"#\S+", "", body_no_url)
    latin_words = re.findall(r"[A-Za-z]{2,}", body_no_tags)
    gates["english_limited"] = all(w in allowed for w in latin_words)
    gates["source_similarity"] = (
        _ngram_similarity(caption, fx["summary_en"]) < 0.25
    )
    recent = recent_posts or []
    gates["recent_similarity"] = all(
        _word_similarity(caption, p) < 0.60 for p in recent
    )
    usage = (template_usage or {}).get((template_ids or {}).get("lead"), 0)
    gates["template_freshness"] = usage <= 3
    # «چرا مهم است؟» خاص: نام اثر + یک حقیقت مشخص (تاریخ/تریلر/کست/پخش/اقتباس/پایان)
    # Critic fix 2026-11-21 (review #1, msg 6 + live HOLDs): خودِ event_fa هم
    # یک حقیقت مشخصِ همین خبر است (مثلاً «انیمه تازه» در why_new_season).
    # بدون این، why_new_season برای اعلامیه‌های بدون فصل همیشه why_specific
    # را رد می‌کرد — همان علتی که Oshi No Ko ‏(۸۵)‏ و BanG Dream ‏(۸۰)‏ را در
    # ران زنده ۲۱ نوامبر HOLD کرد (بعد از حذف why_continuation از announcementها).
    # پیش‌فرض کلی «خبر تازه» نشانه نیست و شمرده نمی‌شود.
    specific_markers = [
        fx.get("date_fa"), "تریلر", "صداپیشه", "پخش", "کی‌ویژوال",
        "اقتباس", "فصل", "استودیو", "پایان", "لایسنس",
    ]
    _ev = fx.get("event_fa")
    if _ev and _ev != "خبر تازه":
        specific_markers.append(_ev)
    _fr_names = [n for n in (fx.get("fr_fa"), fx.get("fr_en")) if n]
    gates["why_specific"] = bool(
        why and any(n in why for n in _fr_names)
        and any(m and m in why for m in specific_markers)
        and not any(g in why for g in GENERIC_WHY)
        and why.count("؟") + why.count(".") <= 2
    )
    # اعداد/تاریخ‌ها از منبع: هر عدد در کپشن باید در تیتر/خلاصه/pubDate باشد
    source_digits = set(re.findall(r"\d+", f"{fx['title_en']} {fx['summary_en']} {fx['pubDate']}"))
    caption_digits = set(re.findall(r"\d+", caption.translate(EN_DIGITS)))
    # لینک منبع را از شمارش عدد کنار بگذار
    caption_no_url = re.sub(r"https?://\S+", "", caption)
    caption_digits = set(re.findall(r"\d+", caption_no_url.translate(EN_DIGITS)))
    gates["numbers_dates"] = caption_digits.issubset(source_digits)
    # ماه فارسی در کپشن باید ماهی باشد که در منبع آمده
    months_in_caption = [fa for fa in MONTHS_FA.values()
                         if re.search(rf"(?<!\w){re.escape(fa)}(?!\w)", caption_no_url)]
    _src_text = f"{fx['title_en']} {fx['summary_en']} {fx['pubDate']}"
    months_in_source = [MONTHS_FA[m] for m in MONTHS_FA if m in _src_text]
    _abbr = {"Jan": "January", "Feb": "February", "Mar": "March", "Apr": "April",
             "May": "May", "Jun": "June", "Jul": "July", "Aug": "August",
             "Sep": "September", "Oct": "October", "Nov": "November", "Dec": "December"}
    months_in_source += [MONTHS_FA[_abbr[a]] for a in _abbr if a in _src_text]
    if months_in_caption and not set(months_in_caption).issubset(set(months_in_source)):
        gates["numbers_dates"] = False
    # دروازه ۱۰ — کلمه تکراری پشت سر هم (منتقد، ۲۲ نوامبر ۲۰۲۶ — پیام ۱۰):
    # قالب lead_11 («{event_fa} تازه اثر اعلام شد») با event_fa «انیمه تازه»
    # «انیمه تازه تازه اثر اعلام شد» ساخت. هیچ کپشن خبری نباید یک کلمه را
    # دوبار پشت سر هم داشته باشد؛ این دروازه کلِ این کلاس خطا را می‌گیرد،
    # حتی اگر قالب دیگری هم همین عیب را داشته باشد. فقط در یک خط می‌سنجد
    # (نه دو سرِ پاراگراف — تیتر «…انیمه تازه» + لید «تازه‌ترین خبر…» خطا
    # نیست) و «تازه» در «تازه‌ترین» را تکرار نمی‌شمرد (ZWNJ در lookahead).
    # بسته بانک ۲۰۲۶-۱۱-۲۳: lookbehind در آغاز — نام فرنچایزی که خودش به
    # «را» ختم می‌شود («یوزاکورا را») نباید خطا بخورد؛ تکرار واقعی فقط
    # وقتی است که کلمه اول هم از مرز کلمه شروع شده باشد.
    gates["no_double_word"] = not re.search(
        r"(?<![\u0600-\u06FF\u200C])([\u0600-\u06FF]{2,})[ \t]+\1(?![\u0600-\u06FF\u200C])",
        caption_no_url)
    # دروازه ۱۱ — جمله بلند تکراری در یک کپشن (پیام ۲۷، ۲۳ نوامبر ۲۰۲۶):
    # همان جمله نباید دوبار بیاید، حتی اگر از دو قالب متفاوت آمده باشد
    # (body_premiere + body_premiere_long — جمله اولی پیشوند دومی است).
    # نگهبان نهایی است: رفع ریشه‌ای در _build_once جلوی ساخت دوباره را
    # می‌گیرد، ولی این دروازه هر منبع تکرار دیگر را هم در پست‌شدن می‌گیرد.
    gates["no_repeated_sentence"] = not _has_repeated_sentence(caption_no_url)
    return gates


# ------------------------------------------------------- واسط اصلی

def rewrite_post(facts: dict, seed: int | None = None,
                 recent_posts: list | None = None,
                 template_usage: dict | None = None) -> dict:
    """بازنویسی یک خبر به پست فارسی. seed اگر داده نشد از هش خبر ساخته می‌شود."""
    banks = load_banks()
    if seed is None:
        seed = seed_from_facts(facts)
    fx = extract_facts(facts, banks)
    best = None
    best_score = -1
    for attempt in range(30):
        rng = random.Random(seed + attempt * 7919)
        built = _build_once(fx, banks, rng)
        caption = built["caption"]
        # تنظیم طول: کوتاه → جمله یادداشت (تاریخ انتشار منبع)؛ بلند → حذف جمله بدنه دوم
        if len(caption) < 600 and built["note"]:
            caption = caption.replace(
                f"\n\nمنبع: {fx['source_name']}",
                f"\n\n{built['note']}\n\nمنبع: {fx['source_name']}", 1)
            built["caption"] = caption
        if len(caption) > 850:
            parts = built["body"].split(". ")
            if len(parts) > 1:
                body2 = ". ".join(parts[:1])
                if not body2.endswith("."):
                    body2 += "."
                caption = caption.replace(built["body"], body2, 1)
                built["caption"] = caption
                built["body"] = body2
        gates = check_gates(built["caption"], built["title"], fx, built["why"],
                            recent_posts=recent_posts,
                            template_usage=template_usage,
                            template_ids=built["template_ids"])
        passed = [g for g, ok in gates.items() if ok]
        score = len(passed)
        if score > best_score:
            best_score, best = score, (built, gates, passed)
        # بسته بانک ۲۰۲۶-۱۱-۲۳: حذف early-break (توقف در اولین ۹/۱۰ با طول
        # معتبر) — هر ۳۰ تلاش امتحان می‌شود تا ۱۱/۱۱ احتمالی در تلاش‌های
        # بعدی از دست نرود؛ best فقط وقتی بهتر شود عوض می‌شود، پس حذف
        # break هیچ آیتمی را که پیش‌تر قبول می‌شد رد نمی‌کند.
    built, gates, passed = best
    return {
        "title": built["title"],
        "caption": built["caption"],
        "category": fx["category"],
        "hashtags": built["hashtags"],
        "gates_passed": passed,
        "template_ids": built["template_ids"],
        "is_breaking": fx["is_breaking"],
        "franchise_en": fx["fr_en"],
        "new_name": fx["new_name"],
    }


# ------------------------------------------------------- CLI

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="موتور بازنویسی فارسی قالبی انیمه‌خبر")
    ap.add_argument("--facts", help="فایل JSON با facts یک خبر")
    ap.add_argument("--seed", type=int, default=None, help="seed (پیش‌فرض: هش خبر)")
    ap.add_argument("--facts-json", help="facts به‌صورت رشته JSON")
    args = ap.parse_args(argv)
    if args.facts:
        with open(args.facts, encoding="utf-8") as fh:
            facts = json.load(fh)
    elif args.facts_json:
        facts = json.loads(args.facts_json)
    else:
        ap.error("یکی از --facts یا --facts-json لازم است")
    result = rewrite_post(facts, args.seed)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
