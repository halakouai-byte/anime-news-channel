"""خواندن RSS، فیلتر v2، dedupe سه‌لایه، امتیاز اولویت، صف انتشار.

منابع: ۸ فید تاییدشده با fetch زنده (sources-v2.md، ۲۰ نوامبر ۲۰۲۶) — هیچ آدرس حدسی.
قانون طلایی v2 (filter-v2 §۰): هر خبر تازه واقعی از منبع معتمد همان موقع
منتشر می‌شود، مگر در فهرست حذف باشد، تکراری باشد، یا به HOLD انسانی برود.
آستانه ۶۰ و سقف روزانه حذف شده‌اند؛ امتیاز ۰–۱۰۰ فقط ترتیب صف است.

ترتیب اجرا در هر fetch: تازگی → فیلتر حذف (پیش از dedupe) → dedupe لایه ۱/۲/۳
→ دسته‌بندی → امتیاز اولویت → صف.

تصمیم قطعی کاربر (قفل‌شده ۲۱ نوامبر ۲۰۲۶): سکوت شبانه نیست؛ انتشار ۲۴/۷.
هیچ پنجره سکوت شبانه‌ای در این فایل نیست.
"""

from __future__ import annotations

import argparse
import difflib
import html
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import feedparser  # noqa: E402
import requests  # noqa: E402

from classify import classify_with_corrections, detect_event  # noqa: E402
from common import (  # noqa: E402
    append_archive,
    append_log,
    data_dir,
    iso_utc,
    load_json,
    load_queue,
    load_state,
    log_error,
    log_info,
    log_warn,
    normalize_url,
    now_tehran,
    now_utc,
    parse_dt,
    redact,
    repo_root,
    same_story_key,
    save_json,
    save_queue,
    save_state,
    sha256_hex,
    tehran_date_str,
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# منابع — فقط آدرس‌هایی که واقعاً fetch شدند (sources-v2.md)
# ---------------------------------------------------------------------------
SOURCES = [
    {"name": "Anime News Network", "short": "ANN", "tier": 1, "score": 25,
     "url": "https://www.animenewsnetwork.com/news/rss.xml"},
    {"name": "MyAnimeList News", "short": "MAL", "tier": 1, "score": 20,
     "url": "https://myanimelist.net/rss/news.xml"},
    {"name": "Anime Corner", "short": "AnimeCorner", "tier": 1, "score": 20,
     "url": "https://animecorner.me/feed/"},
    {"name": "AnimeTV", "short": "AnimeTV", "tier": 1, "score": 20,
     "url": "https://animetv-jp.net/feed/"},
    {"name": "The Fandom Post", "short": "FandomPost", "tier": 1, "score": 20,
     "url": "https://www.fandompost.com/feed/"},
    {"name": "Siliconera", "short": "Siliconera", "tier": 1, "score": 20,
     "url": "https://www.siliconera.com/feed/", "anime_only": True},
    {"name": "Honey's Anime", "short": "HoneysAnime", "tier": 2, "score": 15,
     "url": "https://honeysanime.com/feed/"},
    {"name": "Anime Herald", "short": "AnimeHerald", "tier": 2, "score": 15,
     "url": "https://animeherald.com/feed/"},
]

ANIME_KEYWORDS = [
    "anime", "manga", "otaku", "studio", "voice actor", "seiyuu",
    "shonen", "shojo", "isekai", "ghibli", "pokemon", "naruto",
]

FRESHNESS_HOURS = 48
BREAKING_FRESHNESS_HOURS = 72


# ---------------------------------------------------------------------------
# ابزارهای کوچک
# ---------------------------------------------------------------------------
def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_pubdate(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, key, None)
        if parsed:
            try:
                return datetime(*parsed[:6], tzinfo=now_utc().tzinfo)
            except (TypeError, ValueError):
                pass
    return None


def load_franchises() -> list[dict]:
    """franchises.json متعلق به سازنده موتور بازنویسی است؛ فقط خوانده می‌شود."""
    data = load_json(data_dir() / "franchises.json", {})
    if isinstance(data, dict):
        return data.get("franchises", [])
    return []


def extract_franchise(title: str, summary: str, franchises: list[dict]) -> dict | None:
    """فرنچایزِ موضوع خبر: اول در تیتر (substring)، بعد در خلاصه فقط با
    word-boundary. دلیل: خلاصه‌ها پر از ارجاع به آثار دیگرند («از نویسنده
    Re:Zero») و match سست در خلاصه، breaking کاذب می‌سازد (dry-run ۲۱ نوامبر:
    «Pen to Wappa...» به‌خاطر Re:Zero در خلاصه breaking شد)."""
    title_l = (title or "").lower()
    for fr in franchises:
        name = (fr.get("name_en") or "").lower()
        if name and name in title_l:
            return fr
    summary_l = (summary or "").lower()
    for fr in franchises:
        name = (fr.get("name_en") or "").lower()
        if name and re.search(r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])",
                              summary_l):
            return fr
    return None


