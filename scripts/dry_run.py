"""اجرای خشک کامل pipeline (فاز ۲) — بدون هیچ sendPhotoای.

fetch واقعی از RSS → فیلتر v2 + dedupe → دسته‌بندی → بازنویسی فارسی
(rewrite.py واقعی) → کاور V3 واقعی (cover.py) → خروجی محلی.

هیچ پستی به کانال عمومی نمی‌رود؛ هیچ state/queue/archive واقعی دست نمی‌خورد
(کپی‌های موقت در پوشه خروجی استفاده می‌شوند).

خروجی: <out>/report.md + <out>/captions.json + <out>/covers/*.jpg
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import data_dir, iso_utc, load_json, log_info, repo_root  # noqa: E402
from fetch import run_fetch  # noqa: E402
from rewrite import rewrite_post  # noqa: E402
from cover import build_cover  # noqa: E402
from publish import template_usage_counts  # noqa: E402


def _stage(timings: dict, name: str, started: float) -> None:
    timings[name] = round(time.perf_counter() - started, 2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="اجرای خشک کامل — بدون ارسال تلگرام")
    ap.add_argument("--out", default=None,
                    help="پوشه خروجی (پیش‌فرض: dry-run-output در ریشه ریپو)")
    ap.add_argument("--max-covers", type=int, default=5,
                    help="حداکثر خبر واجد شرایط که کاور می‌گیرد (پیش‌فرض ۵)")
    ap.add_argument("--source", action="append", dest="sources",
                    help="فقط این منبع (short name)؛ قابل تکرار")
    args = ap.parse_args(argv)

    outdir = Path(args.out) if args.out else repo_root() / "dry-run-output"
    outdir.mkdir(parents=True, exist_ok=True)
    covers_dir = outdir / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    tmp = outdir / "tmp-state"
    tmp.mkdir(parents=True, exist_ok=True)
    state_path = tmp / "state.json"
    queue_path = tmp / "queue.json"
    archive_path = tmp / "archive.jsonl"
    for src, dst in ((data_dir() / "state.json", state_path),
                     (data_dir() / "queue.json", queue_path)):
        dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    archive_path.write_text("", encoding="utf-8")

    timings: dict[str, float] = {}
    started_all = time.perf_counter()
    report: dict = {"started_utc": iso_utc(), "stages_seconds": timings,
                    "items": [], "rejected": []}

    # --- مرحله ۱: fetch + فیلتر + dedupe + صف (روی کپی‌های موقت)
    t0 = time.perf_counter()
    stats = run_fetch(source_names=args.sources, state_path=state_path,
                      queue_path=queue_path, archive_path=archive_path,
                      log_path=tmp / "fetch-log.md", write=True)
    _stage(timings, "fetch_filter_dedupe", t0)
    report["fetch_stats"] = stats

    queue = load_json(queue_path, {"items": []})
    eligible = [i for i in queue["items"] if i.get("status") == "QUEUED"]
    held = [i for i in queue["items"] if i.get("status") == "HOLD"]
    report["eligible_count"] = len(eligible)
    report["held_count"] = len(held)

    # دلیل‌های رد از آرشیو موقت
    reasons: dict[str, int] = {}
    for line in archive_path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("status") in ("rejected", "duplicate", "digest-candidate"):
            reasons[rec.get("reason", "?")] = reasons.get(rec.get("reason", "?"), 0) + 1
            report["rejected"].append({
                "title": rec.get("title"), "source": rec.get("source"),
                "reason": rec.get("reason"), "status": rec.get("status")})
    report["reject_reasons"] = reasons

    # --- مرحله ۲ و ۳: بازنویسی + کاور (فقط N خبر اول صف به ترتیب اولویت)
    eligible.sort(key=lambda i: (not i.get("is_breaking", False),
                                 -(i.get("priority_score") or 0)))
    rewrite_secs = 0.0
    cover_secs = 0.0
    gate_counts: dict[str, int] = {}
    for item in eligible[:args.max_covers]:
        facts = {
            "title_en": item.get("title", ""),
            "summary_en": item.get("summary", ""),
            "source_name": item.get("source_name", item.get("source", "")),
            "source_url": item.get("link", ""),
            "pubDate": item.get("pubDate", ""),
            "category_hint": item.get("category"),
        }
        seed = int(item["hash"][:8], 16)
        t0 = time.perf_counter()
        state_now = load_json(state_path, {})
        post = rewrite_post(facts, seed=seed, recent_posts=[],
                            template_usage=template_usage_counts(state_now))
        rewrite_secs += time.perf_counter() - t0
        for g in post.get("gates_passed", []):
            gate_counts[g] = gate_counts.get(g, 0) + 1

        t0 = time.perf_counter()
        cover_path = covers_dir / f"cover-{item['hash'][:12]}.jpg"
        build_cover({
            "title_en": post.get("franchise_en") or item.get("title", ""),
            "category": post.get("category") or item.get("category", "رویداد"),
            "persian_subtitle": post.get("title", ""),
            "rating": None,
            "source": item.get("source", ""),
        }, str(cover_path))
        cover_secs += time.perf_counter() - t0
        cover_mode = getattr(build_cover, "last_build", {}).get("mode")

        all_gates = {"length", "no_placeholder", "english_limited",
                     "source_similarity", "recent_similarity",
                     "template_freshness", "why_specific", "numbers_dates",
                     "event_consistency"}
        missing = sorted(all_gates - set(post.get("gates_passed", [])))
        report["items"].append({
            "title_en": item.get("title"),
            "source": item.get("source"),
            "category": post.get("category"),
            "priority_score": item.get("priority_score"),
            "is_breaking": item.get("is_breaking"),
            "gates_passed": post.get("gates_passed"),
            "gates_count": len(post.get("gates_passed", [])),
            # publish واقعی خبر با دروازه ناقص را HOLD می‌کند، نه منتشر؛
            # dry run برای تست کاور همچنان کاور می‌سازد ولی اینجا علامت می‌خورد.
            "would_hold": bool(missing),
            "missing_gates": missing,
            "caption_chars": len(post.get("caption", "")),
            "title_chars": len(post.get("title", "")),
            "cover": str(cover_path),
            "cover_mode": cover_mode,
            "caption": post.get("caption"),
        })
    timings["rewrite_total"] = round(rewrite_secs, 2)
    timings["cover_total"] = round(cover_secs, 2)
    n_built = len(report["items"])
    timings["rewrite_per_item"] = round(rewrite_secs / n_built, 2) if n_built else 0
    timings["cover_per_item"] = round(cover_secs / n_built, 2) if n_built else 0
    timings["total"] = round(time.perf_counter() - started_all, 2)
    report["gate_counts"] = gate_counts
    report["finished_utc"] = iso_utc()

    (outdir / "captions.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# گزارش اجرای خشک (dry run) — کانال اخبار دنیای انیمه",
        "",
        f"- شروع: {report['started_utc']} UTC — پایان: {report['finished_utc']} UTC",
        "- **هیچ پستی به تلگرام فرستاده نشد** (dry run؛ بدون sendPhoto).",
        "",
        "## زمان‌سنجی (ثانیه)",
        "",
    ]
    for name, secs in timings.items():
        lines.append(f"- {name}: {secs}")
    lines += [
        "",
        "## شمارش",
        "",
        f"- خبر خوانده‌شده از RSS: {stats['fetched']}",
        f"- واجد شرایط (صف QUEUED): {stats['queued']}",
        f"- HOLD انسانی: {stats['held']}",
        f"- ردشده: {stats['rejected']}",
        f"- تکراری: {stats['duplicates']}",
        f"- نامزد Digest: {stats['digest']}",
        f"- قدیمی (stale): {stats['stale']}",
        f"- breaking: {stats['breaking']}",
        "",
        "## دلیل‌های رد",
        "",
    ]
    for code, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
        lines.append(f"- {code}: {count}")
    lines += ["", "## خبرهای بازنویسی‌شده + کاور", ""]
    for it in report["items"]:
        hold_note = (" — WOULD-HOLD در publish واقعی (دروازه‌های جاافتاده: "
                     + ",".join(it["missing_gates"]) + ")") if it["would_hold"] else ""
        lines.append(
            f"- [{it['source']}] {it['title_en'][:80]} — دسته: {it['category']}، "
            f"امتیاز: {it['priority_score']}، gates: {it['gates_count']}/9، "
            f"کپشن: {it['caption_chars']} کاراکتر، کاور: {it['cover_mode']}{hold_note}")
    (outdir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    log_info(f"dry run done in {timings['total']}s: fetched={stats['fetched']} "
             f"queued={stats['queued']} held={stats['held']} "
             f"rejected={stats['rejected']} duplicates={stats['duplicates']}")
    print(f"\nDRY-RUN REPORT: {outdir / 'report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
