// Phase 0 (2): poll ANN + MAL every 60s for ~6 minutes, log status + newest guid/pubDate.
const UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36";
const FEEDS = { ann: "https://www.animenewsnetwork.com/news/rss.xml", mal: "https://myanimelist.net/rss/news.xml" };
const seen = { ann: null, mal: null };
for (let i = 0; i < 7; i++) {
  const t = new Date().toISOString();
  for (const [name, url] of Object.entries(FEEDS)) {
    try {
      const r = await fetch(url, { headers: { "User-Agent": UA } });
      const text = await r.text();
      const m = text.match(/<item[\s>][\s\S]*?<title>(?:<!\[CDATA\[)?([\s\S]*?)(?:\]\]>)?<\/title>[\s\S]*?<pubDate>([^<]+)<\/pubDate>/);
      const guid = (text.match(/<guid[^>]*>([^<]+)<\/guid>/) || [])[1] || "?";
      const isNew = seen[name] !== null && seen[name] !== guid;
      console.log(`${t} poll#${i} ${name} status=${r.status} bytes=${text.length} newest_pub=${m ? m[2] : "?"} guid_changed=${isNew} ${r.status===429 ? "RATE-LIMITED!" : ""} retry_after=${r.headers.get("retry-after") || "-"}`);
      seen[name] = guid;
    } catch (e) { console.log(`${t} poll#${i} ${name} ERROR ${e.message}`); }
  }
  if (i < 6) await new Promise(r => setTimeout(r, 60000));
}
console.log("POLL DONE");
