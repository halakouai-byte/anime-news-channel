"""تست ادغام queue_size — نقد ۳.

queue_size عکس لحظه‌ای صف است، نه شمارنده: مقدار ۵۱ کهنه از max-merge
چسبیده بود و با هر ادغام برمی‌گشت. حالا مقدار تازه‌ترین state می‌برد
(تازه‌ترینِ last_fetch_utc / last_publish_utc).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import merge_state_data  # noqa: E402


def _state(queue_size, last_fetch, last_publish="", posts_today=0):
    return {
        "posted_message_ids": [],
        "posted_hashes": {},
        "story_keys": {},
        "seen_guids": [],
        "seen_at": {},
        "recent_titles": [],
        "last_fetch_utc": last_fetch,
        "last_publish_utc": last_publish,
        "counters": {"posts_total": 0, "posts_today": posts_today,
                     "posts_today_date": "2026-11-23"},
        "circuit_breaker": {"active": False, "activated_at": None,
                            "posts_today": posts_today,
                            "queue_size": queue_size},
    }


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        print(f"  got:  {got}")
        print(f"  want: {want}")
    return ok


def main() -> int:
    results = []

    # ۱) local تازه‌تر است (queue_size=2) و remote کهنه (51) → ۲
    m = merge_state_data(
        _state(2, "2026-11-23T06:00:00Z"),
        _state(51, "2026-11-22T20:00:00Z"))
    results.append(check("fresh-local-wins",
                         m["circuit_breaker"]["queue_size"], 2))

    # ۲) remote تازه‌تر است (3) و local کهنه (51) → ۳
    m = merge_state_data(
        _state(51, "2026-11-23T02:00:00Z"),
        _state(3, "2026-11-23T04:00:00Z"))
    results.append(check("fresh-remote-wins",
                         m["circuit_breaker"]["queue_size"], 3))

    # ۳) بازتولید واقعی نقد ۳: state زنده (51، last_fetch ۰۲:۴۴) +
    #    ران تازه (2، last_fetch ۰۶:۰۰) → ۲ (نه ۵۱)
    m = merge_state_data(
        _state(2, "2026-11-23T06:00:00Z", "2026-11-23T03:06:01Z"),
        _state(51, "2026-11-23T02:44:18Z", "2026-11-23T03:06:01Z"))
    results.append(check("real-review3-case-51-drops-to-2",
                         m["circuit_breaker"]["queue_size"], 2))

    # ۴) بقیه فیلدها دست نخورده: posts_today هنوز max، active هنوز OR
    m = merge_state_data(
        _state(2, "2026-11-23T06:00:00Z", posts_today=5),
        _state(51, "2026-11-22T20:00:00Z", posts_today=7))
    results.append(check("posts_today-still-max",
                         m["circuit_breaker"]["posts_today"], 7))
    local = _state(2, "2026-11-23T06:00:00Z")
    remote = _state(51, "2026-11-22T20:00:00Z")
    remote["circuit_breaker"]["active"] = True
    remote["circuit_breaker"]["activated_at"] = "2026-11-22T19:00:00Z"
    m = merge_state_data(local, remote)
    results.append(check("active-still-or",
                         m["circuit_breaker"]["active"], True))

    print(f"{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
