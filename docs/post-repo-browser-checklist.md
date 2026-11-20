# چک‌لیست بعد از ساخته‌شدن ریپو — برای مدیر (مرورگر)

| مورد | مقدار |
|---|---|
| تاریخ | شنبه ۲۱ نوامبر ۲۰۲۶ (بامداد تهران) |
| ریپو | https://github.com/halakouai-byte/anime-news-channel — عمومی، خالی (size 0)، شاخه `main`، ساخته‌شده 2026-11-20T22:30:05Z |
| وضعیت | ریپو **ساخته شده است**، پس همه موارد زیر حالا قابل انجام‌اند. هیچ‌کدام با API/کد انجام نمی‌شوند — همه از مرورگر و با هماهنگی مدیر. |

## ۱. محافظت نشتی — GitHub native (اول بررسی، بعد فعال‌سازی)

طبق ممیزی ۲۱ نوامبر، Secret scanning + Push protection + CodeQL روی ۳ ریپوی موجود از قبل روشن بودند — پس روی ریپوی جدید هم ممکن است به‌صورت پیش‌فرض روشن باشند. **اول بررسی کن، بعد فعال کن:**

1. باز کن: `https://github.com/halakouai-byte/anime-news-channel/settings/code-security`
2. چک کن هر سه مورد روشن‌اند یا نه:
   - [ ] **Secret scanning** — روشن است؟ اگر نه، روشن کن (Alerts + Push protection).
   - [ ] **Push protection** — روشن است؟ اگر نه، روشن کن (جلوی push توکن را می‌گیرد، نه فقط هشدار بعدش).
   - [ ] **CodeQL analysis** — روشن است؟ اگر نه، با تنظیم پیش‌فرض (Default setup) روشن کن.
3. اگر هر سه از قبل روشن بودند، فقط همین‌جا تیک بزن و تاریخ بررسی را ثبت کن — نیازی به تغییر نیست.

## ۲. Ruleset سبک — فقط ضد force-push/delete

1. باز کن: `https://github.com/halakouai-byte/anime-news-channel/rules`
2. یک ruleset تازه بساز (نام پیشنهادی: `protect-main`):
   - هدف: شاخه `main` (فقط همین شاخه).
   - [ ] Block force pushes — روشن.
   - [ ] Block deletions — روشن.
   - بقیه قوانین (required reviews، required status checks) **خاموش** بمانند — مالک تنها است و اتوماسیون خودش کامیت می‌کند؛ review اجباری چرخه انتشار را قفل می‌کند.
3. ذخیره کن و مطمئن شو ruleset در وضعیت Active است.

## ۳. Secrets گیت‌هاب — بررسی حضور (نه ساخت مقدار در چت)

1. باز کن: `https://github.com/halakouai-byte/anime-news-channel/settings/secrets/actions`
2. چک کن این دو Secret وجود دارند (فقط نام — مقدار هرگز در چت/فایل نمی‌آید):
   - [ ] `TELEGRAM_BOT_TOKEN`
   - [ ] `TELEGRAM_CHAT_ID`
3. اگر نیستند، مقدارشان را فقط مالک از داشبورد وارد می‌کند (مقدار از کانال امن مالک می‌آید، نه از Muse).
4. توجه: `GITHUB_DISPATCH_PAT` در گیت‌هاب نیست و نباید باشد — آن Secret در Cloudflare است (ساخته و ذخیره شده، ۲۱ نوامبر ~۰۲:۰۵ تهران؛ انقضا ۲۱ نوامبر ۲۰۲۷).

## ۴. تایید CI محافظت — اولین push

1. بعد از اولین push (که `secret-scan.yml` را می‌برد)، باز کن:
   `https://github.com/halakouai-byte/anime-news-channel/actions`
2. چک کن ورک‌فلوی **Secret scan** سبز شده باشد (gitleaks با SHA256 تاییدشده، ۰ finding).
3. اگر قرمز شد: لاگ را بخوان، finding را گزارش بده، و رفعش کن — هرگز با پاک‌کردن بی‌سروصدا.

## ۵. مواردی که انجام‌شده‌اند و نیازی به مرورگر ندارند (فقط برای ثبت)

- [x] ریپو ساخته شده (عمومی، خالی، `main`) — ۲۱ نوامبر ~۰۲:۰۵ تهران.
- [x] PAT «anime-news-dispatch» ساخته شده (فقط همین ریپو؛ Actions: Read and write + Contents: Read-only + Metadata: Read-only؛ انقضا یکشنبه ۲۱ نوامبر ۲۰۲۷).
- [x] Worker «anime-news-detector» دیپلوی شده (کد placeholder) — https://anime-news-detector.halakouai-byte.workers.dev — کرون هر ۱ دقیقه فعال، نسخه `a060bfe7`.
- [x] `GITHUB_DISPATCH_PAT` به‌عنوان Cloudflare Worker Secret ذخیره و با `wrangler secret list` تایید شده.
- [ ] ریپو را دوباره نساز؛ Worker را دوباره نساز (placeholder با کد واقعی جایگزین می‌شود، نه بازسازی).

## ۶. تصمیم‌های قفل‌شده کاربر (برای ثبت در چک‌لیست — تکرار نشوند)

- **بدون سکوت شبانه:** انتشار ۲۴/۷، شامل ۰۲:۰۰ تا ۰۷:۰۰ تهران (تصمیم قطعی ۲۱ نوامبر ~۰۱:۵۸ تهران).
- **PAT تایید شده** و ساخته شده (ردیف ۵).
- **فاصله حداقل ۱۵ دقیقه بین پست‌ها می‌ماند.**
