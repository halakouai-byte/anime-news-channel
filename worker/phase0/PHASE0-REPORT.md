# گزارش اندازه‌گیری فاز ۰ — آشکارساز اخبار انیمه (Worker)

تاریخ: شنبه ۲۱ نوامبر ۲۰۲۶، ~۰۲:۰۰–۰۲:۲۰ تهران (۲۲:۳۰–۲۲:۵۰ UTC، ‏۲۰ نوامبر)
Worker زنده: https://anime-news-detector.halakouai-byte.workers.dev
نسخه نهایی دیپلوی‌شده: `2a8d7ac4-9386-4099-9a02-637daa71af5d`
KV: ‏NEWS_KV ‏(`ffbba7902cdb416795ce2ff27be03481`) — تاییدشده با API مستقیم

همه عددهای زیر از تست واقعی‌اند، نه حدس. ابزارها در همین پوشه‌اند
(`fetch-feeds.mjs`، `parse-bench.mjs`، `poll-ann-mal.mjs`، `poll-ann-mal.log`، `tail.log`).

## ۱. CPU — آیا پارس ۵ تا ۱۰ فید + dedupe در ۱۰ms جا می‌شود؟

**پاسخ کوتاه: بله — ولی فقط با پارس افزایشی. نسخه اول (پارس کامل) روی مرز بود.**

| اندازه‌گیری | عدد |
|---|---|
| پارس کامل ۸ فید در Node V8 ‏(۱٫۸۶ MB، ‏۳۰۰ آیتم) | **۷٫۰۲ms** + هش **۱٫۷۳ms** = ‏**۸٫۷۵ms** |
| تیک عادی نسخه اول در analytics واقعی Cloudflare ‏(۵ فید) | **۷٫۷۴ms** |
| تیک عادی نسخه اول ‏(۶ فید، شامل Anime Corner) | **۱۰٫۷۹ms** — بالای سقف |
| تیک seed نسخه اول ‏(~۳۸ کاندید + KV + SHA-256) | **۳۳٫۳۱ms** و **۳۵٫۹۲ms** |
| **تیک عادی نسخه نهایی (پارس افزایشی) — fetch** | **۲٫۵۹ تا ۴٫۹۳ms** |
| **تیک عادی نسخه نهایی — cron در `wrangler tail`** | **cpuTime ‏۰ تا ۵ms** (‏wallTime ~۲ ثانیه، outcome ok) |

**راه‌حل سبک‌سازی (انجام‌شده، با مدرک):** پارس افزایشی — چون آیتم‌ها
newest-first هستند، اسکن در اولین آیتم قدیمی‌تر از highwater متوقف
می‌شود؛ در تیک عادی ۰ تا ۲ آیتم در هر فید پارس می‌شود، نه ۴۰/۱۵۰.
نتیجه: ~۲ تا ۳ برابر کاهش CPU. برش ۲۰۰KB فید هم سر جایش هست.
تیک seed یک‌باره ۳۳–۳۶ms است ولی بی‌خطر (تکراری‌پذیر؛ اگر کشته شود
تیک بعدی ادامه می‌دهد). متر داخلی `performance.now()` حذف شد چون
۰٫۰۰ نشان می‌داد در حالی که analytics ‏۷٫۷ms می‌گفت (دانه‌بندی تایمر)؛
عدد مرجع فقط Cloudflare Analytics ‏(`workersInvocationsAdaptive.cpuTime`)
و `wrangler tail` است.

## ۲. واکنش ANN/MAL به polling هر ۱ دقیقه

۷ بار poll در ۶ دقیقه (۲۲:۳۳ تا ۲۲:۳۹ UTC، ‏۲۸ درخواست):

| مورد | عدد |
|---|---|
| پاسخ‌ها | هر ۱۴ درخواست ANN و MAL ‏**۲۰۰** |
| ‏۴۲۹ / rate limit | **۰** — هیچ `Retry-After` هم نیامد |
| تغییر guid در ANN | در poll#4 (‏۲۲:۳۷:۴۴) — یک آیتم تازه رسید |
| ناهنجاری | poll#5: فید MAL فقط **۳٬۰۰۹ بایت** برگرداند (به‌جای ~۱۹٬۷۷۷) بدون آیتم؛ poll#6 به حالت عادی برگشت. گذرا؛ Worker چنین پاسخی را خطا log می‌کند و crash نمی‌کند. |

