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

۸ دروازه کیفی (ARCHITECTURE.md §4.3 / filter-v2.md §7.1) در check_gates
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

def _all_names(banks: dict) -> dict:
    names = {}
    for section in ("anime", "manga_lightnovel", "studios", "platforms", "people"):
        names.update(banks["names-fa"].get(section, {}))
    return names


def extract_franchise(title: str, summary: str, banks: dict):
    """نام اثر: طولانی‌ترین نام مصوب که در تیتر/خلاصه آمده؛ وگرنه عبارت گیومه‌دار."""
    names = _all_names(banks)
    hay = f"{title}\n{summary}"
    hay_low = hay.lower()
    best = None
    for en in sorted(names, key=len, reverse=True):
        if len(en) < 3:
            continue
        if en.lower() in hay_low:
            best = en
            break
    if best:
        return best, names[best], False
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
    """
    tl = title.lower()
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
    if "cast" in text:
        return "casting"
    if any(k in text for k in ("will premiere", "premieres", "premiere date")):
        return "date"
    if any(k in text for k in ("gets tv anime", "anime adaptation", "adaptation")):
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
    text = f"{title} {summary}".lower()
    if any(k in text for k in ("film", "movie", "box office")):
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


def _eligible_bodies(fx: dict, banks: dict):
    """بدنه‌ها فقط وقتی انتخاب می‌شوند که حقیقتشان در منبع باشد."""
    text = f"{fx['title_en']} {fx['summary_en']}".lower()
    has_date_month = bool(fx["date_fa"]) and any(
        m in fx["date_fa"] for m in MONTHS_FA.values())
    has = {
        "date": bool(fx["date_fa"]),
        "date_month": has_date_month,
        "cast": "cast" in text,
        "visual": any(k in text for k in ("visual", "key visual", "teaser visual")),
        "trailer": any(k in text for k in ("trailer", "promo", " pv ")),
        "premiered": "premiered" in text,
        "manga": any(k in text for k in ("manga", "light novel")),
        "studio": bool(fx["studio_en"]),
        "event_live": any(k in text for k in ("livestream", "anniversary", "event")),
    }
    has_date_month = bool(fx["date_fa"]) and any(
        m in fx["date_fa"] for m in MONTHS_FA.values())
    need = {
        "body_source_date": "date", "body_premiere": "date_month", "body_cast": "cast",
        "body_staff_visual": "visual", "body_trailer": "trailer",
        "body_season_premiered": "premiered", "body_manga_origin": "manga",
        "body_studio": "studio", "body_anniversary": "event_live",
        "body_more_detail": None, "body_wait": None, "body_franchise_context": None,
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
        "visual": any(k in text for k in ("visual", "key visual")),
        "studio": bool(fx["studio_en"]),
        "premiered": "premiered" in text,
    }
    need = {
        "why_premiere_date": "date", "why_new_season": None, "why_cast": "cast",
        "why_trailer": "trailer", "why_adaptation": "manga",
        "why_adaptation_generic": "adaptation",
        "why_visual_staff": "visual", "why_date_set": "date",
        "why_first_look": None, "why_studio": "studio",
        "why_continuation": "premiered",
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
    title = None
    title_id = None
    shuffled_titles = templates["titles"][:]
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
    lead_tpl = rng.choice(templates["leads"])
    lead = _fill(lead_tpl["pattern"], ctx)
    # بدنه: ۲ جمله واجد شرایط (سوم فقط اگر کپشن کوتاه ماند)
    bodies = _eligible_bodies(fx, banks)
    specific = [b for b in bodies if b["id"] not in ("body_more_detail", "body_wait", "body_franchise_context")]
    generic = [b for b in bodies if b["id"] in ("body_more_detail", "body_wait", "body_franchise_context")]
    date_bodies = [b for b in specific if b["id"] in ("body_premiere", "body_source_date")]
    other = [b for b in specific if b["id"] not in ("body_premiere", "body_source_date")]
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
        "casting": ["why_cast", "why_visual_staff"],
        "date": ["why_premiere_date", "why_date_set"],
        "trailer": ["why_trailer"],
        "announcement": ["why_new_season", "why_continuation"],
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


# ------------------------------------------------------- ۸ دروازه کیفی

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


def check_gates(caption: str, title: str, fx: dict, why: str,
                recent_posts: list | None = None,
                template_usage: dict | None = None,
                template_ids: dict | None = None) -> dict:
    """هر ۸ دروازه را می‌سنجد؛ خروجی {gate_id: bool}."""
    gates: dict[str, bool] = {}
    gates["length"] = 600 <= len(caption) <= 850 and len(title) <= 70
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
    # «چرا مهم است؟» خاص: نام اثر + یک حقیقت مشخص (تاریخ/تریلر/کست/پخش/اقتباس)
    specific_markers = [
        fx.get("date_fa"), "تریلر", "صداپیشه", "پخش", "کی‌ویژوال",
        "اقتباس", "فصل", "استودیو",
    ]
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
        if score == 8 and 600 <= len(built["caption"]) <= 850:
            best = (built, gates, passed)
            break
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
