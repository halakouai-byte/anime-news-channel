"""Regression test for the msg-6 content-inversion fix (critic review #1).
Run: python3 scripts/test_rewrite_msg6.py  (from the repo root)
Exits non-zero on any failure. No network, no Telegram — pure rewrite logic.
"""
import json
import re
import sys

import os
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
from rewrite import (  # noqa: E402
    check_gates,
    detect_event,
    extract_facts,
    load_banks,
    rewrite_post,
)

BANKS = load_banks()
FAILURES = []


def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL"), "-", name, detail)
    if not cond:
        FAILURES.append(name)


TAKAMINE = {
    "title_en": "Manga 'Haite Kudasai, Takamine-san' Ends Serialization",
    "summary_en": (
        "The official X account for author Yuuichi Hiiragi announced on Friday "
        "that the Haite Kudasai Takamine-san (Please Put Them On, Takamine-san) "
        "manga will end in the February issue of Gangan Joker magazine, marking "
        "the end of the manga's nearly 8-year run. Hiiragi began serializing the "
        "ecchi romance comedy manga in Gangan Joker in January 2019. Square Enix "
        "published the 11th volume on February 20. A 12-episode television anime "
        "adaptation produced by LIDENFILMS aired in Spring 2025. Crunchyroll "
        "streamed the anime as it aired in Japan."
    ),
    "source_name": "MyAnimeList News",
    "source_url": "https://myanimelist.net/news/74961851",
    "pubDate": "2026-11-20T16:56:46+00:00",
}

OLD_WRONG_CAPTION = (
    "Haite Kudasai, Takamine-san؛ اقتباس انیمه‌ای تازه تازه\n\n"
    "نوبت هایته کوداسای، تاکامینه‌سان بود که خبرساز شود؛ اقتباس انیمه‌ای تازه اثر رسما اعلام شد.\n\n"
    "این اثر از روی مانگایی به همین نام ساخته می‌شود؛ مانگایی که خواننده‌هایش مدت‌هاست چشم‌به‌راه نسخه انیمه آن بوده‌اند. "
    "ساخت این بخش تازه بر عهده کرانچی‌رول است؛ استودیویی که نامش برای طرفداران انیمه، خودش یک نشانه کیفیت است.\n\n"
    "چرا مهم است؟ چون اقتباس هایته کوداسای، تاکامینه‌سان به انیمه یعنی مانگایی که خواننده‌هایش مدت‌ها منتظرش بودند، حالا با صدا و حرکت به صفحه می‌آید.\n\n"
    "منبع: MyAnimeList News\n\nhttps://myanimelist.net/news/74961851\n\n"
    "#انیمه #HaiteKudasaiTakamineSan #مانگا"
)
OLD_WRONG_WHY = (
    "چون اقتباس هایته کوداسای، تاکامینه‌سان به انیمه یعنی مانگایی که خواننده‌هایش "
    "مدت‌ها منتظرش بودند، حالا با صدا و حرکت به صفحه می‌آید."
)

# --- Test 1: the bug, fixed ---------------------------------------------
fx = extract_facts(TAKAMINE, BANKS)
check("T1 event is manga_ending", fx["event"] == "manga_ending",
      f"(got {fx['event']})")
check("T1 event_fa", fx["event_fa"] == "پایان سریال‌سازی",
      f"(got {fx['event_fa']})")
check("T1 category", fx["category"] == "مانگا و اقتباس",
      f"(got {fx['category']})")
post = rewrite_post(TAKAMINE)
cap = post["caption"]
check("T1 no fresh-adaptation claim", "اقتباس انیمه‌ای تازه" not in cap)
check("T1 no Crunchyroll-as-producer", "کرانچی‌رول" not in cap)
check("T1 mentions the ending", "پایان" in cap)
check("T1 gates 9/9", len(post["gates_passed"]) == 9,
      f"(passed {post['gates_passed']})")
print("--- T1 caption ---")
print(cap)
print("------------------")

# --- Test 2: the new gate catches the OLD (wrong) post -------------------
gates = check_gates(OLD_WRONG_CAPTION, "Haite Kudasai, Takamine-san؛ اقتباس انیمه‌ای تازه تازه",
                    fx, OLD_WRONG_WHY)
check("T2 event_consistency FAILS on the old caption",
      gates.get("event_consistency") is False,
      f"(gates: {gates})")

# --- Test 3: no regression on the 5 human-QA samples --------------------
SAMPLES = [
    ("sample-01-bang-dream-yumemita.md", "announcement"),
    ("sample-02-spice-and-wolf-s2.md", None),
    ("sample-03-tougen-anki-cast.md", None),
    ("sample-04-kuku-loop-2027.md", None),
    ("sample-05-pen-to-wappa-premiere.md", None),
]
for fname, expected_event in SAMPLES:
    text = open(f"/home/hatch/workspace/anime-news-channel/samples-rewrite/{fname}",
                encoding="utf-8").read()
    title = re.search(r"\*\*تیتر:\*\* (.+)", text).group(1).strip()
    summary = re.search(r"\*\*خلاصه:\*\* (.+)", text).group(1).strip()
    source = re.search(r"\*\*منبع:\*\* (.+?) —", text).group(1).strip()
    url = re.search(r"\*\*لینک منبع:\*\* (\S+)", text).group(1).strip()
    recorded = re.search(r"\*\*رویداد:\*\* (\S+)", text).group(1).strip()
    facts = {"title_en": title, "summary_en": summary, "source_name": source,
             "source_url": url, "pubDate": ""}
    p = rewrite_post(facts)
    fx2 = extract_facts(facts, BANKS)
    check(f"T3 {fname} event unchanged ({recorded})",
          fx2["event"] == recorded, f"(got {fx2['event']})")
    check(f"T3 {fname} gates 9/9", len(p["gates_passed"]) == 9,
          f"(passed {len(p['gates_passed'])}/9: {p['gates_passed']})")

# --- Test 4: adaptation detection still works ---------------------------
check("T4 'Gets TV Anime' -> adaptation",
      detect_event("Spy x Family Gets TV Anime Season 3", "") == "adaptation")
check("T4 'Ends Serialization' -> manga_ending",
      detect_event("Manga 'Oshi no Ko' Ends Serialization", "") == "manga_ending")
check("T4 summary background alone does NOT make adaptation",
      detect_event("Some Anime Announces New Season",
                   "An anime adaptation aired in 2024. The new season was announced.") != "adaptation")

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} — {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")
