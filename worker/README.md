# آشکارساز اخبار انیمه — Cloudflare Worker ‏(anime-news-detector)

آشکارساز (detector) کانال تلگرام «اخبار دنیای انیمه» (`@animekhabarfa`) —
بخش ۱ از معماری هیبرید نسخه ۲ (`ARCHITECTURE.md` §۶).

**آدرس زنده:** https://anime-news-detector.halakouai-byte.workers.dev
**ریپوی هدف dispatch:** https://github.com/halakouai-byte/anime-news-channel

## این Worker چه می‌کند

هر ۱ دقیقه (Cron Trigger `* * * * *`، **۲۴/۷ بدون پنجره سکوت شبانه** —
تصمیم قطعی کاربر، قفل‌شده ۲۱ نوامبر ۲۰۲۶: خبرها حتی ۰۲:۰۰ تا ۰۷:۰۰ تهران
هم همان موقع شناسایی می‌شوند):

1. فیدهای RSS سررسیده را می‌خواند (۷ منبع در Worker + ‏Fandom Post فقط در
   sweeper — `sources-v2.md`):
   ANN هر ۱ دقیقه؛ MAL ،AnimeTV و Siliconera هر ۲ دقیقه؛
   Anime Corner هر ۵ دقیقه؛ Honey's Anime و Anime Herald روزی ۱ بار
   (ساعت ۰۰:۳۰ UTC).
2. آیتم تازه را تشخیص می‌دهد (تازه‌تر از highwater همان منبع و
   `pubDate` کمتر از ۴۸ ساعت پیش).
3. سه لایه dedupe را روی KV چک می‌کند: (۱) هش SHA-256 لینک نرمال‌شده،
   (۲) story key ‏(فرنچایز + نوع رویداد + بازه ۴۸ ساعته)،
   (۳) شباهت عنوان Jaccard ‏≥ ۰٫۸۵ در پنجره ۷ روزه.
4. آیتم واجد شرایط را در KV ثبت می‌کند (یک کلید جدا برای هر آیتم،
   append-only، TTL ‏۳۰ روز).
5. **فقط وقتی خبر تازه هست** یک `repository_dispatch`
   (event_type ‏`news-detected`) به GitHub Actions می‌فرستد. وقتی خبری
   نیست، نه dispatch می‌رود و نه KV نوشته می‌شود.

بازنویسی فارسی، کاور V3 و ارسال تلگرام کار این Worker نیست — کار
GitHub Actions (منتشرکننده) است که با dispatch بیدار می‌شود.

## راه‌اندازی اول (cold start)

اولین تیک پس از دیپلوی، **seed** می‌کند: همه آیتم‌های فعلی فیدها را
«دیده‌شده» علامت می‌زند و **هیچ dispatchای نمی‌فرستد** — در غیر این
صورت ~۳۰۰ آیتم قدیمی یک‌باره وارد صف می‌شدند. فقط خبرهایی که *بعد*
از seed برسند منتشر می‌شوند.

## Secret ها (هیچ توکنی در کد نیست)

فقط یک Secret لازم است:

| Secret | کاربرد |
|---|---|
| `GITHUB_DISPATCH_PAT` | توکن fine-grained گیت‌هاب برای `repository_dispatch` |

دستور دقیق (مقدار PAT را فقط از طریق stdin بدهید — هرگز در فایل یا چت ننویسید):

```bash
wrangler secret put GITHUB_DISPATCH_PAT
# بعد مقدار PAT را paste کنید و Enter بزنید
```

**scope دقیق PAT** (تاییدشده از مستندات رسمی GitHub،
«Permissions required for fine-grained personal access tokens» —
`POST /repos/{owner}/{repo}/dispatches` زیر مجوز **Contents** با
دسترسی **write** است؛ نه Actions):

- Repository access: ‏**Only select repositories** ← ‏`halakouai-byte/anime-news-channel`
- Repository permissions: **Contents: Read and write** ‏(+ **Metadata: Read-only** که خودکار انتخاب می‌شود)
- انقضا: حداکثر ۱ سال؛ پیش از انقضا بچرخانید (rotation) و Secret را به‌روز کنید.

> ⚠️ نکته تست‌شده: PAT فعلی (`anime-news-dispatch`) با
> **Actions: Read and write + Contents: Read-only** ساخته شده است —
> یعنی برعکس جدول رسمی مستندات. تست زنده dispatch در فاز ۰ نشان می‌دهد
> آیا همین ترکیب کار می‌کند یا نه؛ اگر GitHub ‏`403` برگرداند،
> Contents را به **Read and write** تغییر دهید (Actions به‌تنهایی
> طبق مستندات رسمی برای `repository_dispatch` کافی نیست؛
> `workflow_dispatch` جداگانه است و Actions: write می‌خواهد).

