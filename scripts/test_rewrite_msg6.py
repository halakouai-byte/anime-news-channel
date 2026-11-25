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
check("T1 gates 11/11", len(post["gates_passed"]) == 11,
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
    check(f"T3 {fname} gates 11/11", len(p["gates_passed"]) == 11,
          f"(passed {len(p['gates_passed'])}/10: {p['gates_passed']})")

# --- Test 4: adaptation detection still works ---------------------------
check("T4 'Gets TV Anime' -> adaptation",
      detect_event("Spy x Family Gets TV Anime Season 3", "") == "adaptation")
check("T4 'Ends Serialization' -> manga_ending",
      detect_event("Manga 'Oshi no Ko' Ends Serialization", "") == "manga_ending")
check("T4 summary background alone does NOT make adaptation",
      detect_event("Some Anime Announces New Season",
                   "An anime adaptation aired in 2024. The new season was announced.") != "adaptation")

# --- Test 5: award/eligibility source + "new anime" claim (msg 66) -------
# The Oscars-eligibility list article was posted as "new Gundam anime
# announced" (msg 66, 2026-11-24). The event_consistency gate had no award
# branch, so it passed; the event classifier fell through to "announcement".
OSCARS = {
    "title_en": "All You Need Is Kill, Kaguya!, Grotesqqque, More Anime "
                "Confirmed Eligible for Oscars",
    "summary_en": "Jinsei , Last Blossom , 2nd Gundam Hathaway film, Ribbon "
                  "Hero, Super Mario Galaxy Movie, Avatar Aang also eligible",
    "source_name": "Anime News Network",
    "source_url": "https://animenewsnetwork.com/news/2026-11-24/"
                  "all-you-need-is-kill-kaguya-grotesqqque-more-anime-"
                  "confirmed-eligible-for-oscars/.244148",
    "pubDate": "2026-11-24T07:55:40+00:00",
}
fx5 = extract_facts(OSCARS, BANKS)
check("T5 oscars event is award", fx5["event"] == "award",
      f"(got {fx5['event']})")
check("T5 oscars event_fa", fx5["event_fa"] == "جایزه",
      f"(got {fx5['event_fa']})")
check("T5 oscars franchise is None (roundup)", fx5["fr_en"] is None,
      f"(got {fx5['fr_en']})")
post5 = rewrite_post(OSCARS)
check("T5 oscars rewrite does NOT pass why_specific (HOLD)",
      "why_specific" not in post5["gates_passed"],
      f"(passed {post5['gates_passed']})")
check("T5 oscars rewrite does not claim a new anime",
      "انیمه تازه" not in post5["caption"])

# The gate itself: an award source + a "new anime" claim must fail, even if
# the classifier ever mislabels the event again (defence in depth).
_fx_gate = {
    "title_en": OSCARS["title_en"], "summary_en": OSCARS["summary_en"],
    "pubDate": OSCARS["pubDate"], "fr_fa": "گاندام", "fr_en": "Gundam",
    "event_fa": "انیمه تازه", "event": "announcement",
    "date_fa": None, "studio_en": None,
}
_wrong_cap = (
    "رسمی شد: انیمه تازه Gundam\n\nگاندام سکوت را شکست؛ انیمه تازه اثر "
    "اعلام شد.\n\nگاندام از آن آثاری است که هر خبر تازه‌اش بازتاب دارد.\n\n"
    "چرا مهم است؟ چون تایید انیمه تازه یعنی دنیای گاندام بزرگ‌تر می‌شود "
    "و گاندام در مرکز توجه قرار گرفت.\n\nمنبع: Anime News Network\n"
    "https://example.com/x\n\n#انیمه #Gundam #فیلم")
_gates = check_gates(_wrong_cap, "رسمی شد: انیمه تازه Gundam", _fx_gate,
                     "چون تایید انیمه تازه یعنی دنیای گاندام بزرگ‌تر می‌شود.")
check("T5 gate: award source + new-anime claim fails event_consistency",
      _gates["event_consistency"] is False)
_fx_ctrl = dict(_fx_gate, title_en="Studio X Announces New Anime Film",
                summary_en="Studio X announced a brand-new anime film for 2027.")
_gates_ctrl = check_gates(_wrong_cap, "رسمی شد: انیمه تازه Gundam", _fx_ctrl,
                          "چون تایید انیمه تازه یعنی دنیای گاندام بزرگ‌تر می‌شود.")
check("T5 gate control: no award source passes event_consistency",
      _gates_ctrl["event_consistency"] is True)

# --- Test 6: death/obituary source + "new anime" claim (msg 62) -----------
# The death of manga creator Tsukasa Sei was posted as "Shonen Jump is back;
# new anime announced" (msg 62, 2026-11-24). The event classifier had no death
# branch, so it fell through to "announcement"; the event_consistency gate had
# no death branch, so it passed.
DEATH = {
    "title_en": "Manga Creator Tsukasa Sei Dies",
    "summary_en": "Manga creator Tsukasa Sei died on November 21 due to illness. "
                  "Sei was the creator of the Tsumi to Batsu no Spica manga, "
                  "which was serialized in Shueisha's Weekly Shonen Jump magazine.",
    "source_name": "Anime News Network",
    "source_url": "https://animenewsnetwork.com/news/2026-11-23/"
                  "manga-creator-tsukasa-sei-dies/.244102",
    "pubDate": "2026-11-23T20:34:00+00:00",
}
fx6 = extract_facts(DEATH, BANKS)
check("T6 death event is death", fx6["event"] == "death",
      f"(got {fx6['event']})")
check("T6 death event_fa", fx6["event_fa"] == "درگذشت",
      f"(got {fx6['event_fa']})")
check("T6 death franchise is None (no publisher/magazine)",
      fx6["fr_en"] is None, f"(got {fx6['fr_en']})")
post6 = rewrite_post(DEATH)
check("T6 death rewrite does NOT pass why_specific (HOLD)",
      "why_specific" not in post6["gates_passed"],
      f"(passed {post6['gates_passed']})")
check("T6 death rewrite does not claim a new anime",
      "انیمه تازه" not in post6["caption"])
# "deadline" must not trigger the death branch (word boundary).
check("T6 deadline is not death",
      detect_event("Anime Expo 2027 Submission Deadline Announced", "")
      != "death")
check("T6 passes-away is death",
      detect_event("Voice Actor John Smith Passes Away", "") == "death")

# The gate itself: a death source + a "new anime" claim must fail, even if
# the classifier ever mislabels the event again (defence in depth).
_fx_gate6 = {
    "title_en": DEATH["title_en"], "summary_en": DEATH["summary_en"],
    "pubDate": DEATH["pubDate"], "fr_fa": "شونن جامپ", "fr_en": "Shonen Jump",
    "event_fa": "انیمه تازه", "event": "announcement",
    "date_fa": None, "studio_en": None,
}
_wrong_cap6 = (
    "Shonen Jump برمی‌گردد؛ انیمه تازه\n\nتقویم طرفداران شونن جامپ از امروز "
    "شلوغ‌تر شد؛ انیمه تازه اثر اعلام شد.\n\nچرا مهم است؟ چون تایید انیمه "
    "تازه یعنی دنیای شونن جامپ بزرگ‌تر می‌شود.\n\nمنبع: Anime News Network\n"
    "https://example.com/x\n\n#انیمه #ShonenJump #مانگا")
_gates6 = check_gates(_wrong_cap6, "Shonen Jump برمی‌گردد؛ انیمه تازه",
                      _fx_gate6,
                      "چون تایید انیمه تازه یعنی دنیای شونن جامپ بزرگ‌تر می‌شود.")
check("T6 gate: death source + new-anime claim fails event_consistency",
      _gates6["event_consistency"] is False)
_fx_ctrl6 = dict(_fx_gate6, title_en="Shonen Jump New Anime Announced",
                 summary_en="A new anime was announced.")
_gates_ctrl6 = check_gates(_wrong_cap6, "Shonen Jump برمی‌گردد؛ انیمه تازه",
                           _fx_ctrl6,
                           "چون تایید انیمه تازه یعنی دنیای شونن جامپ بزرگ‌تر می‌شود.")
check("T6 gate control: no death source passes event_consistency",
      _gates_ctrl6["event_consistency"] is True)

print()
if FAILURES:
    print(f"FAILED: {len(FAILURES)} — {FAILURES}")
    sys.exit(1)
print("ALL TESTS PASSED")
