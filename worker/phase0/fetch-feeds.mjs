const FEEDS = {
  ann: "https://www.animenewsnetwork.com/news/rss.xml",
  mal: "https://myanimelist.net/rss/news.xml",
  animecorner: "https://animecorner.me/feed/",
  animetv: "https://animetv-jp.net/feed/",
  fandompost: "https://www.fandompost.com/feed/",
  siliconera: "https://www.siliconera.com/feed/",
  honeys: "https://honeysanime.com/feed/",
  herald: "https://www.animeherald.com/feed/",
};
const UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";
const now = new Date();
const out = {};
for (const [name, url] of Object.entries(FEEDS)) {
  const t0 = performance.now();
  try {
    const res = await fetch(url, { headers: { "User-Agent": UA, Accept: "application/rss+xml, application/xml, text/xml" } });
    const text = await res.text();
    const t1 = performance.now();
    const items = (text.match(/<item[\s>]/g) || []).length;
    const pubDates = [...text.matchAll(/<pubDate>([^<]+)<\/pubDate>/g)].map(m => m[1]);
    const latest = pubDates.length ? new Date(pubDates[0]) : null;
    const titles = [...text.matchAll(/<title>(?:<!\[CDATA\[)?([^<\]]+)/g)].slice(0,3).map(m=>m[1].trim());
    out[name] = { status: res.status, bytes: text.length, fetch_ms: +(t1-t0).toFixed(0), items,
      latest_pubdate_utc: latest ? latest.toISOString() : null,
      latest_age_min: latest ? +((now - latest)/60000).toFixed(1) : null,
      first_titles: titles };
    console.log(name, JSON.stringify(out[name]));
  } catch (e) {
    console.log(name, "ERROR", e.message);
    out[name] = { error: e.message };
  }
}
import fs from "fs";
fs.writeFileSync(process.argv[2] || "/tmp/feeds1.json", JSON.stringify({ fetched_at_utc: now.toISOString(), feeds: out }, null, 2));
