"""ابزار مشترک publisher کانال «اخبار دنیای انیمه» (نسخه ۲).

- redaction توکن پیش از هر لاگ (لاگ ریپوی عمومی برای همه قابل دیدن است).
- خواندن/نوشتن امن state و JSON.
- زمان تهران + تاریخ شمسی (بدون وابستگی خارجی).

قوانین قفل‌شده (تصمیم قطعی کاربر ۲۱ نوامبر ۲۰۲۶):
- سکوت شبانه نیست؛ انتشار ۲۴/۷ است. هیچ پنجره سکوت شبانه‌ای در این فایل نیست.
- Secrets فقط با نام خوانده می‌شوند (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID) و مقدارشان
  هرگز لاگ یا در فایل نوشته نمی‌شود.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# زمان
# ---------------------------------------------------------------------------

TEHRAN = timezone(timedelta(hours=3, minutes=30))  # UTC+3:30، بدون DST
UTC = timezone.utc


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_tehran() -> datetime:
    return datetime.now(TEHRAN)


def tehran_date_str(dt: datetime | None = None) -> str:
    """تاریخ میلادی روز تهران، YYYY-MM-DD (برای شمارنده posts_today)."""
    return (dt or now_tehran()).strftime("%Y-%m-%d")


def parse_dt(value: str | None) -> datetime | None:
    """پارس ISO 8601 (با Z) به datetime آگاه‌از‌منطقه؛ None اگر نامعتبر."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def iso_utc(dt: datetime | None = None) -> str:
    return (dt or now_utc()).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# تاریخ شمسی (الگوریتم تقویم جلالی؛ بدون وابستگی خارجی)
# ---------------------------------------------------------------------------

_JALALI_EPOCH = (1405, 1, 1)          # ۱۴۰۵/۰۱/۰۱ = ۲۰۲۶-۰۳-۲۱ میلادی (نوروز)
_GREGORIAN_EPOCH = (2026, 3, 21)
# سال‌های کبیسه جلالی در چرخه ۳۳ ساله: سال‌هایی که باقی‌مانده بر ۳۳ در این مجموعه است
_JALALI_LEAP_REMAINDERS = {1, 5, 9, 13, 17, 22, 26, 30}
_JALALI_MONTH_DAYS = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
_JALALI_MONTH_NAMES = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]


def _is_jalali_leap(jy: int) -> bool:
    return (jy % 33) in _JALALI_LEAP_REMAINDERS


