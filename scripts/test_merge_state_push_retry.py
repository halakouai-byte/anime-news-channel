#!/usr/bin/env python3
"""تست push-retry در merge_state.py — حادثه پیام ۶۵، ران ۴۵۳۵۶۰۰۰۲۶۳
(۲۴ نوامبر ۲۰۲۶).

بازپخش حادثه:
- ورکر انتشار (Publish #58) پیام ۶۵ را فرستاد؛ قدم ۵ در تلاش اول push
  را خورد (remote در فاصله ۱۵ دقیقه‌ایِ pacing جلو رفته بود — پنج
  کامیت بسته نقد ۴: 15e59c0 تا c931dc0).
- تلاش دوم «nothing to commit» دید و با return 0 بیرون رفت — بدون
  اینکه push کند. state پیام ۶۵ هرگز به main نرسید؛ ران بعد
  (Publish #59) همان خبر را دوباره فرستاد (پیام ۶۶، تکراری).
- علت: «nothing to commit» یعنی درختِ کاری تمیز است، نه اینکه چیزی
  برای push نیست — کامیتِ push‌نشده تلاش اول هنوز جلوتر از
  origin/main بود.

اصلاح: قدم ۳ فقط وقتی چیزی برای کامیت هست کامیت می‌کند؛ merge + push
همیشه اجرا می‌شوند (حتی وقتی چیزی تازه نیست). قدم ۳٫۵ (برگرداندن
فایل‌های غیر‌داده) هم در هر تلاش اجرا می‌شود تا merge در تلاشِ دوباره،
تغییرهای کد/داکِ راه‌دور را برنگرداند.

اجرا: python3 scripts/test_merge_state_push_retry.py (از ریشه ریپو)
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


def _git(cwd, *args):
    r = subprocess.run(["git", "-C", str(cwd), *args],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"git {' '.join(args)} in {cwd}: {r.stderr}"
    return r.stdout.strip()


def _state(ids):
    return {
        "posted_message_ids": ids,
        "posted_hashes": {f"H-{i}": i for i in ids},
        "story_keys": {}, "seen_guids": [], "seen_at": {},
        "recent_titles": [], "last_publish_utc": "2026-11-24T06:54:58Z",
        "counters": {"posts_total": len(ids), "duplicates_total": 0,
                     "rejected_total": 0, "hold_total": 0,
                     "posts_today": len(ids),
                     "posts_today_date": "2026-11-24"},
        "template_usage_7d": {},
        "circuit_breaker": {"active": False, "activated_at": None,
                            "posts_today": 0, "queue_size": 0},
    }


def _write_base(repo, rank, readme, ids):
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / "data").mkdir(parents=True, exist_ok=True)
    (repo / "logs").mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "common.py").write_text(
        f'_STATUS_RANK = {rank}\n', encoding="utf-8")
    (repo / "README.md").write_text(readme, encoding="utf-8")
    (repo / "data" / "state.json").write_text(
        json.dumps(_state(ids), ensure_ascii=False), encoding="utf-8")
    (repo / "data" / "queue.json").write_text(
        json.dumps({"version": 1, "items": []}, ensure_ascii=False),
        encoding="utf-8")
    (repo / "data" / "archive.jsonl").write_text("", encoding="utf-8")
    (repo / "logs" / "fetch-log.md").write_text("", encoding="utf-8")
    (repo / "logs" / "publish-log.md").write_text("", encoding="utf-8")


def _run_merge_state(repo, msg):
    return subprocess.run(
        [sys.executable,
         str(Path(__file__).resolve().parent / "merge_state.py"),
         "--commit-message", msg, "--repo-dir", str(repo)],
        capture_output=True, text=True, timeout=120)


def _show(remote, ref_path):
    r = subprocess.run(["git", "-C", str(remote), "--git-dir", "remote.git",
                        "show", f"main:{ref_path}"],
                       capture_output=True, text=True, timeout=60)
    return r.stdout if r.returncode == 0 else None


OLD_RANK = '{"POSTED": 4, "STALE": 3, "HOLD": 2, "QUEUED": 1}'
NEW_RANK = '{"POSTED": 4, "STALE": 3, "REJECTED": 3, "EXPIRED": 3, "HOLD": 2, "QUEUED": 1}'

tmp = Path(tempfile.mkdtemp(prefix="merge-push-retry-"))
try:
    _git(tmp, "init", "--bare", "remote.git")
    remote = tmp / "remote.git"
    # A = مدیر: پایه کهنه (رتبه قدیم) را می‌سازد و push می‌کند
    a = tmp / "A"
    _git(tmp, "clone", "remote.git", "A")
    _git(a, "config", "user.name", "test")
    _git(a, "config", "user.email", "test@example.com")
    _git(a, "checkout", "-b", "main")
    _write_base(a, OLD_RANK, "README — 57 posts\n", [6, 7])
    _git(a, "add", ".")
    _git(a, "commit", "-m", "base: old rank")
    _git(a, "push", "origin", "main")
    _git(tmp, "--git-dir", "remote.git", "symbolic-ref", "HEAD", "refs/heads/main")
    # B = ورکر: checkout همان لحظه پایه (کهنه)؛ پیام ۶۵ را «می‌فرستد» و
    # state را محلی کامیت می‌کند (تلاش اول merge_state: کامیت ساخته شد
    # ولی push خورد — اینجا با کامیت دستی شبیه‌سازی می‌شود).
    b = tmp / "B"
    _git(tmp, "clone", "remote.git", "B")
    _git(b, "config", "user.name", "test")
    _git(b, "config", "user.email", "test@example.com")
    b_state = json.loads((b / "data" / "state.json").read_text(encoding="utf-8"))
    b_state["posted_message_ids"].append(65)
    b_state["posted_hashes"]["H-65"] = 65
    b_state["counters"]["posts_total"] = 3
    (b / "data" / "state.json").write_text(
        json.dumps(b_state, ensure_ascii=False), encoding="utf-8")
    _git(b, "add", "data/state.json")
    _git(b, "commit", "-m", "publish: message 65 (unpushed)")
    # A حالا بسته نقد ۴ را push می‌کند (remote جلو می‌رود — مثل پنج
    # کامیت بسته در فاصله pacing ران #58): فقط کد/داک، نه data.
    _write_base(a, NEW_RANK, "README — 57 posts\n", [6, 7])
    _git(a, "add", ".")
    _git(a, "commit", "-m", "bundle: review #4 fixes")
    _git(a, "push", "origin", "main")

    # --- T1: merge_state روی B (درخت کاری تمیز، ولی HEAD جلوتر از remote)
    # باید state پیام ۶۵ را push کند، نه اینکه «nothing to commit» بگوید
    # و با موفقیتِ دروغین بیرون برود.
    print("T1 unpushed local commit must be pushed, not swallowed")
    r = _run_merge_state(b, "publish: update state/queue/archive [skip ci]")
    check("merge_state.py exits 0", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[-300:]}")
    main_state = json.loads(_show(tmp, "data/state.json"))
    check("message 65 is on main (state was pushed)",
          65 in main_state["posted_message_ids"],
          f"got {main_state['posted_message_ids']}")
    check("bundle code change survives on main (restore ran on retry)",
          _show(tmp, "scripts/common.py") is not None
          and NEW_RANK in _show(tmp, "scripts/common.py"),
          f"got {(_show(tmp, 'scripts/common.py') or '')[:80]}")
    check("remote README survives on main",
          (_show(tmp, "README.md") or "").find("57 posts") >= 0)

    # --- T2: اجرای دوباره وقتی همه‌چیز همگام است — خروج ۰، بدون کامیت اضافه ---
    print("T2 no-op when already in sync")
    before = _git(tmp, "--git-dir", "remote.git", "rev-parse", "main")
    r = _run_merge_state(b, "publish: update state/queue/archive [skip ci]")
    check("merge_state.py exits 0 with nothing to do", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[-300:]}")
    after = _git(tmp, "--git-dir", "remote.git", "rev-parse", "main")
    check("no extra commit was created", before == after,
          f"before={before} after={after}")
    check("nothing-to-commit is logged",
          "nothing to commit" in r.stdout, f"got {r.stdout[-200:]}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
