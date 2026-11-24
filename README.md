# اخبار دنیای انیمه — کانال تلگرام فارسی «انیمه‌خبر»

کانال خبری فارسی دنیای انیمه (`@animekhabarfa`) — فول‌اتوماسیون با **GitHub + Cloudflare**،
بدون AI در runtime، بدون سرور، بدون هزینه.

## چطور کار می‌کند (معماری هیبرید، نسخه ۲)

1. **Cloudflare Worker — آشکارساز** (`worker/`): هر ۱ دقیقه ۷ فید RSS تاییدشده را
   می‌خواند (Fandom Post به‌خاطر بلاک ۴۰۳ از ورکر حذف شد — نگاه کنید به `sources-v2.md` §۷)؛ خبر تازه را در KV ثبت می‌کند و فقط وقتی خبر تازه هست، با
   `repository_dispatch` ورک‌فلوی انتشار را بیدار می‌کند.
2. **GitHub Actions — منتشرکننده** (`.github/workflows/publish.yml`): بازنویسی فارسی
   قالبی (بدون LLM) + ۱۱ دروازه کیفی + کاور V3 ‏۱۰۸۰×۱۳۵۰ + `sendPhoto` به کانال؛
   بعد `state.json` (مرجع نهایی «منتشر شده/نشده») کامیت می‌شود.
3. **Sweeper** (`sweeper.yml`، هر ۱۵ دقیقه): پشتیبان — خبرهای جامانده را منتشر می‌کند.

جزئیات کامل: [`ARCHITECTURE.md`](ARCHITECTURE.md) · قانون فیلتر: [`filter-v2.md`](filter-v2.md) ·
منابع: [`sources-v2.md`](sources-v2.md) · راهنمای همه عوامل: [`AGENTS.md`](AGENTS.md).

## قانون طلایی فیلتر (v2)

هر خبر تازه واقعی از یک منبع معتمد، همان موقع منتشر می‌شود — مگر در فهرست حذف
(۱۷ دسته) باشد، تکراری باشد، یا به HOLD انسانی برود. **سقف روزانه نیست**
(سقف ۴ پست در روز و آستانه انتشار ۶۰ از v1 حذف شده‌اند). امتیاز ۰–۱۰۰ فقط
**ترتیب صف** است.

## تصمیم‌های قفل‌شده کاربر

- **سکوت شبانه نیست** — انتشار ۲۴/۷، شامل ۰۲:۰۰ تا ۰۷:۰۰ تهران؛ کانال هیچ‌وقت خاموش نیست.
- **فاصله حداقل ۱۵ دقیقه بین پست‌ها** (هدف ۳۰ تا ۶۰)؛ breaking ‏۵ دقیقه.
- **ترمز اضطراری** (سقف روزانه نیست): فقط وقتی هر دو شرط برقرار باشند — بیش از ۲۵ پست
  از ۰۰:۰۰ تهران + صف هنوز بیش از ۱۰ آیتم واجد شرایط دارد. آن‌وقت فقط breaking یا
  اولویت ۷۵+ فوری می‌روند، بقیه با فاصله ۳۰ دقیقه‌ای منتظر می‌مانند.

## منابع (۷ فید تاییدشده با fetch زنده)

| منبع | Tier | RSS |
|---|---|---|
| Anime News Network | ۱ | `animenewsnetwork.com/news/rss.xml` |
| MyAnimeList News | ۱ | `myanimelist.net/rss/news.xml` |
| Anime Corner | ۱ | `animecorner.me/feed/` |
| AnimeTV | ۱ | `animetv-jp.net/feed/` |
| The Fandom Post | ۱ | `fandompost.com/feed/` |
| Siliconera (فقط آیتم انیمه) | ۱ | `siliconera.com/feed/` |
| Honey's Anime | ۲ | `honeysanime.com/feed/` |
| Anime Herald | ۲ | `animeherald.com/feed/` |

## Secrets (فقط نام — مقدار هرگز در کد/لاگ نیست)

| Secret | کجا | کاربرد |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | GitHub Secrets | ارسال پست از Actions |
| `TELEGRAM_CHAT_ID` | GitHub Secrets | شناسه کانال `@animekhabarfa` |
| `GITHUB_DISPATCH_PAT` | Cloudflare Secrets | PAT ‏«anime-news-dispatch» برای `repository_dispatch` از Worker (انقضا: ۲۱ نوامبر ۲۰۲۷ — چرخش پیش از آن در `docs/runbook.md`) |

توکن‌ها پیش از هر لاگ redact می‌شوند (`scripts/common.py`)؛ لاگ ریپوی عمومی برای
همه قابل دیدن است. اسکن سکرت (gitleaks پین‌شده ‏v8.28.0 با تایید SHA256) روی هر
push/PR و هفتگی اجرا می‌شود (`.github/workflows/secret-scan.yml`).

## اجرای محلی (تست — هیچ پستی فرستاده نمی‌شود)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 scripts/dry_run.py        # fetch واقعی + بازنویسی + کاور، بدون sendPhoto
python3 -m py_compile scripts/*.py
```

خروجی dry run در `dry-run-output/` می‌آید: `report.md` (زمان‌سنجی هر مرحله +
دلیل‌های رد) + `captions.json` + `covers/*.jpg`.

## ساختار ریپو

```
scripts/   fetch.py (RSS+فیلتر+dedupe) · classify.py (دسته‌بندی) · rewrite.py (بازنویسی)
           cover.py (کاور V3) · publish.py (sendPhoto) · common.py (redaction/state/شمسی)
           dry_run.py (اجرای خشک)
data/      queue.json · state.json (مرجع نهایی) · archive.jsonl · categories.json
           category-corrections.json · blocklist.json · stopwords.json
           templates-fa.json · phrases-fa.json · synonyms-fa.json · names-fa.json
           franchises.json (بانک‌های بازنویسی)
.github/workflows/  publish.yml · sweeper.yml · keepalive.yml · digest.yml (فاز ۴، غیرفعال)
                    secret-scan.yml (gitleaks)
docs/      setup.md · weekly-checklist.md · runbook.md · edge-cases.md
logs/      fetch-log.md · publish-log.md · dispatch-log.md · error-log.md · keepalive.md
```

## وضعیت زنده

> وضعیت زنده (به‌روز، ۲۴ نوامبر ۲۰۲۶): **۵۵ پست واقعی** (پیام‌های ۶ تا ۶۲،
> منهای فانتوم‌های ۱۵/۱۶)؛ آخرین انتشار ۰۲:۳۸ UTC همان روز. صف: ۰ QUEUED،
> ۳۳ HOLD، ۵۴ STALE.

## مجوز

MIT — [`LICENSE`](LICENSE).