def _jalali_days_in_month(jy: int, jm: int) -> int:
    if jm == 12:
        return 30 if _is_jalali_leap(jy) else 29
    return _JALALI_MONTH_DAYS[jm - 1]


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل تاریخ میلادی به شمسی. مبنا: ۱۴۰۵/۰۱/۰۱ = ۲۰۲۶/۰۳/۲۱."""
    from datetime import date as _date

    base_g = _date(*_GREGORIAN_EPOCH)
    delta = (_date(gy, gm, gd) - base_g).days
    jy, jm, jd = _JALALI_EPOCH
    step = 1 if delta >= 0 else -1
    remaining = abs(delta)
    while remaining:
        dim = _jalali_days_in_month(jy, jm)
        left_in_month = (dim - jd + 1) if step > 0 else jd
        if remaining < left_in_month:
            jd += step * remaining
            remaining = 0
        else:
            remaining -= left_in_month
            if step > 0:
                jd = 1
                jm += 1
                if jm > 12:
                    jm = 1
                    jy += 1
            else:
                jm -= 1
                if jm < 1:
                    jm = 12
                    jy -= 1
                jd = _jalali_days_in_month(jy, jm)
    return jy, jm, jd


def jalali_str(dt: datetime | None = None) -> str:
    """تاریخ شمسی روز تهران، مثل «۳۰ آبان ۱۴۰۵»."""
    tehran = (dt or now_tehran()).astimezone(TEHRAN)
    jy, jm, jd = gregorian_to_jalali(tehran.year, tehran.month, tehran.day)
    return f"{jd} {_JALALI_MONTH_NAMES[jm - 1]} {jy}"


# ---------------------------------------------------------------------------
# Redaction توکن — پیش از هر لاگ
# ---------------------------------------------------------------------------

# الگوی توکن ربات تلگرام: <digits>:<35 کاراکتر>
_BOT_TOKEN_RE = re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35,}\b")
# الگوی کلی secret در URL (query مثل token=... / bot<token>/)
_SECRET_QUERY_RE = re.compile(r"(?i)(token|secret|password|api[_-]?key)=[^&\s\"']+")
_BOT_URL_RE = re.compile(r"(?i)(/bot)\d{8,10}:[A-Za-z0-9_-]{35,}")


def redact(text: str, extra_secrets: list[str] | None = None) -> str:
    """همه مقدارهای شبیه توکن/سکرت را با [REDACTED] جایگزین می‌کند.

    مقدارهای واقعی Secrets هرگز به این تابع پاس داده نمی‌شوند؛ تابع فقط
    الگوها را می‌پوشاند تا اگر جایی اتفاقی در متن بود، به لاگ نرود.
    """
    if not text:
        return text
    out = _BOT_TOKEN_RE.sub("[REDACTED]", text)
    out = _BOT_URL_RE.sub(r"\1[REDACTED]", out)
    out = _SECRET_QUERY_RE.sub(r"\1=[REDACTED]", out)
    for secret in extra_secrets or []:
        if secret and len(secret) >= 8 and secret in out:
            out = out.replace(secret, "[REDACTED]")
    return out


def env_secret(name: str) -> str:
    """خواندن Secret فقط با نام؛ مقدار خالی یعنی تنظیم نشده (هرگز لاگ نشود)."""
    return os.environ.get(name, "")


# ---------------------------------------------------------------------------
# لاگ (همیشه redactشده)
# ---------------------------------------------------------------------------

def log(level: str, message: str, extra_secrets: list[str] | None = None) -> None:
    line = f"[{iso_utc()} UTC] [{level}] {redact(message, extra_secrets)}"
    print(line, file=sys.stderr if level == "ERROR" else sys.stdout, flush=True)


def log_info(message: str) -> None:
    log("INFO", message)


def log_warn(message: str) -> None:
    log("WARN", message)


def log_error(message: str) -> None:
    log("ERROR", message)


def append_log(path: str | Path, line: str) -> None:
    """افزودن یک خط به فایل لاگ ریپو (redactشده)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(redact(line) + "\n")


# ---------------------------------------------------------------------------
# JSON / state
# ---------------------------------------------------------------------------

def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    return repo_root() / "data"


