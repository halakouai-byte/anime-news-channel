#!/usr/bin/env python3
"""تست بسته ادغام لاگ — گم‌شدن خط‌های publish-log برای پیام‌های ۲۳/۲۴/۲۵.

حادثه (۲۲ نوامبر ۲۰۲۶): publish-log.md روی main فقط ۱۳ خط دارد و خط
پیام‌های ۲۳/۲۴/۲۵ در آن نیست، با اینکه state.json و archive.jsonl ثابت
می‌کنند هر سه پست شده‌اند. علت: publish.py بعد از هر پست یک خط به
publish-log.md اضافه می‌کند، ولی sync_remote_state فقط state/queue/archive
را ادغام می‌کرد — نه logs/. پس رانی با checkout کهنه، با `merge -s ours`
خط‌های تازه‌ترِ راه‌دور را بی‌صدا می‌انداخت. fetch-log خودش ترمیم می‌شود
(هر ران یک خط اضافه می‌کند)، ولی publish-log فقط موقع پست اضافه می‌شود،
پس گم‌شدن خط‌هایش ماندگار است.

این تست ثابت می‌کند: (T1) merge_log_lines خط‌ها را union می‌کند، (T2)
بازپخش حادثه با ریپوی git موقت — رانی با checkout کهنه بعد از sync، هم
خط‌های راه‌دور (۲۳/۲۴/۲۵) را دارد و هم خط محلی خودش را، و merge_state.py
آن‌ها را بدون گم‌کردن push می‌کند.

اجرا: /tmp/anime-venv2/bin/python scripts/test_log_merge.py
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import merge_log_lines, sync_remote_state  # noqa: E402

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


def line(mid, ts, guid="https://example.com/news/1"):
    return (f"- {ts} UTC (1 آذر 1405، تهران): posted message_id={mid} "
            f"guid={guid} category=فصل جدید score=45 breaking=False latency_min=1.0")


# --- T1: merge_log_lines — واحد ---
print("T1 merge_log_lines")
L21 = line(21, "2026-11-22T11:33:05Z")
L22 = line(22, "2026-11-22T11:48:06Z")
L23 = line(23, "2026-11-22T12:03:07Z")
L24 = line(24, "2026-11-22T12:18:08Z")
L25 = line(25, "2026-11-22T16:04:57Z")
L26 = line(26, "2026-11-22T17:00:00Z")
check("union keeps both sides", merge_log_lines([L21, L22], [L22, L23]) == [L21, L22, L23])
check("identical line deduped", merge_log_lines([L21, L21], [L21]) == [L21])
check("out-of-order lines get sorted",
      merge_log_lines([L23, L21], [L22]) == [L21, L22, L23])
check("cap keeps the newest",
      merge_log_lines([L21, L22, L23], [L24], cap=3) == [L22, L23, L24])
check("line without timestamp sorts first and does not crash",
      merge_log_lines(["# header", L21], [L22])[0] == "# header")
check("empty inputs give empty output", merge_log_lines([], []) == [])
check("blank lines dropped", merge_log_lines(["", L21], ["  "]) == [L21])

# --- T2: بازپخش حادثه با ریپوی git موقت ---
print("T2 temp git repo: stale checkout + log merge + merge_state push")


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"git {' '.join(args)} in {cwd}: {r.stderr}"
    return r.stdout.strip()


def _write_tree(repo, ids, log_lines):
    d = repo / "data"
    d.mkdir(parents=True, exist_ok=True)
    (d / "state.json").write_text(json.dumps({
        "posted_message_ids": ids, "posted_hashes": {},
        "story_keys": {}, "seen_guids": [], "seen_at": {},
        "recent_titles": [], "last_publish_utc": "2026-11-22T16:04:57Z",
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
    (repo / "logs" / "publish-log.md").write_text(
        "\n".join(log_lines) + "\n", encoding="utf-8")
    (repo / "logs" / "fetch-log.md").write_text("", encoding="utf-8")


tmp = Path(tempfile.mkdtemp(prefix="log-merge-"))
try:
    _git(tmp, "init", "--bare", "remote.git")
    remote = tmp / "remote.git"
    # A = رانی که پیام‌های ۲۱ و ۲۲ را پست کرده و push کرده است
    a = tmp / "A"
    _git(tmp, "clone", "remote.git", "A")
    _git(a, "config", "user.name", "test")
    _git(a, "config", "user.email", "test@example.com")
    _git(a, "checkout", "-b", "main")
    _write_tree(a, [21, 22], [L21, L22])
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v1 posted 21+22")
    _git(a, "push", "origin", "main")
    _git(tmp, "--git-dir", "remote.git", "symbolic-ref", "HEAD", "refs/heads/main")
    # B = ران بعدی: checkout همان لحظه v1 (کهنه)
    bdir = tmp / "B"
    _git(tmp, "clone", "remote.git", "B")
    _git(bdir, "config", "user.name", "test")
    _git(bdir, "config", "user.email", "test@example.com")
    # A حالا پیام‌های ۲۳/۲۴/۲۵ را پست می‌کند و push می‌کند
    _write_tree(a, [21, 22, 23, 24, 25], [L21, L22, L23, L24, L25])
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v2 posted 23+24+25")
    _git(a, "push", "origin", "main")
    # B یک پست محلی می‌فرستد (پیام ۲۶) و خطش را به لاگ کهنه اضافه می‌کند
    blog = bdir / "logs" / "publish-log.md"
    blog.write_text(blog.read_text(encoding="utf-8") + L26 + "\n", encoding="utf-8")
    # T2a: sync در B باید خط‌های راه‌دور (۲۳/۲۴/۲۵) را بیاورد، نه اینکه بیندازد
    ok = sync_remote_state(state_path=bdir / "data" / "state.json",
                           queue_path=bdir / "data" / "queue.json",
                           archive_path=bdir / "data" / "archive.jsonl",
                           repo_dir=bdir)
    merged = blog.read_text(encoding="utf-8").splitlines()
    check("sync succeeds", ok)
    check("stale checkout keeps remote lines 23/24/25 after sync",
          all(x in merged for x in (L23, L24, L25)), f"got {len(merged)} lines")
    check("stale checkout keeps its own line 26",
          L26 in merged, f"got {len(merged)} lines")
    check("merged log is the union, sorted by timestamp",
          merged == [L21, L22, L23, L24, L25, L26], f"got {merged}")
    # T2b: merge_state.py خط‌ها را بدون گم‌کردن push می‌کند
    r = subprocess.run([sys.executable,
                        str(Path(__file__).resolve().parent / "merge_state.py"),
                        "--commit-message", "test: merge log [skip ci]",
                        "--repo-dir", str(bdir)],
                       capture_output=True, text=True, timeout=120)
    check("merge_state.py exits 0", r.returncode == 0,
          f"rc={r.returncode} out={r.stdout[-300:]} err={r.stderr[-300:]}")
    main_log = _git(tmp, "--git-dir", "remote.git", "show",
                    "main:logs/publish-log.md").splitlines()
    check("main publish-log now has all six lines (21..26)",
          main_log == [L21, L22, L23, L24, L25, L26], f"got {main_log}")
finally:
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
