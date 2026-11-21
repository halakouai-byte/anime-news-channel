"""Regression test for the HOLD re-test fix (critic review #1, run 44936475145).

Run 44936475145 posted 2 new items but Oshi No Ko (85) + BanG Dream (80)
stayed HOLD with `gates_failed:why_specific` even though the why_specific
fix made them pass 9/9 locally — because publish.py only read
QUEUED/APPROVED items and never re-evaluated HOLD items.

Run: python3 scripts/test_hold_retest.py  (from the repo root)
Exits non-zero on any failure. No network, no Telegram — pure logic.
Facts below are the real queue records (2026-11-21, live queue.json).
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from publish import is_pending
from rewrite import rewrite_post, extract_facts, check_gates, load_banks

FAILURES = []


def check(name, cond, extra=""):
    print(("PASS - " if cond else "FAIL - ") + name + (" " + str(extra) if extra else ""))
    if not cond:
        FAILURES.append(name)


# --- T1: the predicate -------------------------------------------------------
check("T1 QUEUED is pending", is_pending({"status": "QUEUED"}))
check("T1 APPROVED is pending", is_pending({"status": "APPROVED"}))
check("T1 HOLD gates_failed is pending (re-test)",
      is_pending({"status": "HOLD", "hold_reason": "gates_failed:why_specific"}))
check("T1 HOLD low-confidence is NOT pending (human review)",
      not is_pending({"status": "HOLD", "hold_reason": "low-confidence"}))
check("T1 HOLD without reason is NOT pending",
      not is_pending({"status": "HOLD", "hold_reason": ""}))
check("T1 POSTED is NOT pending", not is_pending({"status": "POSTED"}))
check("T1 STALE is NOT pending", not is_pending({"status": "STALE"}))

# --- T2: the two real HOLD items pass 9/9 with the fixed code ----------------
REAL = [
    ("Oshi No Ko 85 (ANN)", {
        "title_en": "Yen Press Licenses [Oshi No Ko] Étude for Two, Bungo Stray Dogs: "
                    "The Untold Origins of the Detective Agency, More Manga/Novels",
        "summary_en": "Also: Mercenary Sisters , Caring for a Corpse , "
                      "Megarosalia , more",
        "source_name": "ANN",
        "source_url": "https://animenewsnetwork.com/news/2026-11-20/yen-press-licenses-"
                      "oshi-no-ko-etude-for-two-bungo-stray-dogs-the-untold-origins-of-the-detective-/.244035",
        "pubDate": "2026-11-20T19:57:31+00:00",
        "category_hint": "مانگا و اقتباس",
    }),
    ("BanG Dream 80 (ANN)", {
        "title_en": "BanG Dream! Yume∞Mita Series Confirms New Anime in Production",
        "summary_en": "TV anime based on BanG Dream! project's Mugendai Mewtype band "
                      "premiered on July 2",
        "source_name": "ANN",
        "source_url": "https://animenewsnetwork.com/news/2026-11-20/bang-dream-yume-mita-"
                      "series-confirms-new-anime-in-production/.244026",
        "pubDate": "2026-11-20T15:59:17+00:00",
        "category_hint": "فصل جدید",
    }),
]
for name, facts in REAL:
    post = rewrite_post(facts)
    passed = post.get("gates_passed", [])
    check(f"T2 {name} gates 9/9", len(passed) == 9, f"({len(passed)}/9: {passed})")
    check(f"T2 {name} is pending after fix",
          is_pending({"status": "HOLD",
                      "hold_reason": "gates_failed:why_specific"}))
    print(f"     title: {post.get('title')}")

# --- T3: the license event (run 44936475145) ---------------------------------
# The Oshi No Ko item is a Yen Press LICENSE announcement, not a new anime.
# Before the fix it rewrote to "Bungo Stray Dogs در راه است؛ انیمه تازه"
# with a body claiming a new anime is being made from the manga — the same
# inversion class as msg 6. It must now be event "license" with a correct
# caption and 9/9 gates.
BANKS = load_banks()
LIC_FACTS = REAL[0][1]
fx = extract_facts(LIC_FACTS, BANKS)
check("T3 Oshi No Ko event is license", fx.get("event") == "license",
      f"(got {fx.get('event')})")
check("T3 Oshi No Ko event_fa", fx.get("event_fa") == "لایسنس تازه",
      f"(got {fx.get('event_fa')})")
check("T3 Oshi No Ko category", fx.get("category") == "مانگا و اقتباس",
      f"(got {fx.get('category')})")
lic_post = rewrite_post(LIC_FACTS)
lic_cap = lic_post.get("caption", "")
check("T3 no fresh-anime claim", "انیمه تازه" not in lic_cap)
check("T3 no 'made from manga' body claim", "ساخته می‌شود" not in lic_cap)
check("T3 mentions the license", "لایسنس" in lic_cap)
check("T3 gates 9/9", len(lic_post.get("gates_passed", [])) == 9,
      f"({lic_post.get('gates_passed')})")
print("--- T3 caption ---")
print(lic_cap)
print("------------------")

# --- T4: the gate catches the OLD (wrong) license caption --------------------
OLD_WRONG_LIC_CAPTION = """Bungo Stray Dogs در راه است؛ انیمه تازه

از ژاپن خبر رسید: بانگو استری داگز در مسیر تازه‌ای افتاده و انیمه تازه آن اعلام شد.

این اثر از روی مانگایی به همین نام ساخته می‌شود؛ مانگایی که خواننده‌هایش مدت‌هاست چشم‌به‌راه نسخه انیمه آن بوده‌اند. طرفداران این اثر مدت‌ها منتظر چنین خبری بودند و حالا با این اعلام، تصویر آینده اثر روشن‌تر از قبل شده است.

چرا مهم است؟ چون تایید انیمه تازه یعنی قصه بانگو استری داگز ادامه دارد و بخشی که مدت‌ها درباره‌اش حرف زده می‌شد، حالا واقعا ساخته می‌شود.

منبع: ANN
https://animenewsnetwork.com/news/2026-11-20/yen-press-licenses-oshi-no-ko-etude-for-two-bungo-stray-dogs-the-untold-origins-of-the-detective-/.244035

#انیمه #BungoStrayDogs #مانگا"""
OLD_WRONG_LIC_WHY = ("چون تایید انیمه تازه یعنی قصه بانگو استری داگز ادامه دارد و "
                     "بخشی که مدت‌ها درباره‌اش حرف زده می‌شد، حالا واقعا ساخته می‌شود.")
gates4 = check_gates(OLD_WRONG_LIC_CAPTION, "Bungo Stray Dogs در راه است؛ انیمه تازه",
                     fx, OLD_WRONG_LIC_WHY)
check("T4 event_consistency FAILS on the old license caption",
      gates4.get("event_consistency") is False, f"(gates: {gates4})")

if FAILURES:
    print(f"\n{len(FAILURES)} FAILURES: {FAILURES}")
    sys.exit(1)
print("\nALL TESTS PASSED (incl. license event)")
