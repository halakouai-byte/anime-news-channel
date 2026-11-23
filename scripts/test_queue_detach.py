#!/usr/bin/env python3
"""تست بسته رفع جداافتادن صف — ران #34 (۲۳ نوامبر ۲۰۲۶).

حادثه: Zatsuyou (پیام ۳۱) پست شد ولی ردیفش QUEUED ماند؛ Aristocrat
(پیام ۳۲) پست شد ولی ردیفش HOLD ماند؛ Wakako-zake در گیت ماند ولی
ردیفش QUEUED ماند. ریشه: `sync_remote_state` همیشه True برمی‌گرداند،
پس sync پیش‌ازارسال در `publish_one` همیشه صف را از دیسک دوباره
می‌خواند و ارجاع `item` جدا می‌افتاد — تغییر وضعیت روی یک دیکشنری
جداافتاده نوشته می‌شد و گم می‌شد، در حالی که state و آرشیو درست بودند.

رفع (این بسته):
  ۱. `publish_one` بعد از sync، آیتم را با هش در صف تازه‌خوانده‌شده
     دوباره پیدا می‌کند (`_find_queue_row`) تا تغییر روی ردیف زنده بنشیند.
  ۲. `sync_remote_state` وضعیت صف را با posted_hashes همگام می‌کند
     (`reconcile_queue_posted`) — ردیف پست‌شده POSTED می‌خواند، نه تا
     انقضا QUEUED.
  ۳. `sync_remote_state` به‌جای True همیشگی، `changed` را برمی‌گرداند؛
     `merge_state.py` خطای fetch را جداگانه چک می‌کند (abort روی fetch
     ناموفق حفظ شده).

اجرا: /tmp/anime-venv2/bin/python scripts/test_queue_detach.py
بدون شبکه، بدون تلگرام — sendPhoto و کاور mock می‌شوند؛ sync و
merge_state با ریپوی git موقت تست می‌شوند (الگوی test_race_phantom).
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (load_queue, load_state, reconcile_queue_posted,
                    sync_remote_state)
import publish
from publish import _find_queue_row, publish_one

PASS = 0
FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {extra}")


# --- T1: reconcile_queue_posted (منطق خالص) ---
print("T1 reconcile_queue_posted")
st = {"posted_hashes": {"H-a": 31, "H-b": 32, "H-c": 33}}
q = {"version": 1, "items": [
    {"guid": "g-a", "hash": "H-a", "status": "QUEUED"},
    {"guid": "g-b", "hash": "H-b", "status": "HOLD",
     "hold_reason": "gates_failed:why_specific"},
    {"guid": "g-c", "hash": "H-c", "status": "STALE"},
    {"guid": "g-d", "hash": "H-d", "status": "QUEUED"},
    {"guid": "g-e", "hash": "H-e", "status": "POSTED", "message_id": 5},
]}
changed = reconcile_queue_posted(st, q)
by = {i["hash"]: i for i in q["items"]}
check("QUEUED posted row -> POSTED", by["H-a"]["status"] == "POSTED")
check("QUEUED posted row gets message_id", by["H-a"]["message_id"] == 31)
check("HOLD posted row -> POSTED", by["H-b"]["status"] == "POSTED"
      and by["H-b"]["message_id"] == 32)
check("STALE posted row -> POSTED", by["H-c"]["status"] == "POSTED")
check("unposted row untouched", by["H-d"]["status"] == "QUEUED")
check("already-POSTED row untouched", by["H-e"]["status"] == "POSTED"
      and by["H-e"]["message_id"] == 5)
check("returns True when it changed something", changed is True)
# ردیف POSTED با message_id اشتباه → به مرجع (posted_hashes) اصلاح می‌شود
q2 = {"items": [{"guid": "g-x", "hash": "H-a", "status": "POSTED",
                 "message_id": 999}]}
check("wrong message_id is corrected to the authoritative one",
      reconcile_queue_posted(st, q2) is True
      and q2["items"][0]["message_id"] == 31)
# هیچ تغییری → False
q3 = {"items": [{"guid": "g-a", "hash": "H-a", "status": "POSTED",
                 "message_id": 31}]}
check("returns False when nothing changed",
      reconcile_queue_posted(st, q3) is False)

# --- T2: _find_queue_row + مکانیزم جداافتادن ---
print("T2 _find_queue_row + detach mechanism")
q = {"version": 1, "items": [
    {"guid": "g1", "hash": "H1", "status": "QUEUED"},
    {"guid": "g2", "hash": "H2", "status": "HOLD"},
]}
check("finds by hash", _find_queue_row(q, {"hash": "H2"}) is q["items"][1])
check("finds by guid (fallback)", _find_queue_row(q, {"guid": "g1"}) is q["items"][0])
check("returns None when absent", _find_queue_row(q, {"hash": "H9"}) is None)
# بازپخش مکانیزم باگ: ارجاع پیش‌از-reload جدا می‌افتد
old_item = q["items"][0]
fresh = {"version": 1, "items": [
    {"guid": "g1", "hash": "H1", "status": "QUEUED"},
    {"guid": "g2", "hash": "H2", "status": "HOLD"},
]}
q.clear()
q.update(fresh)
old_item["status"] = "POSTED"  # همان کاری که کد قدیمی می‌کرد
check("mutating the detached reference is lost",
      q["items"][0]["status"] == "QUEUED", f"got {q['items'][0]['status']}")
live = _find_queue_row(q, old_item)
check("re-find returns the live row", live is q["items"][0])
live["status"] = "POSTED"
check("mutating the re-found row lands", q["items"][0]["status"] == "POSTED")


# --- T3 + T4 + T5: ریپوی git موقت ---
print("T3+T4+T5 temp git repo")


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"git {' '.join(args)} in {cwd}: {r.stderr}"
    return r.stdout.strip()


def _write_repo(repo, ids, hashes, queue_items):
    d = repo / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({
        "posted_message_ids": ids, "posted_hashes": hashes,
        "story_keys": {}, "seen_guids": [], "seen_at": {},
        "recent_titles": [], "last_publish_utc": "2026-11-23T00:00:00Z",
        "counters": {"posts_total": len(ids), "duplicates_total": 0,
                     "rejected_total": 0, "hold_total": 0,
                     "posts_today": len(ids), "posts_today_date": "2026-11-23"},
        "template_usage_7d": {},
        "circuit_breaker": {"active": False, "activated_at": None,
                            "posts_today": 0, "queue_size": 0},
    }, ensure_ascii=False), encoding="utf-8")
    (d / "queue.json").write_text(json.dumps(
        {"version": 1, "items": queue_items}, ensure_ascii=False), encoding="utf-8")
    (d / "archive.jsonl").write_text("", encoding="utf-8")
    (repo / "logs").mkdir(exist_ok=True)
    (repo / "logs" / "fetch-log.md").write_text("", encoding="utf-8")
    (repo / "logs" / "publish-log.md").write_text("", encoding="utf-8")


tmp = Path(tempfile.mkdtemp(prefix="queue-detach-"))
try:
    _git(tmp, "init", "--bare", "remote.git")
    remote = tmp / "remote.git"
    a = tmp / "A"
    _git(tmp, "clone", "remote.git", "A")
    _git(a, "config", "user.name", "test")
    _git(a, "config", "user.email", "test@example.com")
    _git(a, "checkout", "-b", "main")

    # --- T3: sync مقدار changed را برمی‌گرداند + همگام‌سازی صف ---
    # v1: ردیف H-x در صف QUEUED است و هنوز پست نشده
    stale_row = {"guid": "g-x", "hash": "H-x", "title": "Stale row",
                 "source": "ANN", "status": "QUEUED",
                 "created_utc": "2026-11-23T00:00:00Z",
                 "pubDate": "2026-11-23T00:00:00Z"}
    _write_repo(a, [], {}, [dict(stale_row)])
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v1 stale row queued")
    _git(a, "push", "origin", "main")
    _git(tmp, "--git-dir", "remote.git", "symbolic-ref", "HEAD", "refs/heads/main")
    b = tmp / "B"
    _git(tmp, "clone", "remote.git", "B")
    _git(b, "config", "user.name", "test")
    _git(b, "config", "user.email", "test@example.com")
    # بدون تغییر راه‌دور → False (دیگر True همیشگی نیست)
    no_change = sync_remote_state(state_path=b / "data" / "state.json",
                                  queue_path=b / "data" / "queue.json",
                                  archive_path=b / "data" / "archive.jsonl",
                                  repo_dir=b)
    check("sync returns False when nothing changed", no_change is False,
          f"got {no_change}")
    # A حالا H-x را پست می‌کند (مثل ران دیگری) ولی ردیف صف را QUEUED
    # می‌گذارد — همان وضعیتی که ران #34 ساخت
    _write_repo(a, [99], {"H-x": 99}, [dict(stale_row)])
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v2 posted H-x, row still queued")
    _git(a, "push", "origin", "main")
    changed = sync_remote_state(state_path=b / "data" / "state.json",
                                queue_path=b / "data" / "queue.json",
                                archive_path=b / "data" / "archive.jsonl",
                                repo_dir=b)
    check("sync returns True when the remote changed", changed is True,
          f"got {changed}")
    b_state = load_state(b / "data" / "state.json")
    b_queue = load_queue(b / "data" / "queue.json")
    check("sync brings the remote post into state",
          b_state["posted_hashes"].get("H-x") == 99)
    check("stale QUEUED row is healed to POSTED by the sync",
          b_queue["items"][0]["status"] == "POSTED"
          and b_queue["items"][0].get("message_id") == 99,
          f"got {b_queue['items'][0]}")

    # --- T4: publish_one سرتاسری — reload در sync، ردیف POSTED می‌ماند ---
    # v3 در A: یک پست دیگر (H-other) تا sync در publish_one تغییر ببیند
    # و reload کند — همان ماشه‌ای که در #34 جداافتادن را ساخت.
    fresh_pub = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    bang = {"guid": "ann-bangdream-t4", "hash": "H-bangdream-t4",
            "title": "BanG Dream! Yume∞Mita Series Confirms New Anime in Production",
            "summary": "TV anime based on BanG Dream! project's Mugendai Mewtype band "
                       "premiered on July 2",
            "source": "ANN", "source_name": "ANN",
            "link": "https://animenewsnetwork.com/news/2026-11-20/bang-dream-yume-mita-"
                    "series-confirms-new-anime-in-production/.244026",
            "pubDate": fresh_pub, "created_utc": fresh_pub,
            "status": "QUEUED", "priority_score": 80, "category": "فصل جدید",
            "story_key": "bang dream|announcement|10390"}
    _write_repo(a, [99, 50], {"H-x": 99, "H-other": 50}, [dict(bang)])
    # توجه: _write_repo صف A را با bang بازنویسی می‌کند؛ ردیف H-x در A
    # دیگر نیست، ولی state راه‌دور H-x را پست‌شده دارد — B آن را نگه می‌دارد.
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v3 another run posted H-other")
    _git(a, "push", "origin", "main")
    # B: صف محلی همان bang را دارد (از v1/v2 نمی‌آید — دستی می‌نویسیم تا
    # دقیقاً وضعیت ران #34 را داشته باشیم: یک آیتم QUEUED آماده ارسال)
    _write_repo(b, [99], {"H-x": 99}, [dict(bang)])
    state = load_state(b / "data" / "state.json")
    queue = load_queue(b / "data" / "queue.json")
    item = queue["items"][0]

    def _fake_send_photo(token, chat_id, photo_path, caption):
        return {"message_id": 123, "ok": True}

    def _fake_build_cover(cover_item, out_path):
        Path(out_path).write_bytes(b"fake-cover")

    _orig_send, _orig_cover = publish.send_photo, publish.build_cover
    _orig_log = publish.append_log
    _orig_recent = publish._recent_archive_captions
    _orig_sync = publish.sync_remote_state
    publish.send_photo = _fake_send_photo
    publish.build_cover = _fake_build_cover
    publish.append_log = lambda *args, **kwargs: None
    publish._recent_archive_captions = lambda n: []
    # publish_one داخلاً sync را با repo_root() صدا می‌زند (در پروداکشن
    # همان checkout است)؛ در تست آن را به ریپوی موقت B می‌بریم تا reload
    # واقعی رخ بدهد — همان ماشه جداافتادن.
    publish.sync_remote_state = lambda **kw: _orig_sync(repo_dir=b, **kw)
    (tmp / "out").mkdir(parents=True, exist_ok=True)
    try:
        result = publish_one(item, state, queue, "test-token", "test-chat",
                             workdir=tmp / "out",
                             archive_path=b / "data" / "archive.jsonl",
                             state_path=b / "data" / "state.json",
                             queue_path=b / "data" / "queue.json")
    finally:
        publish.send_photo, publish.build_cover = _orig_send, _orig_cover
        publish.append_log = _orig_log
        publish._recent_archive_captions = _orig_recent
        publish.sync_remote_state = _orig_sync
    check("publish_one posts (not None)", result is not None, f"got {result}")
    disk_queue = load_queue(b / "data" / "queue.json")
    disk_row = next((i for i in disk_queue["items"]
                     if i.get("hash") == "H-bangdream-t4"), None)
    check("posted row is POSTED on disk (not QUEUED)",
          disk_row is not None and disk_row.get("status") == "POSTED",
          f"got {disk_row}")
    check("posted row keeps its message_id on disk",
          disk_row is not None and disk_row.get("message_id") == 123,
          f"got {disk_row}")
    disk_state = load_state(b / "data" / "state.json")
    check("state has the new post",
          disk_state["posted_hashes"].get("H-bangdream-t4") == 123)

    # --- T5: merge_state.py — abort روی fetch ناموفق، ادامه روی عدم تغییر ---
    # ۵الف: fetch ناموفق (remote خراب) → خروج ۱
    c = tmp / "C"
    _git(tmp, "clone", "remote.git", "C")
    _git(c, "config", "user.name", "test")
    _git(c, "config", "user.email", "test@example.com")
    _git(c, "remote", "remove", "origin")
    r = subprocess.run([sys.executable,
                        str(Path(__file__).resolve().parent / "merge_state.py"),
                        "--commit-message", "test: merge state [skip ci]",
                        "--repo-dir", str(c)],
                       capture_output=True, text=True, timeout=120)
    check("merge_state aborts (exit 1) when fetch fails", r.returncode == 1,
          f"rc={r.returncode} out={r.stdout[-200:]} err={r.stderr[-200:]}")
    # ۵ب: تغییری هست → ادامه می‌دهد و خروج ۰ (کامیت + push موفق)
    r2 = subprocess.run([sys.executable,
                         str(Path(__file__).resolve().parent / "merge_state.py"),
                         "--commit-message", "test: merge state [skip ci]",
                         "--repo-dir", str(b)],
                        capture_output=True, text=True, timeout=120)
    check("merge_state exits 0 when there are changes", r2.returncode == 0,
          f"rc={r2.returncode} out={r2.stdout[-200:]} err={r2.stderr[-200:]}")
    # ۵ج: دوباره، حالا هیچ تغییری نیست (sync مقدار False برمی‌گرداند ولی
    # fetch موفق است) → باز هم ادامه می‌دهد و خروج ۰ (چیزی برای کامیت نیست)
    r3 = subprocess.run([sys.executable,
                         str(Path(__file__).resolve().parent / "merge_state.py"),
                         "--commit-message", "test: merge state [skip ci]",
                         "--repo-dir", str(b)],
                        capture_output=True, text=True, timeout=120)
    check("merge_state exits 0 when nothing changed", r3.returncode == 0,
          f"rc={r3.returncode} out={r3.stdout[-200:]} err={r3.stderr[-200:]}")
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
