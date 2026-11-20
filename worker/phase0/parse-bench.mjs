// Phase 0 (1): time the worker-style regex RSS parse (no DOMParser in Workers)
// over real feed bodies fetched right now, including Honey's 1.3 MB.
import fs from "fs";
const UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";
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
function parseItems(xml) {
  const items = [];
  const re = /<item[\s>]([\s\S]*?)<\/item>/g;
  let m;
  while ((m = re.exec(xml)) !== null) {
    const b = m[1];
    const pick = (tag) => { const x = b.match(new RegExp(`<${tag}[^>]*>(?:<!\\[CDATA\\[)?([\\s\\S]*?)(?:\\]\\]>)?</${tag}>`)); return x ? x[1].trim() : ""; };
    items.push({ title: pick("title"), link: pick("link"), guid: pick("guid"), pubDate: pick("pubDate"), desc: pick("description").slice(0, 200) });
  }
  return items;
}
function sha256hex(s) {
  // cheap synchronous stand-in for crypto.subtle in bench; real worker uses subtle (async, ~µs per hash)
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < s.length; i++) { const ch = s.charCodeAt(i); h1 = Math.imul(h1 ^ ch, 2654435761); h2 = Math.imul(h2 ^ ch, 1597334677); }
  return (h1 >>> 0).toString(16) + (h2 >>> 0).toString(16);
}
const results = {};
let totalBytes = 0, totalItems = 0;
for (const [name, url] of Object.entries(FEEDS)) {
  const t0 = performance.now();
  const res = await fetch(url, { headers: { "User-Agent": UA } });
  const xml = await res.text();
  const tFetch = performance.now();
  // parse 5x to get stable CPU number, report per-run
  let items;
  const tP0 = performance.now();
  for (let i = 0; i < 5; i++) items = parseItems(xml);
  const tP1 = performance.now();
  // dedupe layer 1+2: hash + story key per item (sync stand-in)
  const tD0 = performance.now();
  for (const it of items) { sha256hex(it.guid || it.link); }
  const tD1 = performance.now();
  results[name] = { status: res.status, bytes: xml.length, fetch_wall_ms: +(tFetch - t0).toFixed(0),
    parse_ms_per_run: +((tP1 - tP0) / 5).toFixed(2), items: items.length, dedupe_hash_ms: +((tD1 - tD0)).toFixed(2) };
  totalBytes += xml.length; totalItems += items.length;
  console.log(name, JSON.stringify(results[name]));
}
const totalParse = Object.values(results).reduce((a, r) => a + r.parse_ms_per_run, 0);
const totalHash = Object.values(results).reduce((a, r) => a + r.dedupe_hash_ms, 0);
console.log(`TOTAL bytes=${totalBytes} items=${totalItems} parse_all_feeds_ms=${totalParse.toFixed(2)} hash_all_ms=${totalHash.toFixed(2)} parse+hash=${(totalParse+totalHash).toFixed(2)}`);
console.log("NOTE: Node V8 wall time here is an upper bound proxy; Workers CPU limit is 10ms for Cron triggers. See phase0 report for workerd measurement.");
fs.writeFileSync("/tmp/parse-bench.json", JSON.stringify(results, null, 2));
