"""تست رتبه‌بندی وضعیت در ادغام صف — نقد ۴ (بازگردانی انقضا).

باگ: _STATUS_RANK فقط POSTED/STALE/HOLD/QUEUED را داشت؛ REJECTED و
EXPIRED رتبه نداشتند (۰)، پس merge_queue_data ردِ expire_queue را
برمی‌گرداند — HOLD راه‌دورِ کهنه بر REJECTED محلی می‌برد و آیتم ۷۲
ساعته برای همیشه HOLD می‌ماند (۵ HOLD با created_utc ۲۰۲۶-۱۱-۲۱
و سن ۷۷٫۸ ساعت، هنوز HOLD بودند؛ در صف ۰ REJECTED و ۰ EXPIRED).
رفع: REJECTED: 3 و EXPIRED: 3 (هم‌رتبه STALE، زیر POSTED).
"""

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import merge_queue_data  # noqa: E402
from fetch import expire_queue  # noqa: E402


def _q(items):
    return {"version": 1, "items": items}


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        print(f"  got:  {got}")
        print(f"  want: {want}")
    return ok


def main() -> int:
    results = []

    # T1: REJECTED محلی در برابر HOLD راه‌دور → REJECTED می‌ماند (باگ اصلی)
    m = merge_queue_data(
        _q([{"guid": "g1", "hash": "h1", "status": "REJECTED"}]),
        _q([{"guid": "g1", "hash": "h1", "status": "HOLD",
             "hold_reason": "low-confidence"}]),
    )
    results.append(check("T1 REJECTED(local) vs HOLD(remote) stays REJECTED",
                         m["items"][0]["status"], "REJECTED"))

    # T2: EXPIRED محلی در برابر QUEUED راه‌دور → EXPIRED می‌ماند
    m = merge_queue_data(
        _q([{"guid": "g2", "hash": "h2", "status": "EXPIRED"}]),
        _q([{"guid": "g2", "hash": "h2", "status": "QUEUED"}]),
    )
    results.append(check("T2 EXPIRED(local) vs QUEUED(remote) stays EXPIRED",
                         m["items"][0]["status"], "EXPIRED"))

    # T3: POSTED همیشه می‌برد (حتی بر REJECTED)
    m = merge_queue_data(
        _q([{"guid": "g3", "hash": "h3", "status": "POSTED", "message_id": 99}]),
        _q([{"guid": "g3", "hash": "h3", "status": "REJECTED"}]),
    )
    results.append(check("T3 POSTED(local) vs REJECTED(remote) stays POSTED",
                         m["items"][0]["status"], "POSTED"))

    # T4: تساوی رتبه (REJECTED در برابر STALE) → remote می‌برد (قانون کلی ادغام)
    m = merge_queue_data(
        _q([{"guid": "g4", "hash": "h4", "status": "REJECTED"}]),
        _q([{"guid": "g4", "hash": "h4", "status": "STALE"}]),
    )
    results.append(check("T4 REJECTED(local) vs STALE(remote) tie -> remote STALE",
                         m["items"][0]["status"], "STALE"))

    # T5: جهت برعکس هم درست است — REJECTED راه‌دور بر HOLD محلی می‌برد
    m = merge_queue_data(
        _q([{"guid": "g5", "hash": "h5", "status": "HOLD",
             "hold_reason": "low-confidence"}]),
        _q([{"guid": "g5", "hash": "h5", "status": "REJECTED"}]),
    )
    results.append(check("T5 HOLD(local) vs REJECTED(remote) -> REJECTED",
                         m["items"][0]["status"], "REJECTED"))

    # T6: مسیر کامل — HOLD ۷۸ ساعته با expire_queue رد می‌شود و ادغام
    # با صف راه‌دور (که هنوز HOLD دارد) آن را برنمی‌گرداند
    now = datetime.now(timezone.utc)
    created = (now - timedelta(hours=78)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with tempfile.TemporaryDirectory() as td:
        arch = str(Path(td) / "archive.jsonl")
        local = _q([{"guid": "g6", "hash": "h6", "status": "HOLD",
                     "hold_reason": "low-confidence", "created_utc": created,
                     "title": "Old Hold"}])
        stats = expire_queue(local, {"posted_hashes": {}}, archive_path=arch)
        results.append(check("T6a expire_queue rejects 78h HOLD",
                             (local["items"][0]["status"], stats["hold_rejected"]),
                             ("REJECTED", 1)))
        merged = merge_queue_data(
            local,
            _q([{"guid": "g6", "hash": "h6", "status": "HOLD",
                 "hold_reason": "low-confidence", "created_utc": created,
                 "title": "Old Hold"}]),
        )
        results.append(check("T6b merged REJECTED survives remote HOLD",
                             merged["items"][0]["status"], "REJECTED"))

    failed = [r for r in results if not r]
    print(f"\n{'ALL PASSED' if not failed else f'FAILED: {len(failed)} check(s)'} "
          f"({len(results)} checks)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
