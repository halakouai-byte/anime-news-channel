"""انتشار صف به کانال تلگرام با sendPhoto.

- یک نویسنده برای انتشار: فقط Actions (این اسکریپت). Worker هرگز «منتشر شد» نمی‌نویسد.
- گارد state.json پیش از هر ارسال: state تازه از دیسک خوانده می‌شود؛ اگر هش
  قبلاً در posted_hashes بود، ارسال نمی‌شود (در برابر stale read و اجرای موازی).
- فاصله‌گذاری: حداقل ۱۵ دقیقه بین پست‌ها (هدف ۳۰ تا ۶۰)، breaking ‏۵ دقیقه،
  در ترمز اضطراری ۳۰ دقیقه. تصمیم قطعی کاربر (قفل‌شده ۲۱ نوامبر ۲۰۲۶):
  سکوت شبانه نیست؛ انتشار ۲۴/۷، شامل ۰۲:۰۰ تا ۰۷:۰۰ تهران.
- ترمز اضطراری (سقف روزانه نیست): فقط وقتی هر دو شرط برقرار باشند —
  بیش از ۲۵ پست از ۰۰:۰۰ تهران + صف هنوز بیش از ۱۰ آیتم واجد شرایط دارد.
  آن‌وقت فقط breaking یا اولویت ۷۵+ فوری می‌روند، بقیه با فاصله ۳۰ دقیقه‌ای
  منتظر می‌مانند و ادغام (حداکثر ۲ آیتم) اجباری می‌شود.
- تلگرام ۴۲۹ با retry_after: فقط یک بار retry؛ بعد توقف و ماندن خبر در صف.
- Secrets فقط با نام از محیط خوانده می‌شوند (TELEGRAM_BOT_TOKEN /
  TELEGRAM_CHAT_ID) و مقدارشان هرگز لاگ نمی‌شود.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests  # noqa: E402

from common import (  # noqa: E402
    append_archive,
    append_log,
    data_dir,
    env_secret,
    iso_utc,
    jalali_str,
    load_json,
    load_queue,
    load_state,
    log_error,
    log_info,
    log_warn,
    now_tehran,
    now_utc,
    parse_dt,
    redact,
    repo_root,
    save_queue,
    save_state,
    tehran_date_str,
)
from rewrite import rewrite_post  # noqa: E402 — موتور بازنویسی (سازنده دیگر)
from cover import build_cover  # noqa: E402 — کاور خودکار V3 (سازنده دیگر)

TELEGRAM_API = "https://api.telegram.org"

MIN_GAP_MINUTES = 15        # حداقل فاصله بین پست‌ها
BREAKING_GAP_MINUTES = 5    # breaking
BREAKER_GAP_MINUTES = 30    # در ترمز اضطراری
CIRCUIT_POSTS_THRESHOLD = 25
CIRCUIT_QUEUE_THRESHOLD = 10
CIRCUIT_OFF_QUEUE = 5
MAX_SOURCES_PER_CAPTION = 3


# ---------------------------------------------------------------------------
# ترمز اضطراری
# ---------------------------------------------------------------------------
def evaluate_circuit_breaker(state: dict, pending: int) -> bool:
    """فعال فقط وقتی هر دو شرط هم‌زمان برقرار باشند؛ خاموش‌شدن خودکار."""
    cb = state.setdefault("circuit_breaker", {})
    posts_today = state.get("counters", {}).get("posts_today", 0)
    if cb.get("active"):
        if pending < CIRCUIT_OFF_QUEUE:
            cb.update({"active": False, "activated_at": None,
                       "posts_today": posts_today, "queue_size": pending})
            log_info("circuit breaker OFF (queue below 5)")
            return False
        cb.update({"posts_today": posts_today, "queue_size": pending})
        return True
    if posts_today > CIRCUIT_POSTS_THRESHOLD and pending > CIRCUIT_QUEUE_THRESHOLD:
        cb.update({"active": True, "activated_at": iso_utc(),
                   "posts_today": posts_today, "queue_size": pending})
        log_warn(f"circuit breaker ON: posts_today={posts_today} queue={pending}")
        append_log(repo_root() / "logs" / "publish-log.md",
                   f"- {iso_utc()} UTC: CIRCUIT BREAKER ON — posts_today={posts_today} "
                   f"queue={pending}")
        return True
    cb.update({"posts_today": posts_today, "queue_size": pending})
    return False


def gap_minutes(state: dict, is_breaking: bool) -> float:
    """فاصله لازم از آخرین انتشار تا حالا (دقیقه)."""
    last = parse_dt(state.get("last_publish_utc"))
    if not last:
        return 0.0
    need = BREAKING_GAP_MINUTES if is_breaking else MIN_GAP_MINUTES
    if state.get("circuit_breaker", {}).get("active"):
        need = max(need, BREAKER_GAP_MINUTES)
    elapsed = (now_utc() - last).total_seconds() / 60
    return max(0.0, need - elapsed)


# ---------------------------------------------------------------------------
# تلگرام
# ---------------------------------------------------------------------------
class TelegramError(Exception):
    pass


def _api_url(method: str, token: str) -> str:
    return f"{TELEGRAM_API}/bot{token}/{method}"


def send_photo(token: str, chat_id: str, photo_path: str, caption: str) -> dict:
    """sendPhoto با retry ‏۴۲۹ فقط یک بار (با retry_after)."""
    url = _api_url("sendPhoto", token)
    for attempt in (1, 2):
        try:
            with open(photo_path, "rb") as fh:
                resp = requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": (Path(photo_path).name, fh, "image/jpeg")},
                    timeout=60,
                )
        except requests.RequestException as exc:
            raise TelegramError(f"network error: {exc}") from exc
        try:
            payload = resp.json()
        except ValueError:
            raise TelegramError(f"non-JSON response HTTP {resp.status_code}")
        if payload.get("ok"):
            return payload["result"]
        code = payload.get("error_code")
        desc = redact(payload.get("description", ""))
        if code == 429 and attempt == 1:
            wait = int((payload.get("parameters") or {}).get("retry_after", 30))
            log_warn(f"Telegram 429, retry_after={wait}s — one retry only")
            time.sleep(min(wait, 120))
            continue
        raise TelegramError(f"Telegram {code}: {desc}")
    raise TelegramError("Telegram 429 after one retry — stopping")


def edit_caption(token: str, chat_id: str, message_id: int, caption: str) -> dict:
    url = _api_url("editMessageCaption", token)
    resp = requests.post(url, data={
        "chat_id": chat_id, "message_id": message_id, "caption": caption,
    }, timeout=30)
    payload = resp.json()
    if not payload.get("ok"):
        raise TelegramError(
            f"editMessageCaption failed: {redact(payload.get('description', ''))}")
    return payload["result"]


# ---------------------------------------------------------------------------
# انتشار یک آیتم
# ---------------------------------------------------------------------------
def template_usage_counts(state: dict) -> dict:
    """template_usage_7d در state لیستی از زمان‌هاست؛ rewrite موتور شمارش
    ۷ روز اخیر می‌خواهد (عدد)."""
    cutoff = now_utc() - timedelta(days=7)
    out = {}
    for tid, stamps in (state.get("template_usage_7d") or {}).items():
        if isinstance(stamps, list):
            out[tid] = sum(1 for ts in stamps if (parse_dt(ts) or cutoff) >= cutoff)
        else:
            out[tid] = int(stamps or 0)
    return out


def publish_one(item: dict, state: dict, queue: dict, token: str, chat_id: str,
                workdir: Path, archive_path=None,
                state_path=None, queue_path=None) -> dict | None:
    """بازنویسی + کاور + sendPhoto + به‌روزرسانی state. None یعنی ارسال نشد."""
    # گارد state: تازه‌خوانی پیش از ارسال
    fresh = load_state(state_path)
    if item.get("hash") in fresh.get("posted_hashes", {}):
        log_warn(f"guard: already posted, skipping {item.get('hash', '')[:12]}")
        item["status"] = "POSTED"
        return None
    state.update(fresh)

    # Critic fix 2026-11-21 (review #1, item 10 — URGENT): publish-time
    # freshness re-check. The fetch step rejects items older than 48h,
    # but an item queued when young ages in the queue — without this
    # check the first publish wave would post days-old "news" (33 of 70
    # queue items were already 2+ days old on 2026-11-21). Anything
    # older than 48h at publish time is dropped (STALE, archived, never
    # posted) instead of being sent.
    pub_dt = parse_dt(item.get("pubDate"))
    if pub_dt is not None:
        from datetime import timedelta as _td
        if now_utc() - pub_dt > _td(hours=48):
            log_warn(f"stale at publish time (>48h), dropping {item.get('hash', '')[:12]}")
            item["status"] = "STALE"
            append_archive({
                "guid": item.get("guid"), "hash": item.get("hash"),
                "title": item.get("title"), "source": item.get("source"),
                "status": "stale", "reason": "older than 48h at publish time",
            }, path=archive_path)
            return None

    facts = {
        "title_en": item.get("title", ""),
        "summary_en": item.get("summary", ""),
        "source_name": item.get("source_name", item.get("source", "")),
        "source_url": item.get("link", ""),
        "pubDate": item.get("pubDate", ""),
        "category_hint": item.get("category"),
    }
    # seed قطعی از هش خبر (نه random بدون بذر)؛ اگر هش hex نبود، هش آن گرفته می‌شود.
    from common import sha256_hex as _sha
    seed = int(_sha(item.get("hash") or item.get("guid") or "")[:8], 16)
    recent = [a.get("caption", "") for a in _recent_archive_captions(30)
              if a.get("caption")]
    post = rewrite_post(facts, seed=seed, recent_posts=recent,
                        template_usage=template_usage_counts(state))
    # ۹ دروازه کیفی (ARCHITECTURE.md §۴.۳): همه باید پاس شوند. موتور بازنویسی
    # ۳۰ seed را امتحان می‌کند؛ اگر بهترین تلاش هم دروازه‌ای را رد کرد، خبر
    # به HOLD انسانی می‌رود، نه اینکه پست ناقص منتشر شود.
    all_gates = {"length", "no_placeholder", "english_limited",
                 "source_similarity", "recent_similarity",
                 "template_freshness", "why_specific", "numbers_dates",
                 "event_consistency"}
    missing = sorted(all_gates - set(post.get("gates_passed", [])))
    if missing:
        item["status"] = "HOLD"
        item["hold_reason"] = "gates_failed:" + ",".join(missing)
        log_warn(f"gates {len(post.get('gates_passed', []))}/9 — HOLD "
                 f"(missing: {','.join(missing)}): {item.get('title', '')[:50]}")
        append_archive({
            "guid": item.get("guid"), "hash": item.get("hash"),
            "title": item.get("title"), "source": item.get("source"),
            "status": "held", "reason": item["hold_reason"],
        }, path=archive_path)
        return None
    # «خبر روز»: مهم‌ترین خبر صف
    category = post.get("category") or item.get("category", "رویداد")
    cover_item = {
        "title_en": post.get("franchise_en") or item.get("title", ""),
        "category": category,
        "persian_subtitle": post.get("title", ""),
        "rating": None,
        "source": item.get("source", ""),
    }
    cover_path = workdir / f"cover-{item.get('hash', 'x')[:12]}.jpg"
    build_cover(cover_item, str(cover_path))
    if not cover_path.exists():
        log_error("cover build failed — safe exit, no post sent")
        return None

    caption = post["caption"]
    # ادغام اجباری در ترمز اضطراری (حداکثر ۲ آیتم، همان فرنچایز، < ۲ ساعت):
    merged = _try_merge(item, queue, caption)
    if merged:
        caption = merged

    result = send_photo(token, chat_id, str(cover_path), caption)
    message_id = result.get("message_id")
    posted_utc = now_utc()
    pub = parse_dt(item.get("pubDate"))
    latency = round((posted_utc - pub).total_seconds() / 60, 1) if pub else None

    # --- به‌روزرسانی state (مرجع نهایی)
    state["posted_hashes"][item["hash"]] = message_id
    state["posted_message_ids"].append(message_id)
    if item.get("story_key"):
        state.setdefault("story_keys", {})[item["story_key"]] = {
            "message_id": message_id, "posted_utc": iso_utc(posted_utc)}
    state.setdefault("recent_titles", []).append({
        "title_norm": item.get("title", "").lower(),
        "words": sorted(set(item.get("title", "").lower().split())),
        "posted_utc": iso_utc(posted_utc),
    })
    state["last_publish_utc"] = iso_utc(posted_utc)
    counters = state.setdefault("counters", {})
    counters["posts_total"] = counters.get("posts_total", 0) + 1
    counters["posts_today"] = counters.get("posts_today", 0) + 1
    for tid in post.get("template_ids", []):
        state.setdefault("template_usage_7d", {}).setdefault(tid, []).append(
            iso_utc(posted_utc))

    item["status"] = "POSTED"
    item["message_id"] = message_id
    item["posted_utc"] = iso_utc(posted_utc)
    item["caption"] = caption
    save_state(state, state_path)
    save_queue(queue, queue_path)
    append_archive({
        "guid": item.get("guid"), "hash": item.get("hash"),
        "title": item.get("title"), "source": item.get("source"),
        "status": "posted", "message_id": message_id,
        "category": category, "priority_score": item.get("priority_score"),
        "is_breaking": item.get("is_breaking"),
        "latency_minutes_feed_to_channel": latency,
        "caption": caption, "sources": [item.get("source")],
    }, path=archive_path)
    append_log(repo_root() / "logs" / "publish-log.md",
               f"- {iso_utc()} UTC ({jalali_str()}، تهران): "
               f"posted message_id={message_id} guid={item.get('guid')} "
               f"category={category} score={item.get('priority_score')} "
               f"breaking={item.get('is_breaking')} latency_min={latency}")
    log_info(f"posted message_id={message_id}: {item.get('title', '')[:60]}")
    return {"message_id": message_id, "item": item}


def _recent_archive_captions(n: int) -> list[dict]:
    path = data_dir() / "archive.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines()[-500:]:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("status") == "posted" and rec.get("caption"):
            out.append(rec)
    return out[-n:]


def _try_merge(item: dict, queue: dict, caption: str) -> str | None:
    """ادغام اجباری در ترمز اضطراری: یک آیتم کوچک دوم همان فرنچایز (< ۲ ساعت)
    به‌عنوان یک خط به کپشن اضافه می‌شود؛ آیتم دوم POSTED علامت می‌خورد."""
    fr = item.get("franchise_en")
    if not fr:
        return None
    created = parse_dt(item.get("created_utc")) or now_utc()
    for other in queue["items"]:
        if other is item or other.get("status") != "QUEUED":
            continue
        if other.get("franchise_en") != fr or other.get("is_breaking"):
            continue
        o_created = parse_dt(other.get("created_utc")) or now_utc()
        if abs((o_created - created).total_seconds()) > 2 * 3600:
            continue
        other["status"] = "POSTED"
        other["merged_into"] = item.get("hash")
        return (caption + f"\n\n📌 همچنین: {other.get('title', '')} — "
                f"{other.get('link', '')}")
    return None


def attach_second_sources(state: dict, queue: dict, token: str,
                          chat_id: str) -> int:
    """ضمیمه‌کردن منبع دوم با editMessageCaption (فقط اگر پست اول < ۲ ساعت پیش
    منتشر شده باشد و منبع دوم Tier 1 باشد؛ حداکثر ۳ منبع)."""
    done = 0
    for item in list(queue["items"]):
        if item.get("status") != "ATTACH":
            continue
        mid = item.get("attach_to")
        posted = next((a for a in _recent_archive_captions(100)
                       if a.get("message_id") == mid), None)
        if not posted:
            item["status"] = "POSTED"
            continue
        posted_dt = parse_dt(posted.get("archived_utc"))
        if posted_dt and (now_utc() - posted_dt).total_seconds() > 2 * 3600:
            item["status"] = "POSTED"  # بیش از ۲ ساعت؛ کپشن دست نمی‌خورد
            continue
        sources = list(posted.get("sources", []))
        if item.get("source") not in sources:
            sources.append(item["source"])
        sources = sources[:MAX_SOURCES_PER_CAPTION]
        caption = posted.get("caption", "")
        if "🔗 منابع:" in caption:
            caption = caption.split("🔗 منابع:")[0].rstrip()
        caption = caption + "\n\n🔗 منابع: " + " / ".join(sources)
        try:
            edit_caption(token, chat_id, mid, caption)
        except TelegramError as exc:
            log_error(f"attach failed for message {mid}: {exc}")
            continue
        item["status"] = "POSTED"
        done += 1
        log_info(f"attached source {item.get('source')} to message {mid}")
    return done


# ---------------------------------------------------------------------------
# حلقه اصلی
# ---------------------------------------------------------------------------
def is_pending(item: dict) -> bool:
    """آیتم قابل انتشار در این اجرا: QUEUED/APPROVED، یا HOLD با دلیل
    gates_failed (دوباره تست می‌شود — اصلاح یک گیت می‌تواند آن را آزاد کند).
    HOLD انسانی (low-confidence و...) دوباره تست نمی‌شود.
    Critic fix 2026-11-21 (run 44936475145): بدون این، Oshi No Ko ‏۸۵‏ و
    BanG Dream ‏۸۰‏ بعد از اصلاح why_specific هم HOLD ماندند — چون publish
    فقط QUEUED/APPROVED را می‌خواند و HOLD را هرگز دوباره ارزیابی نمی‌کرد."""
    if item.get("status") in ("QUEUED", "APPROVED"):
        return True
    return (item.get("status") == "HOLD"
            and str(item.get("hold_reason") or "").startswith("gates_failed"))


def run_publish(max_posts: int = 2, dry: bool = False,
                state_path=None, queue_path=None, archive_path=None,
                workdir: Path | None = None) -> dict:
    token = env_secret("TELEGRAM_BOT_TOKEN")
    chat_id = env_secret("TELEGRAM_CHAT_ID")
    if not dry and (not token or not chat_id):
        raise SystemExit("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set "
                         "(GitHub Secrets — values are never written here)")
    state = load_state(state_path)
    queue = load_queue(queue_path)
    workdir = workdir or (repo_root() / "out")
    workdir.mkdir(parents=True, exist_ok=True)

    pending = [i for i in queue["items"] if is_pending(i)]
    breaker = evaluate_circuit_breaker(state, len(pending))
    if not dry:
        attach_second_sources(state, queue, token, chat_id)

    # ترتیب صف: breaking اول، بعد امتیاز بالاتر، بعد تازه‌تر
    pending.sort(key=lambda i: i.get("pubDate") or "", reverse=True)
    pending.sort(key=lambda i: (
        not i.get("is_breaking", False),
        -(i.get("priority_score") or 0),
    ))
    # «خبر روز»: بالاترین اولویت صف (اگر breaking نباشد، همان اولی است)
    stats = {"posted": 0, "skipped_gap": 0, "skipped_breaker": 0,
             "attached": 0, "failed": 0, "breaker_active": breaker}
    for item in pending:
        if stats["posted"] >= max_posts:
            break
        if breaker and not item.get("is_breaking") \
                and (item.get("priority_score") or 0) < 75:
            stats["skipped_breaker"] += 1
            continue
        wait = gap_minutes(state, bool(item.get("is_breaking")))
        if wait > 0:
            if dry:
                stats["skipped_gap"] += 1
                log_info(f"dry: gap {wait:.1f} min — would wait, skipping "
                         f"{item.get('title', '')[:50]}")
                continue
            log_info(f"pacing: waiting {wait:.1f} min before next post")
            time.sleep(wait * 60)
        if dry:
            log_info(f"dry: would publish [{item.get('category')}] "
                     f"score={item.get('priority_score')} "
                     f"{item.get('title', '')[:60]}")
            stats["posted"] += 1
            continue
        try:
            result = publish_one(item, state, queue, token, chat_id, workdir,
                                 archive_path=archive_path,
                                 state_path=state_path, queue_path=queue_path)
        except TelegramError as exc:
            log_error(f"publish failed, item stays queued: {exc}")
            stats["failed"] += 1
            break  # ۴۲۹ یا خطای تلگرام: اجرا متوقف می‌شود، خبر در صف می‌ماند
        if result:
            stats["posted"] += 1
            state = load_state(state_path)  # تازه‌خوانی پس از هر ارسال
    save_state(state, state_path)
    save_queue(queue, queue_path)
    log_info(f"publish done: {stats}")
    return stats


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="انتشار صف به تلگرام")
    ap.add_argument("--max-posts", type=int, default=2,
                    help="حداکثر پست در این اجرا (پیش‌فرض ۲)")
    ap.add_argument("--dry", action="store_true",
                    help="فقط محاسبه؛ هیچ sendPhotoای فرستاده نمی‌شود")
    args = ap.parse_args(argv)
    run_publish(max_posts=args.max_posts, dry=args.dry)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
