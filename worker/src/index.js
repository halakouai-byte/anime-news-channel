// anime-news-detector — Cloudflare Worker (detector) for the Persian anime
// news Telegram channel «اخبار دنیای انیمه» (@animekhabarfa).
//
// What it does (ARCHITECTURE.md v2 §6.2, step 1):
//   * Cron Trigger every 1 minute reads the due RSS feeds (8 sources).
//   * Detects fresh items, checks dedupe layers 1/2/3 against KV.
//   * Registers eligible items in KV (one key per item, append-only).
//   * Sends ONE repository_dispatch to GitHub Actions ONLY when there is
//     at least one fresh item. No news -> no dispatch, no KV write.
//
// What it does NOT do:
//   * No rewriting, no cover, no Telegram send (that is Actions' job).
//   * NO night-silence window anywhere: the user locked 24/7 operation,
//     including 02:00-07:00 Tehran. Nothing in this file gates on time
//     of day. (ARCHITECTURE.md §2.7's night-silence proposal was
//     explicitly rejected by the user on 2026-11-21.)
//   * No AI at runtime, no token in code. The dispatch PAT lives ONLY
//     as the Cloudflare Worker Secret GITHUB_DISPATCH_PAT. If the secret
//     is absent, the worker still detects + logs and simply skips dispatch.
//
// KV budget (Free: 1,000 writes/day): the worker writes to KV ONLY
// on-change. A tick with no fresh items performs ZERO KV writes.
// A tick with fresh items writes ~4 keys per item (item/seen/story/
// highwater) + 1 recent-titles update. Expected: 50-100 writes/day.
// meta:last_tick is written at most once per hour (24 writes/day max).
//
// CPU budget (Free Cron Trigger: 10 ms): fetch wall time does NOT count
// toward CPU. Only synchronous parse/dedupe counts. Measured in
// phase 0 (2026-11-21) with Cloudflare's own analytics
// (workersInvocationsAdaptive cpuTime): the FIRST version parsed the
// whole feed every tick and a normal 5-feed tick cost 7.7-10.8 ms —
// at/over the limit. The fix (this version): incremental parsing —
// items are newest-first, so scanning stops at the first item that is
// not newer than the highwater (usually 0-2 items per feed instead of
// 40/150). An in-worker performance.now() meter was REMOVED because it
// read 0.00 (timer granularity) while analytics showed 7.7 ms — a
// lying meter is worse than none. Authoritative CPU numbers come from
// Cloudflare analytics (see worker/README.md, phase-0 report).

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(runTick(env, { source: "cron", cron: event.cron }));
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/tick") {
      const out = await runTick(env, {
        source: "manual",
        dispatchTest: url.searchParams.get("dispatch_test") === "1",
      });
      return json(out, out.ok ? 200 : 500);
    }
    // Status endpoint: no feed fetch, no KV write. Reads meta:last_tick
    // (one KV read) so the manager can see the last tick without tail.
    const last = await env.NEWS_KV.get("meta:last_tick", "json").catch(() => null);
    return json({
      worker: "anime-news-detector",
      now_utc: new Date().toISOString(),
      now_tehran: new Date().toLocaleString("en-GB", { timeZone: "Asia/Tehran" }),
      cron: "* * * * *",
      repo: `${REPO_OWNER}/${REPO_NAME}`,
      dispatch_configured: Boolean(env.GITHUB_DISPATCH_PAT),
      last_tick: last,
      note: "GET /tick runs one detection tick now; /tick?dispatch_test=1 also sends a test repository_dispatch (event_type detector-ping).",
    });
  },
};

// ---------------------------------------------------------------- feeds

const REPO_OWNER = "halakouai-byte";
const REPO_NAME = "anime-news-channel";
const DISPATCH_URL = `https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/dispatches`;

const UA =
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";

