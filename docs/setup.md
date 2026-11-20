# راه‌اندازی — کانال «اخبار دنیای انیمه»

قدم‌به‌قدم، از صفر تا انتشار آزمایشی. هیچ توکنی در هیچ مرحله‌ای در فایل یا چت
نوشته نمی‌شود؛ مقدارها فقط در صفحه Secrets گیت‌هاب / Cloudflare وارد می‌شوند.

## ۰. پیش‌نیازها

- ریپوی عمومی گیت‌هاب: `halakouai-byte/anime-news-channel` (شاخه `main`) — ساخته شده.
- ربات تلگرام `@animekhabarbot` — ادمین کانال `@animekhabarfa` با دسترسی
  `can_post_messages` و `can_edit_messages` (تایید شده ۲۰ نوامبر ۲۰۲۶).
- حساب Cloudflare با Workers Free + KV Free.

## ۱. GitHub Secrets (از مسیر مرورگر، توسط مدیر)

Settings → Secrets and variables → Actions → New repository secret:

| نام | مقدار |
|---|---|
| `TELEGRAM_BOT_TOKEN` | توکن ربات از BotFather |
| `TELEGRAM_CHAT_ID` | شناسه عددی کانال (مثلاً `-1004460838978`) |

مقدارها را هیچ‌وقت در کد، لاگ، یا چت ننویسید. ورک‌فلوها فقط با نام می‌خوانندشان.

## ۲. Cloudflare Worker + PAT (انجام‌شده)

- PAT ‏«anime-news-dispatch» ساخته شده (فقط همین ریپو — Actions: Read and write +
  Contents: Read-only + Metadata: Read-only؛ انقضا یکشنبه ۲۱ نوامبر ۲۰۲۷).
- به‌عنوان Cloudflare Worker Secret با نام `GITHUB_DISPATCH_PAT` ذخیره شده است.
- Worker ‏«anime-news-detector» دیپلوی شده (فعلاً کد placeholder؛ جایگزینی با
  آشکارساز واقعی با هماهنگ‌کننده است)، کرون هر ۱ دقیقه فعال.
- چرخش PAT پیش از ۲۱ نوامبر ۲۰۲۷ — نگاه کنید به `docs/runbook.md`.

## ۳. تست محلی (پیش از هر انتشار واقعی)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/dry_run.py
```

خروجی در `dry-run-output/report.md`: چند خبر واقعی پردازش شد، چندتا با چه کد
دلیلی رد شد، زمان‌سنجی هر مرحله. اگر dry run خطا داد، اول `logs/error-log.md`
و خروجی را بخوانید؛ هیچ‌وقت برای «تست» به کانال عمومی پست نفرستید.

## ۴. انتشار دستی آزمایشی

Actions → Publish → Run workflow (ورودی `dry: true` برای تست بدون ارسال).
بعد از تایید مدیر، همان ورک‌فلو با `dry: false` یک پست واقعی می‌فرستد.

## ۵. بررسی بعد از اولین انتشار

- `data/state.json`: `posted_message_ids` و `last_publish_utc` به‌روز شده باشد.
- `logs/publish-log.md`: خط انتشار با `message_id` و تاخیر «فید → کانال».
- کانال: پست با کاور V3 ‏۱۰۸۰×۱۳۵۰، منبع ذکر شده، تیتر ≤ ۷۰ کاراکتر.

## ۶. تصمیم‌های قفل‌شده (در کد رعایت شده‌اند)

- سکوت شبانه نیست — انتشار ۲۴/۷، شامل ۰۲:۰۰ تا ۰۷:۰۰ تهران.
- فاصله حداقل ۱۵ دقیقه بین پست‌ها (breaking ‏۵ دقیقه).
- ترمز اضطراری فقط با دو شرط هم‌زمان (۲۵+ پست در روز + صف بیش از ۱۰).
