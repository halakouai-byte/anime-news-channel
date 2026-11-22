#!/usr/bin/env python3
"""تست بسته ضد مسابقه — پست‌های فانتوم ۱۵ و ۱۶ (۲۲ نوامبر ۲۰۲۶).

بازپخش حادثه:
- سویپر ۴۵۰۰۳۶۸۸۳۸۳ با checkout کهنه (SHA زمان ساخت، پیش از 26b8fd8)
  پیام ۱۵ (AnimeCorner، فصل ۵ Elite — کلید date) و پیام ۱۶ (MAL
  74967203، همان آیتم پیام ۱۳) را فرستاد؛ کامیتش روی rebase مرد.
- ران ۱۰:۰۱ همان آیتم AnimeCorner را دوباره به‌عنوان پیام ۱۷ پست کرد.

اجرا: /tmp/anime-venv2/bin/python scripts/test_race_phantom.py
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (merge_archive_lines, merge_queue_data,
                    merge_state_data, same_story_key, sync_remote_state)
from publish import _find_posted_duplicate

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


# --- T1: خانواده رونمایی در same_story_key ---
print("T1 reveal family")
check("announcement == date", same_story_key("classroom elite|announcement|10389",
                                              "classroom elite|date|10389"))
check("announcement == trailer", same_story_key("classroom elite|announcement|10389",
                                                 "classroom elite|trailer|10389"))
check("date == trailer", same_story_key("classroom elite|date|10389",
                                        "classroom elite|trailer|10389"))
check("announcement != casting", not same_story_key("classroom elite|announcement|10389",
                                                     "classroom elite|casting|10389"))
check("announcement != license", not same_story_key("classroom elite|announcement|10389",
                                                     "classroom elite|license|10389"))
check("casting != trailer", not same_story_key("tougen anki|casting|10388",
                                               "tougen anki|trailer|10388"))
check("generic wildcard still works", same_story_key("bang dream|event|10388",
                                                      "bang dream|announcement|10389"))
check("different franchise no match", not same_story_key("classroom elite|date|10389",
                                                         "tougen anki|date|10389"))
check("bucket >1 no match", not same_story_key("classroom elite|date|10389",
                                               "classroom elite|date|10391"))
check("bucket +-1 still matches", same_story_key("classroom elite|date|10388",
                                                  "classroom elite|announcement|10389"))

# --- T2: بازپخش Elite — گارد لحظه انتشار آیتم AnimeCorner را می‌گیرد ---
print("T2 Elite replay: publish guard catches the AnimeCorner date item")
queue = {"version": 1, "items": [
    {"guid": "mal-74967203", "hash": "H-mal-elite",
     "title": "'Youkoso Jitsuryoku Shijou Shugi no Kyoushitsu e 5th Season: "
              "2-nensei-hen 2 Gakki' Airs in 2027",
     "status": "POSTED", "message_id": 13,
     "story_key": "classroom elite|trailer|10389"},
]}
state = {"posted_hashes": {"H-mal-elite": 13},
         "story_keys": {"classroom elite|trailer|10389":
                        {"message_id": 13, "posted_utc": "2026-11-22T08:33:00Z"}}}
animecorner = {"guid": "ac-elite-s5", "hash": "H-ac-elite",
               "title": "Classroom of the Elite Season 5 Announces 2027 Premiere Date",
               "status": "QUEUED", "story_key": "classroom elite|date|10389"}
dup = _find_posted_duplicate(animecorner, queue, state)
check("AnimeCorner date item is a duplicate of msg 13", dup is not None
      and dup.get("message_id") == 13, f"got {dup}")
ann = {"guid": "ann-elite-s5", "hash": "H-ann-elite",
       "title": "Classroom of the Elite Anime's 5th Season Reveals Full Title, "
                "Visual, 2027 Debut",
       "status": "HOLD", "story_key": "classroom elite|announcement|10389"}
dup2 = _find_posted_duplicate(ann, queue, state)
check("ANN announcement item is a duplicate of msg 13", dup2 is not None
      and dup2.get("message_id") == 13, f"got {dup2}")
tougen = {"guid": "mal-tougen", "hash": "H-tougen",
          "title": "Tougen Anki: Nikko Kegon no Taki-hen Unveils Additional Cast",
          "status": "QUEUED", "story_key": "anki tougen|casting|10388"}
check("Tougen Anki casting is NOT a duplicate", _find_posted_duplicate(tougen, queue, state) is None)

# --- T3: merge_state_data — union، نه rebase ---
print("T3 merge_state_data")
local = {"posted_message_ids": [6, 7, 8, 9, 10, 11, 12],
         "posted_hashes": {"H-a": 6, "H-b": 7},
         "story_keys": {"fr|announcement|10388": {"message_id": 10,
                                                   "posted_utc": "2026-11-22T01:00:00Z"}},
         "seen_guids": ["g1"], "seen_at": {"H-a": "2026-11-22T00:00:00Z"},
         "recent_titles": [{"title_norm": "x", "posted_utc": "2026-11-22T00:00:00Z"}],
         "last_publish_utc": "2026-11-22T01:30:00Z",
         "counters": {"posts_total": 7, "duplicates_total": 3,
                      "rejected_total": 100, "hold_total": 5,
                      "posts_today": 7, "posts_today_date": "2026-11-22"},
         "template_usage_7d": {"lead_01": ["2026-11-22T00:00:00Z"]},
         "circuit_breaker": {"active": False, "activated_at": None,
                             "posts_today": 7, "queue_size": 10}}
remote = {"posted_message_ids": [6, 7, 8, 9, 10, 11, 12, 13, 14],
          "posted_hashes": {"H-a": 6, "H-mal-elite": 13},
          "story_keys": {"classroom elite|trailer|10389":
                         {"message_id": 13, "posted_utc": "2026-11-22T08:33:00Z"}},
          "seen_guids": ["g1", "g2"], "seen_at": {"H-mal-elite": "2026-11-22T08:33:00Z"},
          "recent_titles": [{"title_norm": "y", "posted_utc": "2026-11-22T08:33:00Z"}],
          "last_publish_utc": "2026-11-22T08:48:01Z",
          "counters": {"posts_total": 9, "duplicates_total": 5,
                       "rejected_total": 100, "hold_total": 6,
                       "posts_today": 9, "posts_today_date": "2026-11-22"},
          "template_usage_7d": {"lead_01": ["2026-11-22T08:33:00Z"],
                                "lead_02": ["2026-11-22T08:33:00Z"]},
          "circuit_breaker": {"active": False, "activated_at": None,
                              "posts_today": 9, "queue_size": 4}}
m = merge_state_data(local, remote)
check("posted ids are the union", m["posted_message_ids"] == [6, 7, 8, 9, 10, 11, 12, 13, 14],
      f"got {m['posted_message_ids']}")
check("posted hashes are the union", m["posted_hashes"] == {"H-a": 6, "H-b": 7, "H-mal-elite": 13},
      f"got {m['posted_hashes']}")
check("story keys are the union", len(m["story_keys"]) == 2)
check("posts_total recomputed from ids", m["counters"]["posts_total"] == 9,
      f"got {m['counters']['posts_total']}")
check("last_publish_utc is the max", m["last_publish_utc"] == "2026-11-22T08:48:01Z")
check("monotonic counters take max", m["counters"]["duplicates_total"] == 5
      and m["counters"]["hold_total"] == 6)
# درگیری هش: remote برنده است (اولین پست، مرجع است)
conflict = merge_state_data({"posted_hashes": {"H-x": 16}},
                            {"posted_hashes": {"H-x": 13}})
check("hash conflict keeps remote (first post)", conflict["posted_hashes"]["H-x"] == 13)

# --- T4: merge_queue_data — وضعیت پیشرفته‌تر می‌برد ---
print("T4 merge_queue_data")
lq = {"version": 1, "items": [
    {"guid": "g-elite", "hash": "H-mal-elite", "status": "POSTED", "message_id": 16},
    {"guid": "g-hold", "hash": "H-hold", "status": "HOLD", "hold_reason": "gates_failed:x"},
    {"guid": "g-local-only", "hash": "H-lo", "status": "QUEUED"},
]}
rq = {"version": 1, "items": [
    {"guid": "g-elite", "hash": "H-mal-elite", "status": "POSTED", "message_id": 13},
    {"guid": "g-hold", "hash": "H-hold", "status": "QUEUED"},
    {"guid": "g-remote-only", "hash": "H-ro", "status": "QUEUED"},
]}
mq = merge_queue_data(lq, rq)
by_guid = {i["guid"]: i for i in mq["items"]}
check("phantom POSTED keeps remote message_id 13 (first post)",
      by_guid["g-elite"]["message_id"] == 13, f"got {by_guid['g-elite']}")
check("local HOLD beats remote QUEUED", by_guid["g-hold"]["status"] == "HOLD")
check("local-only item kept", "g-local-only" in by_guid)
check("remote-only item kept", "g-remote-only" in by_guid)
check("4 items total", len(mq["items"]) == 4, f"got {len(mq['items'])}")
# POSTED راه‌دور، QUEUED محلی را بازنویسی نمی‌کند
mq2 = merge_queue_data({"items": [{"guid": "g2", "hash": "H2", "status": "QUEUED"}]},
                       {"items": [{"guid": "g2", "hash": "H2", "status": "POSTED", "message_id": 17}]})
check("remote POSTED beats local QUEUED",
      mq2["items"][0]["status"] == "POSTED" and mq2["items"][0]["message_id"] == 17)

# --- T5: merge_archive_lines ---
print("T5 merge_archive_lines")
local_lines = ['{"guid": "a", "hash": "H1", "status": "posted", "message_id": 13, "archived_utc": "2026-11-22T08:33:00Z"}']
remote_lines = ['{"guid": "a", "hash": "H1", "status": "posted", "message_id": 13, "archived_utc": "2026-11-22T08:33:00Z"}',
                '{"guid": "b", "hash": "H2", "status": "posted", "message_id": 14, "archived_utc": "2026-11-22T08:48:01Z"}']
merged_lines = merge_archive_lines(local_lines, remote_lines)
check("archive union dedupes identical rows", len(merged_lines) == 2, f"got {len(merged_lines)}")
# همان هش با دو message_id (فانتوم): هر دو ردیف می‌مانند
phantom = merge_archive_lines(
    ['{"guid": "a", "hash": "H1", "status": "posted", "message_id": 16, "archived_utc": "2026-11-22T09:03:26Z"}'],
    ['{"guid": "a", "hash": "H1", "status": "posted", "message_id": 13, "archived_utc": "2026-11-22T08:33:00Z"}'])
check("phantom double-post keeps both archive rows", len(phantom) == 2, f"got {len(phantom)}")

# --- T6 + T7: بازپخش کامل با ریپوی git موقت ---
print("T6+T7 temp git repo: stale checkout + merge_state push")


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"git {' '.join(args)} in {cwd}: {r.stderr}"
    return r.stdout.strip()


def _write_state(repo, ids, hashes):
    d = repo / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({
        "posted_message_ids": ids, "posted_hashes": hashes,
        "story_keys": {}, "seen_guids": [], "seen_at": {},
        "recent_titles": [], "last_publish_utc": "2026-11-22T08:48:01Z",
        "counters": {"posts_total": len(ids), "duplicates_total": 0,
                     "rejected_total": 0, "hold_total": 0,
                     "posts_today": len(ids), "posts_today_date": "2026-11-22"},
        "template_usage_7d": {},
        "circuit_breaker": {"active": False, "activated_at": None,
                            "posts_today": 0, "queue_size": 0},
    }, ensure_ascii=False), encoding="utf-8")
    (d / "queue.json").write_text(json.dumps({"version": 1, "items": []},
                                             ensure_ascii=False), encoding="utf-8")
    (d / "archive.jsonl").write_text("", encoding="utf-8")
    (repo / "logs").mkdir(exist_ok=True)
    (repo / "logs" / "fetch-log.md").write_text("", encoding="utf-8")


tmp = Path(tempfile.mkdtemp(prefix="race-phantom-"))
try:
    _git(tmp, "init", "--bare", "remote.git")
    remote = tmp / "remote.git"
    # A = ران publish: اول state کهنه (پست‌های ۶ تا ۱۲)، بعد state تازه (۱۳ و ۱۴)
    a = tmp / "A"
    _git(tmp, "clone", "remote.git", "A")
    _git(a, "config", "user.name", "test")
    _git(a, "config", "user.email", "test@example.com")
    _git(a, "checkout", "-b", "main")
    _write_state(a, [6, 7, 8, 9, 10, 11, 12], {})
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v1 stale base")
    _git(a, "push", "origin", "main")
    _git(tmp, "--git-dir", "remote.git", "symbolic-ref", "HEAD", "refs/heads/main")
    # B = سویپر: checkout همان لحظه v1 (کهنه) — قبل از اینکه A پست‌های ۱۳/۱۴ را push کند
    b = tmp / "B"
    _git(tmp, "clone", "remote.git", "B")
    _git(b, "config", "user.name", "test")
    _git(b, "config", "user.email", "test@example.com")
    # A حالا ۱۳ و ۱۴ را push می‌کند (26b8fd8 در حادثه واقعی)
    _write_state(a, [6, 7, 8, 9, 10, 11, 12, 13, 14],
                 {"H-mal-elite": 13, "H-duel": 14})
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v2 posted 13+14")
    _git(a, "push", "origin", "main")
    # T6: sync در B رکوردهای ۱۳/۱۴ را می‌آورد (قبل از اصلاح، B آن‌ها را نمی‌دید)
    ok = sync_remote_state(state_path=b / "data" / "state.json",
                           queue_path=b / "data" / "queue.json",
                           archive_path=b / "data" / "archive.jsonl",
                           repo_dir=b)
    b_state = json.loads((b / "data" / "state.json").read_text(encoding="utf-8"))
    check("sync succeeds", ok)
    check("stale checkout sees remote posts 13+14 after sync",
          13 in b_state["posted_message_ids"] and 14 in b_state["posted_message_ids"],
          f"got {b_state['posted_message_ids']}")
    check("stale checkout sees remote hash H-mal-elite after sync",
          b_state["posted_hashes"].get("H-mal-elite") == 13)
    check("posts_total recomputed to 9", b_state["counters"]["posts_total"] == 9,
          f"got {b_state['counters']['posts_total']}")
    # T7: B رکورد محلی خودش را اضافه می‌کند (پیام‌های ۱۵/۱۶ سویپر) و merge_state push می‌کند
    b_state["posted_message_ids"].append(15)
    b_state["posted_message_ids"].append(16)
    b_state["posted_hashes"]["H-ac-elite"] = 15
    b_state["counters"]["posts_total"] = 11
    (b / "data" / "state.json").write_text(
        json.dumps(b_state, ensure_ascii=False), encoding="utf-8")
    # ران دیگری هم‌زمان کامیت می‌کند (مسابقه دوم): A یک رکورد دیگر push می‌کند
    _write_state(a, [6, 7, 8, 9, 10, 11, 12, 13, 14, 17], {"H-mal-elite": 13, "H-duel": 14})
    # توجه: _write_state فایل را بازنویسی می‌کند — رکورد ۱۵/۱۶ در A نیست (درست مثل حادثه)
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v3 posted 17")
    _git(a, "push", "origin", "main")
    r = subprocess.run([sys.executable,
                        str(Path(__file__).resolve().parent / "merge_state.py"),
                        "--commit-message", "test: merge state [skip ci]",
                        "--repo-dir", str(b)],
                       capture_output=True, text=True, timeout=120)
    check("merge_state.py exits 0 despite the concurrent push",
          r.returncode == 0, f"rc={r.returncode} out={r.stdout[-300:]} err={r.stderr[-300:]}")
    main_state = json.loads(_git(tmp, "--git-dir", "remote.git", "show", "main:data/state.json"))
    check("main now has the union (13,14,15,16,17)",
          main_state["posted_message_ids"] == [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17],
          f"got {main_state['posted_message_ids']}")
    check("main keeps H-mal-elite -> 13 (first post wins)",
          main_state["posted_hashes"].get("H-mal-elite") == 13)
    check("main keeps B's H-ac-elite -> 15",
          main_state["posted_hashes"].get("H-ac-elite") == 15)
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