const FEEDS = [
  { id: "ann",         name: "Anime News Network", url: "https://www.animenewsnetwork.com/news/rss.xml", everyMin: 1 },
  { id: "fandompost",  name: "The Fandom Post",    url: "https://www.fandompost.com/feed/",              everyMin: 1 },
  { id: "mal",         name: "MyAnimeList News",   url: "https://myanimelist.net/rss/news.xml",         everyMin: 2 },
  { id: "animetv",     name: "AnimeTV",            url: "https://animetv-jp.net/feed/",                 everyMin: 2 },
  { id: "siliconera",  name: "Siliconera",         url: "https://www.siliconera.com/feed/",             everyMin: 2 },
  { id: "animecorner", name: "Anime Corner",       url: "https://animecorner.me/feed/",                 everyMin: 5 },
  // Daily feeds: due once a day at 00:30 UTC (04:00 Tehran). They are
  // huge (Honey's ~1.3 MB / 150 items) and publish ~1 item/week, so
  // polling them every minute would burn CPU for nothing.
  { id: "honeys",      name: "Honey's Anime",      url: "https://honeysanime.com/feed/",                everyMin: 1440, dailyMinute: 30 },
  { id: "herald",      name: "Anime Herald",       url: "https://www.animeherald.com/feed/",            everyMin: 1440, dailyMinute: 30 },
];

const FETCH_TIMEOUT_MS = 8000;
const FRESH_HOURS = 48;          // ARCH §2.4: pubDate < 48 h
const PARSE_TRUNCATE_BYTES = 200_000; // see header: newest-first feeds
const SEEN_TTL = 30 * 24 * 3600; // 30 days (ARCH §2.5 layer 1)
const STORY_TTL = 48 * 3600;     // 48 h story window (ARCH §2.5 layer 2)
const TITLES_TTL = 7 * 24 * 3600; // 7-day title-similarity window (layer 3)
const ITEM_TTL = 30 * 24 * 3600;

// Detector-level exclusions (ARCH §2.4 R-list, high-precision subset
// only — cheap title patterns. The publisher in Actions applies the
// full 17-category filter, including the Siliconera anime-only rule
// R15, which needs the franchise bank the worker does not carry; the
// detector therefore does NOT judge Siliconera anime-ness and tags
// those items for the publisher instead of dropping them.)
const EXCLUDE_PATTERNS = [
  [/review/i, "R1-review"], [/rankings?/i, "R2-ranking"], [/blu-?ray/i, "R3-bluray"],
  [/poll/i, "R4-poll"], [/quiz/i, "R11-quiz"], [/giveaway/i, "R11-giveaway"],
  [/sponsored/i, "R12-sponsored"], [/\bmerch\b/i, "R5-merch"],
  [/rumor/i, "R7-rumor"], [/reportedly/i, "R7-rumor"], [/allegedly/i, "R7-rumor"],
];

const EVENT_KEYWORDS = [
  [/trailer|teaser|\bPV\b|preview video/i, "trailer"],
  [/release date|premieres|premiere date|debuts/i, "date"],
  [/cast|voice actor|voices?/i, "casting"],
  [/box office|grosses|earns/i, "box_office"],
  [/manga|light novel|adaptation|gets anime/i, "adaptation"],
  [/award|wins|nominated/i, "award"],
  [/event|festival|expo|concert/i, "event"],
  [/announces?|reveals?|unveils?|confirms?|gets new|green-?lit/i, "announcement"],
];

// ---------------------------------------------------------------- tick