def normalize_franchise(text: str) -> str:
    stop = set(load_json(data_dir() / "stopwords.json", {}).get("stopwords", []))
    text = (text or "").lower()
    text = re.sub(r"[^a-z0-9 ]", " ", text)
    text = re.sub(r"\b(season|part|cour)\s+\d+\b", " ", text)
    text = re.sub(r"\b(s|season)\s*\d+\b", " ", text)
    words = [w for w in text.split() if w not in stop and len(w) > 1]
    return " ".join(sorted(set(words)))


def story_key(franchise_norm: str, event_type: str, pub: datetime | None) -> str | None:
    if not franchise_norm:
        return None
    bucket = 0
    if pub is not None:
        bucket = int(pub.timestamp() // (48 * 3600))
    return f"{franchise_norm}|{event_type}|{bucket}"


def title_words(title: str, franchise_norm: str) -> set[str]:
    stop = set(load_json(data_dir() / "stopwords.json", {}).get("stopwords", []))
    text = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    words = {w for w in text.split() if w not in stop and len(w) > 1}
    for w in franchise_norm.split():
        words.discard(w)
    return words


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# ---------------------------------------------------------------------------
# فیلتر حذف — ۱۷ دسته (filter-v2 §۲)
# ---------------------------------------------------------------------------
class FilterResult:
    def __init__(self, decision: str, code: str, detail: str = ""):
        self.decision = decision  # ok | reject | hold | digest
        self.code = code
        self.detail = detail


def _matches(text: str, patterns: list[str]) -> str | None:
    for pat in patterns:
        if re.search(pat, text, flags=re.IGNORECASE):
            return pat
    return None


def check_blocklist(title: str, summary: str, source: dict,
                    franchise: dict | None, multi_source: bool) -> FilterResult:
    text = f"{title} {summary}"
    block = load_json(data_dir() / "blocklist.json", {})
    rules = block.get("rules", [])

    # R6 حساس — اول از همه: هرگز خودکار منتشر نمی‌شود (حتی breaking).
    # فقط عبارت خبری در تیتر (word-boundary) یا عبارت چندکلمه‌ای در خلاصه؛
    # کلمه تکی در خلاصه مثبت کاذب می‌سازد (عنوان اثر / سیناپس داستان).
    title_pats = block.get("sensitive_title_patterns") or []
    summary_phrases = block.get("sensitive_summary_phrases") or []
    for pat in title_pats:
        if re.search(r"(?<![a-z])" + re.escape(pat.lower()) + r"(?![a-z])",
                     (title or "").lower()):
            return FilterResult("hold", "R6-hold", f"sensitive in title: {pat}")
    for phrase in summary_phrases:
        if phrase.lower() in (summary or "").lower():
            return FilterResult("hold", "R6-hold",
                                f"sensitive phrase in summary: {phrase}")

    for rule in rules:
        code = rule.get("code", "")
        if code in ("R6", "R9"):
            continue  # R6 بالا چک شد؛ R9 را dedupe صادر می‌کند
        pat = _matches(text, rule.get("patterns", []))
        if not pat:
            continue
        action = rule.get("action", "reject")
        # استثناهای مستند:
        if code == "R3":
            fresh = ("bonus episode" in text.lower() or "interview" in text.lower()
                     or "director's cut" in text.lower() or "director’s cut" in text.lower())
            if fresh:
                continue  # بلوری + محتوای تازه = خبر
        if code == "R5":
            if re.search(r"\b(film|season|trailer|announced|announces)\b", text, re.IGNORECASE):
                continue  # کالا همراه با خبر اصلی
        if code == "R7":
            if franchise and multi_source:
                return FilterResult("hold", "R7-hold",
                                    "rumor about a big franchise in 2+ sources")
            return FilterResult("reject", "R7-rumor", f"pattern: {pat}")
        if code == "R17":
            if franchise:
                return FilterResult("digest", "R17-digest",
                                    "catalog item for a big franchise")
            first_global = re.search(r"worldwide premiere|global premiere|first (ever )?stream",
                                     text, re.IGNORECASE)
            if first_global:
                continue  # اولین پخش جهانی = خبر
        if action == "digest":
            return FilterResult("digest", f"{code}-digest", f"pattern: {pat}")
        return FilterResult("reject", f"{code}-{action}", f"pattern: {pat}")

    # R15 برای Siliconera: فقط آیتم‌های انیمه‌محور
    if source.get("anime_only"):
        hay = text.lower()
        if not any(k in hay for k in ANIME_KEYWORDS):
            return FilterResult("reject", "R15-non-anime", "Siliconera non-anime item")
    return FilterResult("ok", "", "")


# ---------------------------------------------------------------------------
# امتیاز اولویت ۰–۱۰۰ — فقط ترتیب صف (filter-v2 §۶)
# ---------------------------------------------------------------------------
def priority_score(source: dict, franchise: dict | None, event_type: str,
                   age_hours: float, multi_source: bool, is_breaking: bool) -> int:
    score = source.get("score", 15)
    if franchise:
        score += 20
    event_points = {
        "announcement": 20, "date": 20, "trailer": 15, "box_office": 15,
        "adaptation": 10, "event": 10, "casting": 10, "award": 10, "other": 5,
    }
    score += event_points.get(event_type, 5)
    if age_hours < 1:
        score += 15
    elif age_hours < 6:
        score += 10
    elif age_hours < 24:
        score += 5
    if multi_source:
        score += 10
    if is_breaking:
        score += 10
    return min(100, score)


def is_breaking_news(franchise: dict | None, event_type: str,
                     title: str, summary: str) -> bool:
    text = f"{title} {summary}".lower()
    if franchise and franchise.get("breaking_eligible") and event_type in (
            "announcement", "trailer", "date"):
        return True
    if franchise and event_type == "box_office" and re.search(
            r"record|highest-grossing|surpasses|all-time", text):
        return True
    if re.search(r"studio (closes|shuts down|merges)|merger of .* studio", text):
        return True
    return False


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------
def fetch_source(session: requests.Session, source: dict) -> list[dict]:
    started = time.perf_counter()
    try:
        resp = session.get(source["url"], timeout=25)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log_error(f"fetch failed: {source['short']} — {exc}")
        return []
    feed = feedparser.parse(resp.content)
    items = []
    for entry in feed.entries:
        pub = parse_pubdate(entry)
        items.append({
            "title": strip_html(getattr(entry, "title", "")),
            "link": getattr(entry, "link", "") or "",
            "guid": getattr(entry, "id", "") or getattr(entry, "link", ""),
            "summary": strip_html(getattr(entry, "summary", "")
                                  or getattr(entry, "description", ""))[:2000],
            "pubDate": pub,
            "source": source,
        })
    log_info(f"fetched {source['short']}: {len(items)} items "
             f"in {time.perf_counter() - started:.1f}s")
    return items


def expire_queue(queue: dict, state: dict, archive_path=None) -> dict:
    """HOLD بیش از ۷۲ ساعت → REJECTED؛ QUEUED بیش از ۴۸ ساعت → EXPIRED."""
    now = now_utc()
    stats = {"expired": 0, "hold_rejected": 0}
    for item in queue["items"]:
        created = parse_dt(item.get("created_utc")) or now
        age_h = (now - created).total_seconds() / 3600
        if item.get("status") == "HOLD" and age_h > 72:
            item["status"] = "REJECTED"
            stats["hold_rejected"] += 1
            append_archive({"guid": item.get("guid"), "hash": item.get("hash"),
                            "title": item.get("title"), "status": "rejected",
                            "reason": "R6-hold-expired-72h"}, path=archive_path)
        elif item.get("status") == "QUEUED" and age_h > 48:
            item["status"] = "EXPIRED"
            stats["expired"] += 1
            append_archive({"guid": item.get("guid"), "hash": item.get("hash"),
                            "title": item.get("title"), "status": "expired",
                            "reason": "expired-in-queue"}, path=archive_path)
    return stats


def process_items(items: list[dict], state: dict, queue: dict,
                  franchises: list[dict], archive_path=None) -> dict:
    stats = {"fetched": len(items), "queued": 0, "held": 0, "rejected": 0,
             "duplicates": 0, "digest": 0, "stale": 0, "breaking": 0,
             "reasons": {}}
    now = now_utc()

    # گروه‌بندی story_key برای تشخیص چندمنبعی (R7 + امتیاز)
    def _pre_key(it: dict) -> str | None:
        fr = extract_franchise(it["title"], it["summary"], franchises)
        fn = normalize_franchise((fr or {}).get("name_en", "")) if fr else ""
        return story_key(fn, detect_event(it["title"], it["summary"]), it["pubDate"])

    key_sources: dict[str, set[str]] = {}
    for it in items:
        k = _pre_key(it)
        if k:
            key_sources.setdefault(k, set()).add(it["source"]["short"])

    seen_hashes = set(state.get("seen_guids", []))
    story_keys = state.get("story_keys", {})
    recent_titles = state.get("recent_titles", [])
    queued_hashes = {i.get("hash") for i in queue["items"]
                     if i.get("status") in ("QUEUED", "HOLD", "APPROVED")}
    # Critic fix 2026-11-22 (run 44971616356 — سه پست BanG Dream): لایه ۲
    # فقط در برابر پست‌شده‌ها (state) + همین اجرا می‌سنجید؛ کلید آیتم‌های
    # QUEUED/HOLD از اجراهای قبل نه در state بود نه در این اجرا — پس ANN و
    # AnimeCorner با همان story_key هر دو در صف ماندند. این مجموعه همان
    # کلیدها را از صف فعلی هم می‌خواند.
    queued_story_keys = {i.get("story_key") for i in queue["items"]
                         if i.get("status") in ("QUEUED", "HOLD", "APPROVED")
                         and i.get("story_key")}
    # ردیابی درون‌اجرا: dedupe فقط در برابر پست‌های قبلی کافی نیست — دو منبع
    # در یک fetch هم‌زمان می‌رسند و نسخه دوم باید با نسخه اولِ همین اجرا
    # سنجیده شود (dry-run ۲۱ نوامبر: بدون این ردیابی، ۰ تکراری گرفته شد
    # با اینکه ANN/MAL/FandomPost همان داستان را پوشش داده بودند).
    run_story_keys: set[str] = set()
    run_titles: list[set[str]] = []

    for it in items:
        title, summary = it["title"], it["summary"]
        source = it["source"]
        norm_link = normalize_url(it["link"] or it["guid"])
        item_hash = sha256_hex(it["guid"] or norm_link)
        pub = it["pubDate"]
        age_h = (now - pub).total_seconds() / 3600 if pub else 0.0

        franchise = extract_franchise(title, summary, franchises)
        fr_norm = normalize_franchise(franchise["name_en"]) if franchise else ""
        event_type = detect_event(title, summary)
        skey = story_key(fr_norm, event_type, pub)
        multi = bool(skey and len(key_sources.get(skey, set())) >= 2)

        # --- تازگی (شرط ۳): breaking تا ۷۲ ساعت، بقیه ۴۸ ساعت
        breaking_early = is_breaking_news(franchise, event_type, title, summary)
        limit = BREAKING_FRESHNESS_HOURS if breaking_early else FRESHNESS_HOURS
        if pub and age_h > limit:
            stats["stale"] += 1
            stats["reasons"]["stale-48h"] = stats["reasons"].get("stale-48h", 0) + 1
            append_archive({"guid": it["guid"], "hash": item_hash, "title": title,
                            "source": source["short"], "status": "rejected",
                            "reason": "stale-48h"}, path=archive_path)
            continue

        # --- فیلتر حذف (پیش از dedupe)
        filt = check_blocklist(title, summary, source, franchise, multi)
        if filt.decision == "reject":
            stats["rejected"] += 1
            stats["reasons"][filt.code] = stats["reasons"].get(filt.code, 0) + 1
            state["counters"]["rejected_total"] += 1
            append_archive({"guid": it["guid"], "hash": item_hash, "title": title,
                            "source": source["short"], "status": "rejected",
                            "reason": filt.code, "detail": filt.detail}, path=archive_path)
            continue
        if filt.decision == "digest":
            stats["digest"] += 1
            stats["reasons"][filt.code] = stats["reasons"].get(filt.code, 0) + 1
            append_archive({"guid": it["guid"], "hash": item_hash, "title": title,
                            "source": source["short"], "status": "digest-candidate",
                            "reason": filt.code, "detail": filt.detail}, path=archive_path)
            continue

        # --- dedupe لایه ۱: guid/link دقیق، ۳۰ روز
        if item_hash in seen_hashes or item_hash in queued_hashes:
            stats["duplicates"] += 1
            stats["reasons"]["R9-duplicate-L1"] = stats["reasons"].get("R9-duplicate-L1", 0) + 1
            state["counters"]["duplicates_total"] += 1
            append_archive({"guid": it["guid"], "hash": item_hash, "title": title,
                            "source": source["short"], "status": "duplicate",
                            "reason": "R9-duplicate", "layer": 1}, path=archive_path)
            continue
        # --- dedupe لایه ۲: story_key، ۴۸ ساعت (state + همین اجرا + صف)
        # Critic fix 2026-11-22 (run 44971616356 — سه پست BanG Dream):
        # مقایسه دقیق رشته کافی نبود — سطل ۴۸ ساعته ثابت در مرز می‌شکند
        # (AnimeTV سطل ۱۰۳۸۹ گرفت، ANN سطل ۱۰۳۸۸) و رویداد generic «event»
        # با «announcement» یکی نبود (MAL). same_story_key هر دو را
        # می‌پوشاند (سطل ±۱ + «event»/«other» به‌عنوان wildcard) و
        # queued_story_keys آیتم‌های QUEUED/HOLD اجراهای قبل را هم می‌گیرد.
        dup_key = None
        if skey:
            for cand in list(story_keys) + list(run_story_keys) + list(queued_story_keys):
                if same_story_key(skey, cand):
                    dup_key = cand
                    break
        if dup_key is not None:
            posted = story_keys.get(dup_key, {})
            stats["duplicates"] += 1
            stats["reasons"]["R9-duplicate-L2"] = stats["reasons"].get("R9-duplicate-L2", 0) + 1
            state["counters"]["duplicates_total"] += 1
            mid = posted.get("message_id")
            posted_dt = parse_dt(posted.get("posted_utc"))
            attachable = bool(
                mid and posted_dt and (now - posted_dt).total_seconds() < 2 * 3600
                and source["tier"] == 1)
            if attachable:
                queue["items"].append({
                    "guid": it["guid"], "hash": item_hash, "story_key": skey,
                    "title": title, "link": norm_link, "source": source["short"],
                    "status": "ATTACH", "attach_to": mid,
                    "created_utc": iso_utc(), "pubDate": pub.isoformat() if pub else None,
                })
                log_info(f"duplicate will attach to message {mid}: {title[:60]}")
            append_archive({"guid": it["guid"], "hash": item_hash, "title": title,
                            "source": source["short"], "status": "duplicate",
                            "reason": "R9-duplicate", "layer": 2,
                            "duplicate-of": mid}, path=archive_path)
            continue
        # --- dedupe لایه ۳: شباهت تیتر ≥ ۰٫۸۵، ۷ روز
        words = title_words(title, fr_norm)
        dup3 = False
        past_word_sets = [set(p.get("words", [])) for p in recent_titles] + run_titles
        for past_words in past_word_sets:
            if not words or not past_words:
                continue
            sim_j = jaccard(words, past_words)
            sim_s = difflib.SequenceMatcher(
                None, " ".join(sorted(words)), " ".join(sorted(past_words))).ratio()
            if sim_j >= 0.85 or sim_s >= 0.85:
                dup3 = True
                break
        if dup3:
            stats["duplicates"] += 1
            stats["reasons"]["R9-duplicate-L3"] = stats["reasons"].get("R9-duplicate-L3", 0) + 1
            state["counters"]["duplicates_total"] += 1
            append_archive({"guid": it["guid"], "hash": item_hash, "title": title,
                            "source": source["short"], "status": "duplicate",
                            "reason": "R9-duplicate", "layer": 3}, path=archive_path)
            continue

        # --- دسته‌بندی (آستانه اطمینان ۳ → HOLD)
        cls = classify_with_corrections(item_hash, title, summary)
        status = "QUEUED"
        if filt.decision == "hold":
            status = "HOLD"
            stats["held"] += 1
            state["counters"]["hold_total"] += 1
        elif not cls["confident"]:
            status = "HOLD"
            stats["held"] += 1
            state["counters"]["hold_total"] += 1

        score = priority_score(source, franchise, event_type, age_h, multi,
                               breaking_early)
        if breaking_early:
            stats["breaking"] += 1

        queue["items"].append({
            "guid": it["guid"], "hash": item_hash, "story_key": skey,
            "title": title, "link": norm_link, "summary": summary[:500],
            "source": source["short"], "source_name": source["name"],
            "tier": source["tier"],
            "pubDate": pub.isoformat() if pub else None,
            "category": cls["category"], "category_score": cls["score"],
            "category_source": cls["source"],
            "event_type": event_type,
            "franchise_en": (franchise or {}).get("name_en"),
            "priority_score": score,
            "is_breaking": breaking_early,
            "status": status,
            "hold_reason": (filt.code if filt.decision == "hold"
                            else ("low-confidence" if not cls["confident"] else "")),
            "created_utc": iso_utc(),
        })
        seen_hashes.add(item_hash)
        state.setdefault("seen_at", {})[item_hash] = iso_utc()
        if skey:
            run_story_keys.add(skey)
        run_titles.append(words)
        if status == "QUEUED":
            stats["queued"] += 1
        state["seen_guids"] = sorted(seen_hashes)
    return stats


def run_fetch(source_names: list[str] | None = None,
              state_path=None, queue_path=None, archive_path=None,
              log_path=None, write: bool = True) -> dict:
    state = load_state(state_path)
    queue = load_queue(queue_path)
    expire_queue(queue, state, archive_path=archive_path)
    franchises = load_franchises()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    sources = [s for s in SOURCES if not source_names or s["short"] in source_names]
    all_items: list[dict] = []
    fetch_started = time.perf_counter()
    for source in sources:
        all_items.extend(fetch_source(session, source))
    fetch_secs = time.perf_counter() - fetch_started

    t0 = time.perf_counter()
    stats = process_items(all_items, state, queue, franchises,
                          archive_path=archive_path)
    process_secs = time.perf_counter() - t0
    stats["fetch_seconds"] = round(fetch_secs, 1)
    stats["process_seconds"] = round(process_secs, 1)
    state["last_fetch_utc"] = iso_utc()

    if write:
        save_state(state, state_path)
        save_queue(queue, queue_path)
        append_log(log_path or (repo_root() / "logs" / "fetch-log.md"),
                   f"- {iso_utc()} UTC ({tehran_date_str()} تهران): "
                   f"fetched={stats['fetched']} queued={stats['queued']} "
                   f"held={stats['held']} rejected={stats['rejected']} "
                   f"duplicates={stats['duplicates']} digest={stats['digest']} "
                   f"stale={stats['stale']} breaking={stats['breaking']} "
                   f"reasons={stats['reasons']}")
    log_info(f"fetch done: {stats}")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="خواندن RSS + فیلتر v2 + صف انتشار")
    ap.add_argument("--source", action="append", dest="sources",
                    help="فقط این منبع (short name)؛ قابل تکرار")
    ap.add_argument("--no-write", action="store_true",
                    help="فقط محاسبه؛ state/queue نوشته نمی‌شوند")
    args = ap.parse_args(argv)
    run_fetch(source_names=args.sources, write=not args.no_write)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