**اگر Secret نباشد:** Worker کاملاً graceful عمل می‌کند — detect و log
می‌کند ولی dispatch نمی‌فرستد (`dispatch_status: "skipped (no secret)"`).
در این حالت sweeper ‏۱۵ دقیقه‌ای Actions پشتیبان است.

## دیپلوی

```bash
cd worker
npm i -g wrangler          # اگر نصب نیست (نسخه تست‌شده: 4.166.0)
wrangler kv namespace create NEWS_KV   # فقط بار اول؛ id را در wrangler.toml بگذارید
wrangler secret put GITHUB_DISPATCH_PAT # فقط بار اول (یا هنگام rotation)
wrangler deploy
```

نکته‌ها:

- `compatibility_date` در `wrangler.toml` باید **۲۰۲۶-۱۱-۲۰** بماند؛
  تاریخ ۲۰۲۶-۱۱-۲۱ از نظر ساعت UTC سرور Cloudflare «آینده» است و
  دیپلوی با خطای `10021` رد می‌شود.
- در محیط غیرتعاملی، wrangler به `CLOUDFLARE_API_TOKEN` نیاز دارد؛
  تیم prompt-pack با surrogate همین credential کار می‌کند
  (`~/workspace/prompt-pack/deploy-cloudflare.py` را ببینید).
- دیپلوی Secret ها را پاک نمی‌کند؛ ولی پس از هر دیپلوی با
  `wrangler secret list` حضور `GITHUB_DISPATCH_PAT` را چک کنید.

## تست خشک (dry run) — بدون هیچ پستی به کانال

```bash
# وضعیت + آخرین تیک (بدون fetch فید، بدون KV write)
curl https://anime-news-detector.halakouai-byte.workers.dev/

# اجرای دستی یک تیک تشخیص (مثل cron؛ اگر خبر تازه باشد dispatch واقعی می‌رود)
curl https://anime-news-detector.halakouai-byte.workers.dev/tick

# تست زنده endpoint dispatch بدون خبر تازه (event_type: detector-ping)
curl "https://anime-news-detector.halakouai-byte.workers.dev/tick?dispatch_test=1"
```

لاگ‌های زنده:

```bash
wrangler tail   # هر تیک یک خط: fresh / excluded / dup / dispatch
```

هر تیک این را log می‌کند:

```
tick cron due=ann,fandompost,mal,animetv,siliconera fetched=4 fresh=0 excluded=0 dup=0 dispatch=skipped (no fresh items) errors=1
```

(نمونه واقعی از `wrangler tail`، ۲۱ نوامبر ۲۰۲۶، پیش از حذف Fandom Post از
polling؛ ‏errors=1 همان ۴۰۳ آن فید بود — پایین را ببینید.)

## نکته نظارتی — `last_tick` هر دقیقه به‌روز نمی‌شود (طراحی عمدی)

`GET /` مقدار `meta:last_tick` را از KV می‌خواند، ولی این کلید فقط در سه
حالت نوشته می‌شود: سر ساعت (`minuteOfDay % 60 === 0`)، وقتی خبر تازه
هست، یا وقتی خطایی هست. پس در زمان آرام (نه خبر تازه، نه خطا) `last_tick`
تا **~۱ ساعت** قدیمی می‌ماند — این به‌معنای توقف تیک‌ها نیست. پیش از حذف
Fandom Post هر تیک به‌خاطر ۴۰۳ خطا داشت و `last_tick` هر دقیقه به‌روز
می‌شد؛ بعد از حذف، تیک‌ها بی‌خطا شدند و فقط سر ساعت نوشته می‌شود (مثال
واقعی: ۰۴:۰۰:۳۰ → ۰۶:۰۰:۲۹ UTC، ۲۱ نوامبر ۲۰۲۶). برای اطمینان از سلامت
cron به‌جای `last_tick` از `wrangler tail` استفاده کنید (هر تیک یک خط
می‌دهد؛ تایید زنده ۰۶:۵۳ UTC همان روز: دو تیک پیاپی با errors=0). نوشتن
`last_tick` در هر تیک ممکن نیست: ۱٬۴۴۰ write در روز از سقف رایگان KV
(۱٬۰۰۰ write در روز) بیشتر است.

## محدودیت‌های Cloudflare Free — با عدد (فاز ۰، ۲۱ نوامبر ۲۰۲۶)