def load_json(path: str | Path, default):
    path = Path(path)
    if not path.exists():
        return default
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: str | Path, obj) -> None:
    """نوشتن اتمی JSON (فایل موقت + جایگزینی)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(path)


def default_state() -> dict:
    return {
        "version": 2,
        "seen_guids": [],          # هش SHA-256 guid/link نرمال‌شده، ۳۰ روز اخیر
        "seen_at": {},             # hash -> ISO UTC اولین دیده‌شدن
        "posted_hashes": {},       # hash -> message_id
        "posted_message_ids": [],  # message_idهای منتشرشده
        "story_keys": {},          # story_key -> {message_id, posted_utc}
        "recent_titles": [],       # [{title_norm, posted_utc}] برای dedupe لایه ۳ (۷ روز)
        "last_fetch_utc": None,
        "last_publish_utc": None,
        "queue_version": 1,
        "counters": {
            "posts_total": 0,
            "posts_today": 0,      # به وقت تهران
            "posts_today_date": tehran_date_str(),
            "rejected_total": 0,
            "duplicates_total": 0,
            "hold_total": 0,
        },
        "circuit_breaker": {
            "active": False,
            "activated_at": None,
            "posts_today": 0,
            "queue_size": 0,
        },
        "template_usage_7d": {},   # template_id -> [ISO UTC ...] برای gate ۶
    }


def load_state(path: str | Path | None = None) -> dict:
    path = Path(path) if path else data_dir() / "state.json"
    state = load_json(path, None)
    if not isinstance(state, dict) or "counters" not in state:
        state = default_state()
    # شمارنده روزانه را با روز تهران همگام کن
    today = tehran_date_str()
    counters = state.setdefault("counters", {})
    if counters.get("posts_today_date") != today:
        counters["posts_today"] = 0
        counters["posts_today_date"] = today
    state.setdefault("circuit_breaker", default_state()["circuit_breaker"])
    return state


def save_state(state: dict, path: str | Path | None = None) -> None:
    path = Path(path) if path else data_dir() / "state.json"
    # هرس حافظه seen: فقط ۳۰ روز اخیر
    cutoff = now_utc() - timedelta(days=30)
    seen_at = state.get("seen_at", {})
    fresh_hashes = {
        h for h, ts in seen_at.items()
        if (parse_dt(ts) or cutoff) >= cutoff
    }
    state["seen_guids"] = [h for h in state.get("seen_guids", []) if h in fresh_hashes]
    state["seen_at"] = {h: ts for h, ts in seen_at.items() if h in fresh_hashes}
    # recent_titles: فقط ۷ روز اخیر
    cutoff7 = now_utc() - timedelta(days=7)
    state["recent_titles"] = [
        t for t in state.get("recent_titles", [])
        if (parse_dt(t.get("posted_utc")) or cutoff7) >= cutoff7
    ]
    save_json(path, state)


def load_queue(path: str | Path | None = None) -> dict:
    path = Path(path) if path else data_dir() / "queue.json"
    queue = load_json(path, None)
    if not isinstance(queue, dict) or "items" not in queue:
        queue = {"version": 1, "items": []}
    return queue


def save_queue(queue: dict, path: str | Path | None = None) -> None:
    path = Path(path) if path else data_dir() / "queue.json"
    save_json(path, queue)


def append_archive(record: dict, path: str | Path | None = None, cap: int = 500) -> None:
    """افزودن یک رکورد به archive.jsonl با سقف ۵۰۰ خط (قدیمی‌ها حذف می‌شوند)."""
    path = Path(path) if path else data_dir() / "archive.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    record = dict(record)
    record.setdefault("archived_utc", iso_utc())
    lines.append(json.dumps(record, ensure_ascii=False))
    lines = lines[-cap:]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# نرمال‌سازی URL (dedupe لایه ۱ — filter-v2 §۳.۱)
# ---------------------------------------------------------------------------

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "fbclid", "gclid", "ref", "_location", "output",
}
_TRACKING_PREFIXES = ("utm_",)


def normalize_url(url: str) -> str:
    from urllib.parse import parse_qsl, urlparse, urlunparse

    url = (url or "").strip()
    if not url:
        return ""
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    # حذف پارامترهای ردیابی
    params = [
        (k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if k.lower() not in _TRACKING_PARAMS
        and not k.lower().startswith(_TRACKING_PREFIXES)
        and k.lower() != "ref"
    ]
    params.sort()
    query = "&".join(f"{k}={v}" for k, v in params)
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, host, path, "", query, ""))


# رویدادهای generic که نوع واقعی را نمی‌گویند — در تطابق story_key مثل
# wildcard عمل می‌کنند (هر رویدادی با آن‌ها یکی است).
_GENERIC_EVENTS = frozenset({"event", "other"})


def same_story_key(k1: str | None, k2: str | None) -> bool:
    """آیا دو story_key (`franchise|event|bucket`) یک داستان‌اند؟

    مقایسه دقیق رشته کافی نیست — سه پست BanG Dream در ران ۴۴۹۷۱۶۱۶۳۵۶
    (۲۲ نوامبر ۲۰۲۶) همین را ثابت کرد:
    - سطل ۴۸ ساعته ثابت در مرز می‌شکند: AnimeTV با pubDate ۰۰:۵۰ UTC روز
      بعد سطل ۱۰۳۸۹ گرفت، در حالی که ANN ‏(۱۵:۵۹ UTC روز قبل) سطل ۱۰۳۸۸
      داشت — فقط ~۹ ساعت فاصله، ولی کلید متفاوت. پس سطل ±۱ هم یکی است.
    - رویداد generic: ‏classify برای MAL ‏«event»‏ برگرداند (کلمه «event» در
      خلاصه)، در حالی که بقیه «announcement» بودند. «event»/«other» نوع
      واقعی نیستند، پس با هر رویدادی یکی شمرده می‌شوند.
    """
    if not k1 or not k2 or k1 == k2:
        return bool(k1 and k1 == k2)
    try:
        fr1, ev1, b1 = k1.rsplit("|", 2)
        fr2, ev2, b2 = k2.rsplit("|", 2)
        bucket1, bucket2 = int(b1), int(b2)
    except (ValueError, AttributeError):
        return False
    if fr1 != fr2:
        return False
    if abs(bucket1 - bucket2) > 1:
        return False
    return ev1 == ev2 or ev1 in _GENERIC_EVENTS or ev2 in _GENERIC_EVENTS
