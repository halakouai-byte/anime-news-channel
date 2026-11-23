"""تست گارد _has_premiered — نقد ۳ (پیام ۱۸ زنده).

پیام ۱۸: بدنه «بخش تازه این اثر پیش‌تر پخش خود را آغاز کرده بود» برای
قوس تازه Tougen Anki آمد — در حالی که فقط بخش قبلی پخش شده بود و قوس
تازه هنوز پخش نشده بود. گارد قدیم فقط «premiered» در خلاصه + فصل
برگشتی می‌خواست؛ گارد تازه تاریخِ چسبیده به «premiered» را با date_fa
همین آیتم می‌سنجد.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rewrite import _has_premiered, extract_facts, load_banks, rewrite_post  # noqa: E402

BANKS = load_banks()


def _fx(title, summary, date_fa):
    return {"title_en": title, "summary_en": summary, "date_fa": date_fa}


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        print(f"  got:  {got}")
        print(f"  want: {want}")
    return ok


def main() -> int:
    results = []

    # ۱) «premiered» در تیتر: خودِ خبر است
    results.append(check(
        "premiered-in-title",
        _has_premiered(_fx(
            "Demon Slayer Season 2 Premiered on October 10",
            "The second season premiered on October 10, 2021.", "۱۰ اکتبر ۲۰۲۱")),
        True))

    # ۲) پیام ۱۸ واقعی (خلاصه واقعی MAL 74961958، خوانده‌شده ۲۳ نوامبر):
    #    «The first part of the second season ... premiered on October 2»
    #    — بدون سال، و قوس تازه (Nikko Kegon no Taki-hen) هیچ تاریخ پخش
    #    آینده‌ای در مقاله ندارد؛ پس date_fa=None است و گارد رد می‌کند.
    #    گارد قدیم True می‌داد (همان باگ زنده پیام ۱۸).
    results.append(check(
        "msg18-real-mal-summary",
        _has_premiered(_fx(
            "'Tougen Anki: Nikko Kegon no Taki-hen' Unveils Additional Cast",
            "The official website for the Tougen Anki: Nikko Kegon no Taki-hen "
            "(Tougen Anki: Nikko Kegon Falls Arc) television anime unveiled "
            "additional cast members on Saturday. The first part of the second "
            "season adapting Yura Urushibara's action fantasy manga premiered "
            "on October 2 at 11.30 p.m. on Nippon Television's Friday Anime "
            "Night programming block, followed by BS Nippon Television.",
            None)),
        False))

    # ۳) تاریخ «premiered» همان date_fa است → درست
    results.append(check(
        "premiered-date-matches-date_fa",
        _has_premiered(_fx(
            "Frieren Season 2 Unveils New Cast",
            "The second season premiered on January 16, 2026, and new cast "
            "members were revealed on Friday.", "۱۶ ژانویه ۲۰۲۶")),
        True))

    # ۴) ماه + سال هم‌خوان (بدون روز)
    results.append(check(
        "premiered-month-year-matches",
        _has_premiered(_fx(
            "Kaiju No. 8 Season 2 Announces Blu-ray",
            "The second season premiered in July 2025 to strong ratings.",
            "ژوئیه ۲۰۲۵")),
        True))

    # ۵) بدون date_fa: محافظه‌کارانه رد می‌شود
    results.append(check(
        "no-date_fa-rejects",
        _has_premiered(_fx(
            "Some Anime Season 2 Unveils Cast",
            "The second season premiered last year.", None)),
        False))

    # ۶) «premiered» بدون تاریخِ چسبیده: رد می‌شود
    results.append(check(
        "premiered-without-date-rejects",
        _has_premiered(_fx(
            "Some Anime Season 2 Unveils Cast",
            "The second season premiered earlier and continues this fall.",
            "۲۰۲۷")),
        False))

    # ۷) خط‌مشی کامل با خلاصه واقعی پیام ۱۸: بدنه body_season_premiered
    #    انتخاب نمی‌شود
    post = rewrite_post({
        "title_en": "'Tougen Anki: Nikko Kegon no Taki-hen' Unveils Additional Cast",
        "summary_en": "The official website for the Tougen Anki: Nikko Kegon no Taki-hen "
                      "(Tougen Anki: Nikko Kegon Falls Arc) television anime unveiled "
                      "additional cast members on Saturday. The first part of the second "
                      "season adapting Yura Urushibara's action fantasy manga premiered "
                      "on October 2 at 11.30 p.m. on Nippon Television's Friday Anime "
                      "Night programming block, followed by BS Nippon Television.",
        "source_url": "https://myanimelist.net/news/74961958",
    })
    results.append(check(
        "msg18-shape-body-not-premiered",
        "body_season_premiered" in (post.get("template_ids") or []),
        False))

    print(f"{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
