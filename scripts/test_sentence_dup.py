#!/usr/bin/env python3
"""تست نگهبان تکرار جمله — پیام ۲۷ (Hidan no Aria، ۲۳ نوامبر ۲۰۲۶).

حادثه: پیام ۲۷ کپشن ۷۸۷ حرفی داشت که جمله body_premiere_long دوبار پشت
سر هم در بدنه آمده بود («طبق اعلام رسمی، آریا سلاح سرخ در آوریل ۲۰۲۷
پخش می‌شود ... برنامه بچینند.» × ۲). علت دو مکانیزم بود، هر دو از یک
نقص در _build_once:
  ۱) همان قالب دوبار انتخاب شد (body_premiere_long در date_bodies و هم
     در other — چون other فقط body_premiere و body_source_date را کنار
     می‌گذاشت، نه body_premiere_long را که بسته بانک ۲۳ نوامبر اضافه
     کرده بود)؛
  ۲) دو قالب تاریخی متفاوت با جمله هم‌پوشان (body_premiere + body_premiere_long
     — جمله اولی پیشوند دومی است)، چون فقط یکی از آن‌ها از other کنار
     گذاشته می‌شد.
رفع: other همه قالب‌های تاریخی را کنار می‌گذارد (یک مجموعه id مشترک)،
و دروازه ۱۱ (no_repeated_sentence) هر کپشنی را که یک جمله ≥ ۴۰ حرفی
دوبار داشته باشد رد می‌کند — نگهبان نهایی برای هر منبع تکرار دیگر.

T1: تست واحد دروازه. T2: رگرسیون — آیتم Hidan روی ۱۰۰ seed: هیچ کپشن
نتیجه‌ای نباید جمله تکراری داشته باشد و دو بدنه هرگز یک id ندارند.
T3: کپشن واقعی پیام ۲۷ باید دروازه را رد کند، پیام ۳۰ (همان جمله، یک بار)
باید قبول شود.

اجرا: /tmp/anime-venv2/bin/python scripts/test_sentence_dup.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rewrite import check_gates, rewrite_post

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


# کپشن واقعی پیام ۲۷ (۷۸۷ حرف، جمله تکراری) و پیام ۳۰ (۷۲۲ حرف، تمیز)
MSG27_CAPTION = "Aria the Scarlet Ammo | معرفی صداپیشه‌های تازه در آوریل ۲۰۲۷\n\nدر میان خبرهای امروز، خبر آریا سلاح سرخ را هم داریم: معرفی صداپیشه‌های تازه اثر تایید شد.\n\nطبق اعلام رسمی، آریا سلاح سرخ در آوریل ۲۰۲۷ پخش می‌شود و این تاریخ از حالا در تقویم طرفداران اثر ثبت شده است؛ تاریخی که انتظار برای آن از امروز رسماً آغاز شده و طرفداران می‌توانند برایش برنامه بچینند. طبق اعلام رسمی، آریا سلاح سرخ در آوریل ۲۰۲۷ پخش می‌شود و این تاریخ از حالا در تقویم طرفداران اثر ثبت شده است؛ تاریخی که انتظار برای آن از امروز رسماً آغاز شده و طرفداران می‌توانند برایش برنامه بچینند.\n\nچرا مهم است؟ چون معرفی صداپیشه‌های تازه، صدای شخصیت‌های آریا سلاح سرخ را مشخص می‌کند و همان صداهایی است که در فصل تازه خواهید شنید.\n\nمنبع: MyAnimeList News\nhttps://myanimelist.net/news/74967474\n\n#انیمه #AriaTheScarletAmmo #فصل_جدید"

MSG30_CAPTION = "Omniscient Reader's Viewpoint | تریلر تازه اعلام شد\n\nدیدگاه خواننده دانای کل دوباره خبرساز شد؛ این‌بار با تریلر تازه.\n\nطبق اعلام رسمی، دیدگاه خواننده دانای کل در ۲۴ نوامبر پخش می‌شود و این تاریخ از حالا در تقویم طرفداران اثر ثبت شده است؛ تاریخی که انتظار برای آن از امروز رسماً آغاز شده و طرفداران می‌توانند برایش برنامه بچینند.\n\nچرا مهم است؟ چون تریلر تازه دیدگاه خواننده دانای کل اولین نگاه واقعی به فضای این اثر است و نشان می‌دهد عوامل ساخت چه لحنی برای ادامه قصه انتخاب کرده‌اند؛ نگاهی که تا امروز هیچ‌کجا دیده نشده بود.\n\nمنبع: Anime News Network\nhttps://animenewsnetwork.com/news/2026-11-21/omniscient-reader-viewpoint-webtoon-returns-with-season-2-on-november-24/.244045\n\n#انیمه #OmniscientReaderSViewpoint #فصل_جدید"

_FX = {"title_en": "x", "summary_en": "x", "pubDate": "",
       "fr_en": "Yozakura", "fr_fa": "ماموریت: خانواده یوزاکورا",
       "studio_en": None, "source_name": "",
       "event_fa": "معرفی صداپیشه‌های تازه", "date_fa": None}

print("T1 gate unit tests")
_dup = ("طبق اعلام رسمی، آریا سلاح سرخ در آوریل ۲۰۲۷ پخش می‌شود و این تاریخ "
        "از حالا در تقویم طرفداران اثر ثبت شده است؛ تاریخی که انتظار برای آن "
        "از امروز رسماً آغاز شده و طرفداران می‌توانند برایش برنامه بچینند. ")
check("duplicated long sentence fails the gate",
      not check_gates(_dup + _dup, "t", _FX, "w")["no_repeated_sentence"])
check("clean caption passes the gate",
      check_gates("خبر تازه‌ای از دنیای انیمه رسید؛ اثری که طرفدارانش مدت‌ها "
                  "منتظرش بودند، حالا با یک تریلر تازه برگشته است.",
                  "t", _FX, "w")["no_repeated_sentence"])
check("short repeated phrase (<40 chars) is not flagged",
      check_gates("خبر تازه آمد. خبر تازه آمد.", "t", _FX, "w")["no_repeated_sentence"])
_half = ("طبق اعلام رسمی، آریا سلاح سرخ در آوریل ۲۰۲۷ پخش می‌شود و این تاریخ "
         "از حالا در تقویم طرفداران اثر ثبت شده است. ")
_long = _half + "تاریخی که انتظار برای آن از امروز رسماً آغاز شده و طرفداران می‌توانند برایش برنامه بچینند. "
check("body_premiere + body_premiere_long overlap fails (shared first half)",
      not check_gates(_half + _long, "t", _FX, "w")["no_repeated_sentence"])
check("two different long sentences pass",
      check_gates("طبق اعلام رسمی، آریا سلاح سرخ در آوریل ۲۰۲۷ پخش می‌شود و این تاریخ "
                  "از حالا در تقویم طرفداران اثر ثبت شده است. "
                  "هم‌زمان با این خبر، کی‌ویژوال تازه اثر هم منتشر شد؛ تصویری که "
                  "حال‌وهوای بخش تازه را بهتر از هر توضیحی نشان می‌دهد.",
                  "t", _FX, "w")["no_repeated_sentence"])

print("T3 real captions from the channel")
check("msg 27 caption fails the gate",
      not check_gates(MSG27_CAPTION, "Aria the Scarlet Ammo | معرفی صداپیشه‌های تازه در آوریل ۲۰۲۷",
                      _FX, "w")["no_repeated_sentence"])
check("msg 30 caption passes the gate",
      check_gates(MSG30_CAPTION, "Omniscient Reader's Viewpoint | تریلر تازه اعلام شد",
                  _FX, "w")["no_repeated_sentence"])

print("T2 regression: Hidan item over 100 seeds")
fx = json.loads((Path(__file__).resolve().parent / "test_gate_rescue_fixture.json").read_text(encoding="utf-8"))
hidan = next(it for it in fx["items"] if "Hidan" in it["title_en"])
facts = {k: hidan[k] for k in ("title_en", "summary_en", "source_name",
                               "source_url", "pubDate", "category_hint")}
dup_results = []
same_body = []
for seed in range(100):
    post = rewrite_post(facts, seed=seed, recent_posts=fx["recent_posts"],
                        template_usage=fx["template_usage"])
    bodies = post["template_ids"]["bodies"]
    if len(bodies) == 2 and bodies[0] == bodies[1]:
        same_body.append((seed, bodies))
    # دروازه ۱۱ در مسیر واقعی (rewrite_post) سنجیده می‌شود: اگر کپشن
    # بهترین تلاش جمله تکراری داشته باشد، این گیت در gates_passed نیست.
    if "no_repeated_sentence" not in post.get("gates_passed", []):
        dup_results.append(seed)
check("no result caption has a repeated long sentence (100 seeds)",
      not dup_results, f"dup in seeds {dup_results[:5]}")
check("the two body templates are never the same id (100 seeds)",
      not same_body, f"same body id in seeds {same_body[:3]}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