| محدودیت | مقدار | وضعیت ما (اندازه‌گیری واقعی، نه حدس) |
|---|---|---|
| CPU در Cron Trigger | ۱۰ میلی‌ثانیه | **نسخه اول** (پارس کامل فید در هر تیک): تیک عادی ۵ فید **۷٫۷ تا ۱۰٫۸ms** — روی مرز سقف. **نسخه فعلی** (پارس افزایشی: توقف در اولین آیتم قدیمی‌تر از highwater): تیک عادی **۲٫۶ تا ۴٫۹ms**، تیک‌های cron در `wrangler tail` ‏**۰ تا ۵ms** — با حاشیه امن زیر سقف. تیک seed (اولین بار، ~۳۸ کاندید): **۳۳ تا ۳۶ms** — بالای سقف ولی یک‌باره و بی‌خطر (seed تکراری‌پذیر است؛ اگر وسطش کشته شود تیک بعدی ادامه می‌دهد). منبع عددها: Cloudflare Analytics ‏(`workersInvocationsAdaptive.cpuTime`) + ‏`wrangler tail`. متر داخلی `performance.now()` حذف شد چون ۰٫۰۰ نشان می‌داد در حالی که analytics ‏۷٫۷ms می‌گفت (دانه‌بندی تایمر) — متر دروغ‌گو بدتر از نبودن متر است. |
| KV write | ۱٬۰۰۰ در روز | فقط on-change: تیک بدون خبر تازه **۰ write** (تاییدشده در لاگ تیک‌ها)؛ هر آیتم تازه ~۴ write؛ پیش‌بینی ۵۰ تا ۱۰۰ write در روز. |
| KV read | ۱۰۰٬۰۰۰ در روز | ~۸٬۶۰۰ read در روز (highwater هر فید سررسیده + کاندیدها). |
| Subrequest | ۵۰ در هر invocation | حداکثر ۸ فید + ۱ dispatch. |
| Workers requests | ۱۰۰٬۰۰۰ در روز | تیک ۱ دقیقه‌ای = ۱٬۴۴۰ در روز (~۱٫۴٪). |

## اندازه‌گیری‌های فاز ۰ (۲۱ نوامبر ۲۰۲۶، با عدد)

۱. **CPU:** نسخه اول: پارس کامل ۸ فید واقعی (۱٫۸۶ MB، ‏۳۰۰ آیتم) در Node V8 ‏**۷٫۰۲ms** + هش ‏**۱٫۷۳ms**؛ در analytics واقعی Cloudflare تیک عادی ۵ فید **۷٫۷۴ms** و ۶ فید **۱۰٫۷۹ms** بود. پس از سبک‌سازی (پارس افزایشی + توقف در highwater): تیک‌های واقعی **۲٫۵۹ تا ۴٫۹۳ms** (fetch) و **۰ تا ۵ms** (cron در `wrangler tail`) — در سقف ۱۰ms جا می‌شود.
۲. **واکنش ANN/MAL به polling هر ۱ دقیقه:** ۷ بار poll در ۶ دقیقه (۲۲:۳۳ تا ۲۲:۳۹ UTC) — هر ۱۴ درخواست **۲۰۰**، **هیچ ۴۲۹**، هیچ `Retry-After`. یک ناهنجاری گذرا: در poll#5 فید MAL فقط **۳٬۰۰۹ بایت** برگرداند (به‌جای ~۱۹٬۷۷۷) بدون آیتم قابل پارس — در poll#6 به حالت عادی برگشت. Worker چنین پاسخی را به‌عنوان خطا log می‌کند و crash نمی‌کند.
۳. **تاخیر سایت → RSS:** آیتم تازه ANN با `pubDate` ‏۲۲:۰۰ UTC در poll ‏۲۲:۳۶:۴۳ هنوز در فید نبود و در poll ‏۲۲:۳۷:۴۴ ظاهر شد — یعنی **تاخیر pubDate تا ظاهرشدن در فید ≈ ۳۶ تا ۳۷ دقیقه** برای آن آیتم. (این تاخیر خودِ فید ANN است؛ Worker همان آیتم را در تیک ۲۲:۳۸:۵۵ — یعنی ~۱ دقیقه پس از ظاهرشدن در فید — تشخیص داد و در KV ثبت کرد.) قدمت تازه‌ترین آیتم‌ها در fetch ‏۲۲:۳۲ UTC: ‏ANN ‏۱۵۵ دقیقه، MAL ‏۲۸۹ دقیقه — این آهنگ انتشار خود سایت‌هاست، نه تاخیر فید.
۴. **scope دقیق PAT:** مستندات رسمی GitHub می‌گوید `POST /repos/{owner}/{repo}/dispatches` به **Contents: Read and write** نیاز دارد (جدول «Permissions required for fine-grained PATs»). انتظار اولیه «Actions: Read and write» برای `repository_dispatch` نادرست است — Actions: write مال endpoint جداگانه `workflow_dispatch` است.