## ۳. تاخیر سایت → RSS (ANN و MAL)

- آیتم تازه ANN با `pubDate` ‏۲۲:۰۰ UTC در poll ‏۲۲:۳۶:۴۳ هنوز در فید
  نبود و در poll ‏۲۲:۳۷:۴۴ ظاهر شد → **تاخیر pubDate تا ظاهرشدن در
  فید ≈ ۳۶ تا ۳۷ دقیقه** برای آن آیتم.
- همان آیتم در تیک Worker ‏۲۲:۳۸:۵۵ (~۱ دقیقه پس از ظاهرشدن در فید)
  به‌عنوان fresh=1 تشخیص داده و در KV ثبت شد. پس زنجیره «فید → تشخیص»
  ~۱ دقیقه است؛ گلوگاه تاخیر، خودِ فید ANN است.
- قدمت تازه‌ترین آیتم‌ها در fetch ‏۲۲:۳۲ UTC: ‏ANN ‏۱۵۵ دقیقه، MAL ‏۲۸۹
  دقیقه، Siliconera ‏۳۳ دقیقه — این آهنگ انتشار خود سایت‌هاست، نه تاخیر فید.

## ۴. scope دقیق PAT برای repository_dispatch

**تاییدشده از مستندات رسمی GitHub** («Permissions required for
fine-grained personal access tokens»): ‏`POST /repos/{owner}/{repo}/dispatches`
زیر مجوز **Contents** با دسترسی **write** است. انتظار اولیه
«Actions: Read and write» نادرست است — Actions: write مال endpoint
جداگانه `workflow_dispatch` است.

**تست زنده (۲۱ نوامبر ۲۰۲۶، ۰۲:۰۸ تهران):** PAT فعلی
(`anime-news-dispatch` با Actions R+W + Contents R-only) →
**HTTP ‏۴۰۳** ‏`{"message":"Resource not accessible by personal access token",...}`.
**رفع دقیق:** در `github.com/settings/tokens` همان PAT را ویرایش کنید
و **Contents را به Read and write** تغییر دهید؛ پس از آن
`/tick?dispatch_test=1` باید **۲۰۴** برگرداند. تا آن زمان Worker خبرها
را در KV ثبت می‌کند و dispatch با ۴۰۳ log می‌شود — هیچ خبری گم نمی‌شود.

## ۵. یافته‌های دیگر تست خشک (dry run)

- **Seed تایید شد:** تیک اول ۳۹ آیتم ANN + تیک دوم ۳۸ آیتم
  MAL/AnimeTV/Siliconera را دیده‌شده علامت زد و هیچ dispatchای نفرستاد.
- **تشخیص تازه تایید شد:** «North American Anime, Manga Releases,
  November 15-21» ‏(ANN) در تیک ۲۲:۳۸:۵۵ ‏fresh=1 شد و در KV ثبت شد
  (`item:e08ba92d…`)؛ dispatch آن با ۴۰۳ رد شد (مشکل PAT).
- **تیک‌های cron واقعی** (`wrangler tail`، نسخه نهایی، ۳ تیک متوالی):
  `fresh=0` و `dispatch=skipped (no fresh items)` — وقتی خبری نیست
  dispatch نمی‌رود. نمونه:
  `tick cron due=ann,fandompost,mal,animetv,siliconera fetched=4 fresh=0 excluded=0 dup=0 dispatch=skipped (no fresh items) errors=1`
- **Fandom Post از داخل Worker ‏۴۰۳ می‌دهد** (از همین VM با همان
  User-Agent ‏۲۰۰). علت احتمالی: بلاک IPهای خروجی Cloudflare.
  Worker ادامه می‌دهد؛ sweeper ‏Actions پشتیبان است.
- **KV تایید شد** (API مستقیم): ‏`hw:ann=2026-11-20T22:00:00Z`،
  ‏`meta:last_tick`، ‏`item:`/`seen:`/`story:` موجودند. توجه:
  `wrangler kv key list/get` در این محیط خالی نشان می‌داد در حالی که
  API مستقیم کلیدها را برمی‌گرداند — وارسی KV با API مستقیم یا داشبورد.
- **بدون dispatch واقعی به کانال:** هیچ پستی به کانال عمومی نرفته است؛
  dispatch واقعی هم (به‌خاطر ۴۰۳) هرگز نرسید. پس از اصلاح PAT، اولین
  dispatch واقعی با event_type ‏`news-detected` خواهد رفت.
