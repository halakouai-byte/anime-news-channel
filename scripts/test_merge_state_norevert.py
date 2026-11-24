#!/usr/bin/env python3
"""تست برگرداندن فایل‌های غیر‌داده در merge_state.py — حادثه ۲۴ نوامبر ۲۰۲۶.

بازپخش حادثه (مرج 3c34da3):
- بسته نقد ۴ ساعت ۰۶:۵۷–۰۶:۵۹ UTC در سه کامیت نشست (رتبه وضعیت،
  بانک v1.3، تست‌ها، README، AGENTS.md).
- ورکر انتشار ساعت ۰۷:۰۹:۵۹ UTC از کلون کهنه (55bc1b5، پیش از بسته)
  push کرد؛ `merge -s ours` درخت کهنه را کامل نگه داشت و تغییرهای
  کد/داکِ راه‌دور از main برگشتند. داده‌ها سالم ماندند چون
  sync_remote_state آن‌ها را union می‌کند — ولی کد و داک برگشتند.

اصلاح (قدم ۳٫۵ در merge_state.py): پیش از `merge -s ours`، همه
فایل‌های غیر از data/ و logs/ از origin/main برگردانده می‌شوند
(محتوا + حذف‌ها) و به همان کامیت اضافه می‌شوند. ورکر فقط data/
و logs/ را مالک است و هرگز نباید چیز دیگری را برگرداند.

اجرا: /tmp/anime-venv2/bin/python scripts/test_merge_state_norevert.py
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


def _write_repo(repo, code_rank, readme, state_ids, archive_rows):
    (repo / "scripts").mkdir(parents=True, exist_ok=True)
    (repo / "data").mkdir(parents=True, exist_ok=True)
    (repo / "logs").mkdir(parents=True, exist_ok=True)
    (repo / "scripts" / "common.py").write_text(
        f'_STATUS_RANK = {code_rank}\n', encoding="utf-8")
    (repo / "README.md").write_text(readme, encoding="utf-8")
    (repo / "data" / "state.json").write_text(json.dumps({
        "posted_message_ids": state_ids,
        "posted_hashes": {f"H-{i}": i for i in state_ids},
        "story_keys": {}, "seen_guids": [], "seen_at": {},
        "recent_titles": [], "last_publish_utc": "2026-11-24T06:54:58Z",
        "counters": {"posts_total": len(state_ids), "duplicates_total": 0,
                     "rejected_total": 0, "hold_total": 0,
                     "posts_today": len(state_ids),
                     "posts_today_date": "2026-11-24"},
        "template_usage_7d": {},
        "circuit_breaker": {"active": False, "activated_at": None,
                            "posts_today": 0, "queue_size": 0},
    }, ensure_ascii=False), encoding="utf-8")
    (repo / "data" / "queue.json").write_text(
        json.dumps({"version": 1, "items": []}, ensure_ascii=False),
        encoding="utf-8")
    (repo / "data" / "archive.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in archive_rows),
        encoding="utf-8")
    (repo / "logs" / "fetch-log.md").write_text("", encoding="utf-8")
    (repo / "logs" / "publish-log.md").write_text("", encoding="utf-8")


def _run_merge_state(repo, msg):
    return subprocess.run(
        [sys.executable,
         str(Path(__file__).resolve().parent / "merge_state.py"),
         "--commit-message", msg, "--repo-dir", str(repo)],
        capture_output=True, text=True, timeout=120)


def _show(remote, ref_path):
    """محتوای فایل روی main راه‌دور؛ None اگر فایل نیست (برای چک
    «فایل هست» — نبودن فایل خودش یک FAIL است، نه کرش تست)."""
    r = subprocess.run(["git", "-C", str(remote), "--git-dir", "remote.git",
                        "show", f"main:{ref_path}"],
                       capture_output=True, text=True, timeout=60)
    return r.stdout if r.returncode == 0 else None


OLD_RANK = '{"POSTED": 4, "STALE": 3, "HOLD": 2, "QUEUED": 1}'
NEW_RANK = '{"POSTED": 4, "STALE": 3, "REJECTED": 3, "EXPIRED": 3, "HOLD": 2, "QUEUED": 1}'

tmp = Path(tempfile.mkdtemp(prefix="merge-norevert-"))
try:
    _git(tmp, "init", "--bare", "remote.git")
    remote = tmp / "remote.git"
    # A = مدیر: v1 (پایه کهنه) را می‌سازد و push می‌کند
    a = tmp / "A"
    _git(tmp, "clone", "remote.git", "A")
    _git(a, "config", "user.name", "test")
    _git(a, "config", "user.email", "test@example.com")
    _git(a, "checkout", "-b", "main")
    _write_repo(a, OLD_RANK, "README — 55 posts\n", [6, 7],
                [{"message_id": 6, "status": "posted", "caption": "old caption 6"},
                 {"message_id": 7, "status": "posted", "caption": "Bleach caption 7"}])
    _git(a, "add", ".")
    _git(a, "commit", "-m", "v1 stale base")
    _git(a, "push", "origin", "main")
    _git(tmp, "--git-dir", "remote.git", "symbolic-ref", "HEAD", "refs/heads/main")
    # B = ورکر: checkout همان لحظه v1 (کهنه) — کلون کهنه حادثه
    b = tmp / "B"
    _git(tmp, "clone", "remote.git", "B")
    _git(b, "config", "user.name", "test")
    _git(b, "config", "user.email", "test@example.com")
    # A حالا بسته نقد ۴ را push می‌کند: رتبه تازه + فایل تازه + README
    # تازه + اصلاح کپشن آرشیو (پیام ۷: Bleach → Zatsuyou)
    _write_repo(a, NEW_RANK, "README — 56 posts\n", [6, 7],
                [{"message_id": 6, "status": "posted", "caption": "old caption 6"},
                 {"message_id": 7, "status": "posted", "caption": "Zatsuyou caption 7"}])
    (a / "scripts" / "test_status_rank.py").write_text(
        "# new test file\n", encoding="utf-8")
    _git(a, "add", ".")
    _git(a, "commit", "-m", "bundle: review #4 fixes")
    _git(a, "push", "origin", "main")

    # --- T1: ورکر (کلون کهنه) یک پست تازه می‌فرستد و merge_state push می‌کند ---
    print("T1 stale worker push must not revert the bundle")
    b_state = json.loads((b / "data" / "state.json").read_text(encoding="utf-8"))
    b_state["posted_message_ids"].append(8)
    b_state["posted_hashes"]["H-8"] = 8
    b_state["counters"]["posts_total"] = 3
    (b / "data" / "state.json").write_text(
        json.dumps(b_state, ensure_ascii=False), encoding="utf-8")
    with open(b / "data" / "archive.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"message_id": 8, "status": "posted",
                            "caption": "new post 8"}, ensure_ascii=False) + "\n")
    r = _run_merge_state(b, "publish: update state/queue/archive [skip ci]")
    check("merge_state.py exits 0", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[-300:]}")
    check("bundle code change survives (new rank on main)",
          _show(tmp, "scripts/common.py") is not None
          and NEW_RANK in _show(tmp, "scripts/common.py"),
          f"got {(_show(tmp, 'scripts/common.py') or '')[:80]}")
    check("bundle new file survives on main",
          (_show(tmp, "scripts/test_status_rank.py") or "").strip() == "# new test file")
    check("bundle README survives on main",
          (_show(tmp, "README.md") or "").find("56 posts") >= 0)
    main_state = json.loads(_show(tmp, "data/state.json"))
    check("worker post 8 is on main",
          8 in main_state["posted_message_ids"],
          f"got {main_state['posted_message_ids']}")
    main_archive = _show(tmp, "data/archive.jsonl") or ""
    check("bundle archive caption fix survives (Zatsuyou, not Bleach)",
          "Zatsuyou caption 7" in main_archive and "Bleach caption 7" not in main_archive,
          f"got {main_archive[:200]}")
    check("worker archive row 8 is on main",
          '"message_id": 8' in main_archive)

    # --- T2: حذف راه‌دور نباید برگردد ---
    print("T2 remote deletion must not be resurrected")
    _git(a, "pull", "--ff-only", "origin", "main")
    # یک فایل موقت روی main می‌سازیم و push می‌کنیم؛ B هم آن را
    # می‌گیرد (مثل کلونی که فایل را دیده)، بعد A حذفش می‌کند.
    (a / "scripts" / "todelete.py").write_text("# temp\n", encoding="utf-8")
    _git(a, "add", ".")
    _git(a, "commit", "-m", "add a temp file")
    _git(a, "push", "origin", "main")
    _git(b, "fetch", "origin", "main")
    _git(b, "checkout", "origin/main", "--", "scripts/todelete.py")
    _git(a, "rm", "-q", "scripts/todelete.py")
    _git(a, "commit", "-m", "remove the temp file")
    _git(a, "push", "origin", "main")
    # B یک پست دیگر می‌فرستد (درختش هنوز فایل حذف‌شده را دارد)
    b_state = json.loads((b / "data" / "state.json").read_text(encoding="utf-8"))
    b_state["posted_message_ids"].append(9)
    b_state["posted_hashes"]["H-9"] = 9
    b_state["counters"]["posts_total"] = 4
    (b / "data" / "state.json").write_text(
        json.dumps(b_state, ensure_ascii=False), encoding="utf-8")
    r = _run_merge_state(b, "publish: update state/queue/archive [skip ci]")
    check("merge_state.py exits 0 on the deletion run", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[-300:]}")
    ls = _git(tmp, "--git-dir", "remote.git", "ls-tree", "-r", "--name-only", "main")
    check("deleted file stays deleted on main",
          "scripts/todelete.py" not in ls.splitlines(), f"got {ls}")
    main_state = json.loads(_show(tmp, "data/state.json"))
    check("worker post 9 is on main",
          9 in main_state["posted_message_ids"])
    check("bundle code still survives after the deletion run",
          _show(tmp, "scripts/common.py") is not None
          and NEW_RANK in _show(tmp, "scripts/common.py"))

    # --- T3: وقتی چیزی برای برگرداندن نیست، خروج ۰ و بدون کامیت اضافه ---
    print("T3 no-op when already up to date")
    r = _run_merge_state(b, "publish: update state/queue/archive [skip ci]")
    check("merge_state.py exits 0 with nothing to commit", r.returncode == 0,
          f"rc={r.returncode} err={r.stderr[-300:]}")
    check("no extra commit was created",
          "nothing to commit" in r.stdout,
          f"got {r.stdout[-200:]}")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
