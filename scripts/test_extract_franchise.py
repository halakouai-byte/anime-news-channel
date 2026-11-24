"""تست استخراج فرنچایز دو مرحله‌ای — نقد ۳ (پیام ۸ زنده).

قاعده: ۱) نام انیمه/مانگا در تیتر؛ ۲) همان‌ها در خلاصه؛
۳) استودیو/پلتفرم/شخص فقط وقتی هیچ نام انیمه‌ای نیست (new_name=True).
پیام ۸: تیتر «New Oishinbo TV Anime...» بود ولی کد قدیم
«Shin-Ei Animation» (۱۷ حرف، در خلاصه) را بر «Oishinbo» (۸ حرف، در
تیتر) ترجیح می‌داد — چون «Oishinbo» در بانک هم بود و باز باخت.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rewrite import detect_event, extract_franchise, load_banks  # noqa: E402

BANKS = load_banks()

OISHINBO_TITLE = "New Oishinbo TV Anime Set to Premiere on January 4, 2027"
OISHINBO_SUMMARY = (
    "The TV anime Oishinbo, based on the works of Tetsu Kariya and Akira "
    "Hanasaki, will begin airing on January 4, 2027. The new cast members, "
    "main PV, and key visual have also been revealed. The series is produced "
    "by Shin-Ei Animation and continues the story of the original anime, "
    "35 years after the previous series ended."
)


def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        print(f"  got:  {got}")
        print(f"  want: {want}")
    return ok


def main() -> int:
    results = []

    # ۱) پیام ۸ (متن واقعی AnimeTV): نام انیمه در تیتر، استودیو در خلاصه
    results.append(check(
        "oishinbo-title-beats-studio-in-summary",
        extract_franchise(OISHINBO_TITLE, OISHINBO_SUMMARY, BANKS),
        ("Oishinbo", "اویشینبو", False)))

    # ۲) پیام ۲۰: نام کامل ژاپنی در تیتر
    results.append(check(
        "tensei-full-japanese-title",
        extract_franchise(
            "Tensei Kizoku, Kantei Skill de Nariagaru 3rd Season Unveils New Cast",
            "The official website for Tensei Kizoku, Kantei Skill de Nariagaru "
            "3rd Season revealed new cast members on Friday. The season will "
            "premiere in 2027.", BANKS),
        ("Tensei Kizoku, Kantei Skill de Nariagaru", "تنسی کیزوکو", False)))

    # ۳) نام انگلیسی اثر (ANN): کلید «As a Reincarnated Aristocrat»
    results.append(check(
        "tensei-english-title",
        extract_franchise(
            "'As a Reincarnated Aristocrat, I'll Use My Appraisal Skill' "
            "Season 3 Announced",
            "The third season of As a Reincarnated Aristocrat, I'll Use My "
            "Appraisal Skill has been announced for 2027.", BANKS),
        ("As a Reincarnated Aristocrat", "تنسی کیزوکو", False)))

    # ۴) نام انیمه در خلاصه، استودیو در تیتر: خلاصه می‌برد
    results.append(check(
        "anime-in-summary-beats-studio-in-title",
        extract_franchise(
            "ufotable Announces New Project Details",
            "The new anime Frieren: Beyond Journey's End will return with a "
            "second season in 2027, the official website announced.",
            BANKS),
        ("Frieren: Beyond Journey's End", "فریرن؛ آن‌سوی پایان سفر", False)))

    # ۵) فقط استودیو (نام انیمه در بانک نیست): fallback با new_name=True
    results.append(check(
        "studio-only-fallback-is-new-name",
        extract_franchise(
            "New Original Anime Announced for 2027",
            "The original anime, produced by ufotable, will premiere in "
            "2027. More details will be revealed soon.", BANKS),
        ("ufotable", "یوفوتیبل", True)))

    # ۶) رگرسیون Hidan (پیام ۲۷): طولانی‌ترین نام انیمه در تیتر
    results.append(check(
        "hidan-still-correct",
        extract_franchise(
            "Hidan no Aria (Aria the Scarlet Ammo) Gets New Anime Project",
            "The Aria the Scarlet Ammo anime project was announced on "
            "Friday.", BANKS),
        ("Aria the Scarlet Ammo", "آریا سلاح سرخ", False)))

    # ۷) عبارت گیومه‌دار وقتی هیچ نامی نیست
    results.append(check(
        "quoted-fallback",
        extract_franchise(
            "'Some Brand New Anime' Gets TV Adaptation",
            "A TV anime adaptation of the manga was announced.", BANKS),
        ("Some Brand New Anime", "Some Brand New Anime", True)))

    # ۸) پیام ۳۱ (نقد ۴): تیتر Zatsuyou دارد؛ خلاصه در اعتبارات بازیگران
    # «Bleach» را ذکر می‌کند — باید Zatsuyou بگیرد، نه Bleach
    results.append(check(
        "msg31-zatsuyou-not-bleach",
        extract_franchise(
            "'Zatsuyou Fuyo Jutsushi ga Jibun no Saikyou ni Kizuku made' "
            "Announces Additional Cast",
            "The official website for the television anime of Zatsuyou Fuyo "
            "Jutsushi ga Jibun no Saikyou ni Kizuku made revealed additional "
            "cast members on Sunday. Melis: Natsumi Takamori (Bleach: "
            "Sennen Kessen-hen).", BANKS),
        ("Zatsuyou Fuyo Jutsushi ga Jibun no Saikyou ni Kizuku made",
         "زاتسویو فویو جوتسوشی", False)))

    # ۹) جمله اول خلاصه می‌برد، نه ذکرِ گذرای بلندتر در جمله بعد (نقد ۴)
    # کد قدیم (خلاصه کامل) طولانی‌ترین نام را می‌گرفت: «Frieren» (۲۹ حرف)
    # بر «Oishinbo» (۸ حرف) — با اینکه Frieren فقط در اعتبارات آمده بود.
    results.append(check(
        "summary-lead-beats-passing-mention",
        extract_franchise(
            "Additional Cast Members Revealed for Upcoming Anime",
            "The official website for the television anime of Oishinbo "
            "revealed additional cast members. Melis: Natsumi Takamori "
            "(Frieren: Beyond Journey's End) joins the cast.", BANKS),
        ("Oishinbo", "اویشینبو", False)))

    # ۱۰) نام فقط داخل پرانتز در جمله بعد: نباید گرفته شود (نقد ۴)
    results.append(check(
        "parenthetical-only-is-not-a-match",
        extract_franchise(
            "Additional Cast Members Revealed for Upcoming Anime",
            "The new cast members were announced on Friday. The theme song "
            "is performed by the artist (Bleach: Sennen Kessen-hen).",
            BANKS),
        (None, None, True)))

    # ۱۱) پیام ۶۶ (۲۴ نوامبر ۲۰۲۶): مقاله فهرستی اسکار — تیتر و جمله اول
    # خلاصه هر دو فهرست‌اند («X, Y, Z, More Anime ...»)؛ موضوع واحد
    # ندارد و نباید یک نام (Gundam) از فهرست برداشته شود.
    results.append(check(
        "msg66-roundup-no-franchise",
        extract_franchise(
            "All You Need Is Kill, Kaguya!, Grotesqqque, More Anime "
            "Confirmed Eligible for Oscars",
            "Jinsei , Last Blossom , 2nd Gundam Hathaway film, Ribbon "
            "Hero, Super Mario Galaxy Movie, Avatar Aang also eligible",
            BANKS),
        (None, None, True)))

    # ۱۲) همان مقاله: رویداد «award» است، نه «announcement» — وگرنه کپشن
    # «انیمه تازه Gundam» می‌ساخت (وارونه‌سازی رویداد، مثل پیام ۶).
    results.append(check(
        "msg66-oscars-event-award",
        detect_event(
            "All You Need Is Kill, Kaguya!, Grotesqqque, More Anime "
            "Confirmed Eligible for Oscars",
            "Jinsei , Last Blossom , 2nd Gundam Hathaway film, Ribbon "
            "Hero, Super Mario Galaxy Movie, Avatar Aang also eligible"),
        "award"))

    # ۱۳) مقاله تک‌اثرِ اسکار فهرست نیست — نگهبان فهرست نباید آن را
    # بگیرد: Gundam برگردد و رویداد «award» باشد.
    results.append(check(
        "msg66-single-franchise-oscars",
        (extract_franchise(
            "Mobile Suit Gundam Hathaway Confirmed Eligible for Oscars",
            "The second Gundam Hathaway film has been confirmed eligible "
            "for Best Animated Feature at the Academy Awards.", BANKS)[0],
         detect_event(
            "Mobile Suit Gundam Hathaway Confirmed Eligible for Oscars",
            "The second Gundam Hathaway film has been confirmed eligible "
            "for Best Animated Feature at the Academy Awards.")),
        ("Mobile Suit Gundam", "award")))

    print(f"{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