async function runTick(env, opts) {
  const startedAt = Date.now();
  const now = new Date(startedAt);
  const minuteOfDay = now.getUTCHours() * 60 + now.getUTCMinutes();
  const due = FEEDS.filter((f) =>
    f.everyMin >= 1440 ? minuteOfDay === f.dailyMinute : minuteOfDay % f.everyMin === 0,
  );

  const result = {
    ok: true, at_utc: now.toISOString(), source: opts.source,
    feeds_due: due.map((f) => f.id), fetched: 0, candidates: 0,
    fresh: 0, excluded: 0, duplicates: 0, dispatched: false,
    dispatch_status: null, errors: [],
  };

  // Recent titles for layer-3 similarity (one KV read per tick).
  let recentTitles = [];
  try {
    recentTitles = (await env.NEWS_KV.get("meta:recent_titles", "json")) || [];
  } catch (e) {
    result.errors.push(`recent_titles read: ${String(e).slice(0, 120)}`);
  }

  const freshItems = [];
  const settled = await Promise.allSettled(due.map((f) => fetchFeed(env, f, now, recentTitles)));

  for (let i = 0; i < settled.length; i++) {
    const feed = due[i];
    const s = settled[i];
    if (s.status === "rejected") {
      result.errors.push(`${feed.id}: ${String(s.reason).slice(0, 160)}`);
      continue;
    }
    const r = s.value;
    if (r.error) { result.errors.push(`${feed.id}: ${r.error}`); continue; }
    result.fetched++;
    result.candidates += r.candidates;
    result.excluded += r.excluded;
    result.duplicates += r.duplicates;
    freshItems.push(...r.fresh);
  }
  result.fresh = freshItems.length;

  // Register fresh items in KV (on-change writes only) + update
  // highwater marks and the recent-titles list.
  if (freshItems.length > 0) {
    await registerFresh(env, freshItems, recentTitles, result);
  }

  // Dispatch ONLY when there is fresh news.
  if (freshItems.length > 0) {
    const d = await sendDispatch(env, freshItems, "news-detected");
    result.dispatch_status = typeof d === "object" ? d.status : d;
    result.dispatched = result.dispatch_status === 204;
    if (!result.dispatched) {
      result.errors.push(`dispatch: HTTP ${result.dispatch_status}${typeof d === "object" && d.error ? ` — ${d.error}` : ""}`);
    }
  } else if (opts.dispatchTest) {
    // Manual test hook: verify the PAT + endpoint without fresh news.
    const d = await sendDispatch(env, [], "detector-ping", true);
    result.dispatch_status = typeof d === "object" ? d.status : d;
    result.dispatched = result.dispatch_status === 204;
    if (!result.dispatched) {
      result.errors.push(`dispatch test: HTTP ${result.dispatch_status}${typeof d === "object" && d.error ? ` — ${d.error}` : ""}`);
    }
  } else {
    result.dispatch_status = "skipped (no fresh items)";
  }

  // Hourly status write only (≤24 KV writes/day) — never per tick.
  if (minuteOfDay % 60 === 0 || freshItems.length > 0 || result.errors.length > 0) {
    await env.NEWS_KV.put("meta:last_tick", JSON.stringify({ ...result, fresh_titles: freshItems.map((x) => x.title).slice(0, 10) }), { expirationTtl: 2 * 24 * 3600 }).catch(() => {});
  }

  console.log(`tick ${result.source} due=${result.feeds_due.join(",")} fetched=${result.fetched} fresh=${result.fresh} excluded=${result.excluded} dup=${result.duplicates} dispatch=${result.dispatch_status} errors=${result.errors.length}`);
  return result;
}

// ---------------------------------------------------------------- feed

