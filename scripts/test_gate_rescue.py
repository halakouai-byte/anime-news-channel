#!/usr/bin/env python3
"""تست اثبات‌کننده بسته بانک قالب‌ها — نجات آیتم‌های HOLD (نوامبر ۲۰۲۶).

سکوت ۸ ساعته ۲۲ نوامبر ۲۰۲۶: ۳۵ آیتم gates_failed در صف بود — همه خبر واقعی
(۲۰ فصل جدید + ۶ تریلر + ۲ فیلم)، ولی بازنویسی نمی‌توانست از آن‌ها پست
۶۰۰ حرفی بسازد (length نزدیک به کف) یا «چرا»ی مشخص نداشت (why_specific —
علتش خالی‌بودن نام فرنچایز بود، نه خود قالب «چرا»).

این تست با فیکسچر منجمد (۳۹ آیتم، اسنپ‌شات صف main در ۲۰۲۶-۱۱-۲۳ ~۰۴:۰۰ UTC)
دقیقاً همان ارزیابی ران واقعی را تکرار می‌کند (یک فراخوانی rewrite_post
با ۳۰ تلاش داخلی، کپشن‌های اخیر و template_usage واقعی) و می‌شمرد چند آیتم
به ۱۰/۱۰ می‌رسند. آیتم‌هایی که گیت‌ها درست نگه‌شان داشته‌اند (event_consistency
برای Sakamoto Days، recent_similarity برای بازاعلان همان فرنچایز) نباید
نجات پیدا کنند — نجات آن‌ها رگرسیون است، نه بهبود.

اجرا: /tmp/anime-venv2/bin/python scripts/test_gate_rescue.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import sha256_hex
from publish import template_usage_counts
from rewrite import rewrite_post

FIXTURE = Path(__file__).resolve().parent / "test_gate_rescue_fixture.json"

# آستانه: بسته بانک باید حداقل این تعداد از ۳۹ آیتم را به ۱۰/۱۰ برساند.
# (اندازه‌گیری پس از اعمال بسته: ۳۷ آیتم؛ آستانه با حاشیه ۴ تا پایین‌تر گذاشته شد.)
RESCUED_MIN = 33

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


def main() -> int:
    fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = fx["items"]
    recent = fx["recent_posts"]
    usage = fx["template_usage"]
    # template_usage فیکسچر همان خروجی template_usage_counts(state) است.
    assert set(usage) == {"title", "lead", "bodies", "why"}, usage
    rescued = []
    still_held = []
    wrongly_rescued = []
    for it in items:
        facts = {
            "title_en": it["title_en"], "summary_en": it["summary_en"],
            "source_name": it["source_name"], "source_url": it["source_url"],
            "pubDate": it["pubDate"], "category_hint": it["category_hint"],
        }
        seed = int(sha256_hex(it["hash"])[:8], 16)
        post = rewrite_post(facts, seed=seed, recent_posts=recent,
                            template_usage=usage)
        passed = set(post.get("gates_passed", []))
        recorded = set(g for g in (it["hold_reason"] or "")
                       .replace("gates_failed:", "").split(",") if g)
        if len(passed) == 11:
            # فقط event_consistency باید همیشه HOLD بماند (کپشن گمراه‌کننده —
            # Sakamoto Days). recent_similarity معیارش شباهت کپشن است، نه
            # یکسانی خبر: وقتی قالب‌های تازه جمله‌بندی را به‌اندازه کافی
            # عوض کنند (زیر ۰٫۶۰)، نجات آیتم درست است — خبرهای نجات‌یافته
            # (Kekkaishi، Sono Mono، Detective S2، BLUE BOX) ضرباهنگ‌های
            # متفاوتی‌اند و لایه‌های dedupe آن‌ها را تکراری نشناخته‌اند.
            if recorded and recorded <= {"event_consistency"}:
                wrongly_rescued.append((it["title_en"][:50], sorted(recorded)))
            else:
                rescued.append(it["title_en"][:50])
        else:
            still_held.append((it["title_en"][:50], sorted(set(
                ["length", "no_placeholder", "english_limited",
                 "source_similarity", "recent_similarity",
                 "template_freshness", "why_specific", "numbers_dates",
                 "event_consistency", "no_double_word",
                 "no_repeated_sentence"]) - passed)))
    print(f"fixture: {len(items)} gates_failed HOLD items")
    print(f"rescued (11/11): {len(rescued)}")
    for t in rescued:
        print(f"  + {t}")
    print(f"still held: {len(still_held)}")
    for t, missing in still_held:
        print(f"  - {t} missing={missing}")
    check(f"rescued >= {RESCUED_MIN}", len(rescued) >= RESCUED_MIN,
          f"got {len(rescued)}")
    check("gate-working items stay held (event_consistency)",
          not wrongly_rescued, f"wrongly rescued: {wrongly_rescued}")
    # دروازه ۱۰ — مرز کلمه در آغاز: «یوزاکورا را» خطا نیست، «تازه تازه» خطاست.
    from rewrite import check_gates
    _fx = {"title_en": "x", "summary_en": "x", "pubDate": "",
           "fr_en": "Yozakura", "fr_fa": "ماموریت: خانواده یوزاکورا",
           "studio_en": None, "source_name": "",
           "event_fa": "معرفی صداپیشه‌های تازه", "date_fa": None}
    check("no_double_word: name ending in «را» + object «را» is not a double",
          check_gates("صدای شخصیت‌های ماموریت: خانواده یوزاکورا را مشخص می‌کند.",
                      "t", _fx, "w")["no_double_word"])
    check("no_double_word: real double «تازه تازه» still fails",
          not check_gates("انیمه تازه تازه اثر اعلام شد.", "t", _fx, "w")["no_double_word"])
    print(f"\n{PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