## نتیجه تست زنده dispatch — ⚠️ نیازمند اصلاح PAT

تست زنده در ۲۱ نوامبر ۲۰۲۶، ۰۲:۰۸ تهران (`/tick?dispatch_test=1` و
تیک واقعی با ۱ خبر تازه):

- پاسخ GitHub: **HTTP ‏۴۰۳** — ‏`{"message":"Resource not accessible by personal access token","documentation_url":"https://docs.github.com/rest/repos/repos#create-a-repository-dispatch-event"}`
- علت: PAT فعلی (`anime-news-dispatch`) با **Actions: Read and write + Contents: Read-only** ساخته شده و `repository_dispatch` طبق مستندات رسمی به **Contents: write** نیاز دارد.
- **رفع دقیق (با مرورگر، بدون ساختن PAT تازه):** در
  `github.com/settings/tokens` همان PAT را ویرایش کنید و
  **Contents را به Read and write** تغییر دهید (Metadata: Read-only
  سر جایش می‌ماند؛ Actions: Read and write هم می‌تواند بماند).
  پس از اصلاح، `/tick?dispatch_test=1` باید **۲۰۴** برگرداند.
- تا زمان اصلاح، Worker خبرهای تازه را در KV ثبت می‌کند و dispatch را
  با ۴۰۳ در لاگ ثبت می‌کند؛ هیچ خبری گم نمی‌شود — آیتم‌ها در KV
  (`item:<sha256>`) منتظر sweeper ‏۱۵ دقیقه‌ای Actions می‌مانند.

## یافته‌های دیگر تست زنده

- **Fandom Post از polling ورکر حذف شد (۲۱ نوامبر ۲۰۲۶، تصمیم مدیر —
  گزینه ب):** سرور آن IPهای خروجی Cloudflare را بلاک می‌کند (۴۰۳ پایدار،
  بیش از ۳٫۵ ساعت، ۰۰:۱۱ تا ۰۳:۳۵ UTC؛ از همین VM با همان User-Agent
  ‏۲۰۰ می‌دهد). پوشش آن فقط با sweeper ‏Actions (هر ۱۵ دقیقه، با IP رانر
  گیت‌هاب) می‌ماند؛ `scripts/fetch.py` هنوز آن را دارد. بدون تست زنده
  دوباره از داخل Worker برنگردانیدش.
- **Seed (cold start) تایید شد:** تیک اول ۳۹ آیتم ANN و تیک دوم ۳۸
  آیتم MAL/AnimeTV/Siliconera را «دیده‌شده» علامت زد و **هیچ dispatchای
  نفرستاد** — بدون flood.
- **تشخیص خبر تازه تایید شد:** آیتم «North American Anime, Manga
  Releases, November 15-21» ‏(ANN) در تیک ۲۲:۳۸:۵۵ به‌عنوان fresh=1
  تشخیص داده و در KV ثبت شد (`item:e08ba92d…`)؛ dispatch آن با ۴۰۳
  رد شد (مشکل PAT، نه تشخیص). توجه: این آیتم از نوع فهرست هفتگی
  انتشار است و فیلتر کامل منتشرکننده (R10/R17) احتمالاً آن را از
  انتشار حذف می‌کند — تشخیص وظیفه Worker است، تصمیم انتشار با Actions.
- **KV با API مستقیم تایید شد:** ‏`hw:ann=2026-11-20T22:00:00Z`،
  ‏`meta:last_tick`، ‏`item:` + ‏`seen:` + ‏`story:` همه موجودند.
  نکته: `wrangler kv key list/get` در همین محیط خالی نشان می‌داد
  در حالی که API مستقیم کلیدها را برمی‌گرداند — برای وارسی KV از
  API مستقیم (یا داشبورد) استفاده کنید، نه از `wrangler kv key list`.
- **تیک‌های cron واقعی** (‏`wrangler tail`، نسخه نهایی):
  ۳ تیک متوالی با `fresh=0` و `dispatch=skipped (no fresh items)` —
  یعنی وقتی خبری نیست dispatch نمی‌رود. نمونه‌ها در بخش «تست خشک» بالا.

## فایل‌ها

```
worker/
├── src/index.js      # آشکارساز: fetch فید + dedupe سه‌لایه + dispatch
├── wrangler.toml     # نام، cron هر ۱ دقیقه، KV binding، vars (بدون secret)
├── README.md         # همین فایل
└── phase0/           # اسکریپت‌های اندازه‌گیری فاز ۰ (fetch/parse/poll) — موقت
```