async function fetchFeed(env, feed, now, recentTitles) {
  const out = { candidates: 0, excluded: 0, duplicates: 0, fresh: [], error: null };
  let res;
  try {
    res = await fetch(feed.url, {
      headers: { "User-Agent": UA, Accept: "application/rss+xml, application/xml, text/xml" },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
  } catch (e) {
    out.error = `fetch failed: ${String(e).slice(0, 120)}`;
    return out;
  }
  if (res.status !== 200) {
    out.error = `HTTP ${res.status}${res.status === 429 ? " (rate-limited)" : ""}`;
    return out;
  }
  const xml = (await res.text()).slice(0, PARSE_TRUNCATE_BYTES);
  // Incremental parse: items are newest-first, so we stop scanning at
  // the first item that is not newer than the highwater (or older than
  // 48 h) instead of parsing the whole feed. On a normal tick that is
  // 0-2 items per feed, not 40/150 — this is what keeps a tick's CPU
  // near 1-3 ms instead of ~8-11 ms (phase-0 GraphQL measurement).
  const itemRe = /<item[\s>]([\s\S]*?)<\/item>/g;
  let m;
  const hwRaw = await env.NEWS_KV.get(`hw:${feed.id}`).catch(() => null);
  const highwater = hwRaw ? new Date(hwRaw).getTime() : 0;
  const seeding = highwater === 0;
  let maxPub = highwater;

  while ((m = itemRe.exec(xml)) !== null) {
    const it = parseItem(m[1]);
    const pub = Date.parse(it.pubDate);
    if (!pub || Number.isNaN(pub)) continue;
    if (pub > maxPub) maxPub = pub;
    if (now.getTime() - pub > FRESH_HOURS * 3600_000) break; // older than 48 h: rest is older too
    if (pub <= highwater) break; // reached already-processed items
    out.candidates++;
    const excluded = matchExclude(it.title + " " + it.description);
    if (excluded) { out.excluded++; continue; }
    const id = await sha256Hex(normalizeLink(it.link || it.guid || it.title));
    const seen = await env.NEWS_KV.get(`seen:${id}`).catch(() => null);
    if (seen) { out.duplicates++; continue; }
    const storyKey = storyKeyFor(it);
    const storySeen = await env.NEWS_KV.get(`story:${storyKey}`).catch(() => null);
    if (storySeen) { out.duplicates++; continue; }
    if (similarTitle(it.title, recentTitles)) { out.duplicates++; continue; }
    out.fresh.push({
      id, source: feed.id, source_name: feed.name, title: it.title,
      link: normalizeLink(it.link || it.guid), guid: it.guid || "",
      pubDate: new Date(pub).toISOString(), story_key: storyKey,
      event_type: eventTypeOf(it.title + " " + it.description),
      detected_at_utc: now.toISOString(), seed: seeding,
    });
  }

  if (seeding) {
    // Bootstrap: record the highwater + seen marks, but keep the items
    // OUT of the queue (seed:true items are never registered below —
    // runTick only registers fresh items when NOT seeding; see
    // registerFresh) and dispatch nothing.
    for (const it of out.fresh) {
      await env.NEWS_KV.put(`seen:${it.id}`, "1", { expirationTtl: SEEN_TTL }).catch(() => {});
    }
    out.fresh = [];
    out.duplicates = out.candidates - out.excluded; // seed: all known
  }
  if (maxPub > highwater) {
    await env.NEWS_KV.put(`hw:${feed.id}`, new Date(maxPub).toISOString(), { expirationTtl: SEEN_TTL }).catch(() => {});
  }
  return out;
}

async function registerFresh(env, freshItems, recentTitles, result) {
  const titles = recentTitles.map((t) => t.title || t);
  for (const it of freshItems) {
    const value = JSON.stringify({ ...it, seed: undefined, status: "queued" });
    await Promise.all([
      env.NEWS_KV.put(`item:${it.id}`, value, { expirationTtl: ITEM_TTL }),
      env.NEWS_KV.put(`seen:${it.id}`, "1", { expirationTtl: SEEN_TTL }),
      env.NEWS_KV.put(`story:${it.story_key}`, it.id, { expirationTtl: STORY_TTL }),
    ]).catch((e) => result.errors.push(`kv put ${it.id.slice(0, 12)}: ${String(e).slice(0, 100)}`));
    titles.push(it.title);
  }
  // Recent titles for layer 3 (one write per tick that had fresh news).
  const trimmed = titles.slice(-200);
  await env.NEWS_KV.put("meta:recent_titles", JSON.stringify(trimmed), { expirationTtl: TITLES_TTL }).catch(() => {});
}

// ---------------------------------------------------------------- dispatch

async function sendDispatch(env, items, eventType, isTest = false) {
  const pat = env.GITHUB_DISPATCH_PAT;
  if (!pat) {
    console.log("dispatch skipped: GITHUB_DISPATCH_PAT secret is not set (detect + log only)");
    return "skipped (no secret)";
  }
  const body = {
    event_type: eventType,
    client_payload: isTest
      ? { test: true, at_utc: new Date().toISOString(), worker: "anime-news-detector" }
      : {
          count: items.length,
          at_utc: new Date().toISOString(),
          items: items.map((it) => ({ id: it.id, source: it.source, title: it.title, link: it.link, pubDate: it.pubDate, story_key: it.story_key })),
        },
  };
  try {
    const res = await fetch(DISPATCH_URL, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        // The PAT is sent ONLY in this Authorization header, never logged.
        Authorization: `Bearer ${pat}`,
        "User-Agent": "anime-news-detector",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(10000),
    });
    console.log(`dispatch ${eventType} -> HTTP ${res.status}`);
    if (res.status !== 204) {
      // Include GitHub's error message (no token in it) so a 403 can be
      // diagnosed: e.g. "Resource not accessible by integration" means
      // the PAT lacks Contents: write for /dispatches.
      const bodyText = (await res.text().catch(() => "")).slice(0, 200);
      console.log(`dispatch ${eventType} error body: ${bodyText}`);
      return { status: res.status, error: bodyText };
    }
    return res.status;
  } catch (e) {
    console.log(`dispatch ${eventType} failed: ${String(e).slice(0, 120)}`);
    return "fetch failed";
  }
}

// ---------------------------------------------------------------- parsing

function parseItem(b) {
  return {
    title: decodeEntities(pick(b, "title")),
    link: decodeEntities(pick(b, "link")),
    guid: decodeEntities(pick(b, "guid")),
    pubDate: pick(b, "pubDate"),
    description: decodeEntities(pick(b, "description")).slice(0, 500),
  };
}

function pick(block, tag) {
  const x = block.match(new RegExp(`<${tag}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${tag}>`));
  return x ? x[1].trim() : "";
}

function decodeEntities(s) {
  return s
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"').replace(/&#0?39;/g, "'").replace(/&#0?38;/g, "&")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/&#x([0-9a-fA-F]+);/g, (_, n) => String.fromCodePoint(parseInt(n, 16)));
}

// ---------------------------------------------------------------- dedupe

function normalizeLink(raw) {
  try {
    const u = new URL(raw.trim());
    u.protocol = u.protocol.toLowerCase();
    u.hostname = u.hostname.toLowerCase().replace(/^www\./, "");
    for (const p of [...u.searchParams.keys()]) {
      if (/^(utm_|fbclid|gclid|ref$|ref=rss)/i.test(p)) u.searchParams.delete(p);
    }
    u.hash = "";
    let s = u.toString();
    if (s.endsWith("/")) s = s.slice(0, -1);
    return s;
  } catch {
    return raw.trim().toLowerCase();
  }
}

async function sha256Hex(s) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function normalizeFranchise(title) {
  return title
    .toLowerCase()
    .replace(/\[[^\]]*\]/g, " ")
    .replace(/[^a-z0-9\u0600-\u06FF ]/g, " ")
    .replace(/\b(anime|manga|season|trailer|teaser|reveals?|announces?|unveils?|confirms?|gets?|new|official|first|second|third|film|movie|series|episode|part|chapter)\b/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .split(" ")
    .slice(0, 6)
    .join(" ");
}

function eventTypeOf(text) {
  for (const [re, type] of EVENT_KEYWORDS) if (re.test(text)) return type;
  return "other";
}

function storyKeyFor(it) {
  const franchise = normalizeFranchise(it.title);
  const type = eventTypeOf(it.title + " " + it.description);
  const pub = Date.parse(it.pubDate);
  const bucket = Number.isNaN(pub) ? 0 : Math.floor(pub / (48 * 3600_000));
  return `${franchise}|${type}|${bucket}`;
}

function tokenizeTitle(title) {
  return new Set(
    title.toLowerCase().replace(/[^a-z0-9\u0600-\u06FF ]/g, " ").split(/\s+/)
      .filter((w) => w.length > 2 && !["anime", "manga", "season", "reveals", "announces", "trailer", "teaser", "official"].includes(w)),
  );
}

function similarTitle(title, recentTitles) {
  const a = tokenizeTitle(title);
  if (a.size === 0) return false;
  for (const other of recentTitles) {
    const b = tokenizeTitle(typeof other === "string" ? other : other.title || "");
    if (b.size === 0) continue;
    let inter = 0;
    for (const w of a) if (b.has(w)) inter++;
    const jaccard = inter / (a.size + b.size - inter);
    if (jaccard >= 0.85) return true;
  }
  return false;
}

function matchExclude(text) {
  for (const [re, code] of EXCLUDE_PATTERNS) if (re.test(text)) return code;
  return null;
}

function json(obj, status = 200) {
  return new Response(JSON.stringify(obj, null, 2), {
    status, headers: { "Content-Type": "application/json; charset=utf-8" },
  });
}
