#!/usr/bin/env python3
"""کامیت ضدتداخل state/queue/archive — جایگزین pull --rebase در ورک‌فلوها.

حادثه (۲۲ نوامبر ۲۰۲۶، پست‌های فانتوم ۱۵ و ۱۶): سویپر با checkout کهنه
دو پست فرستاد و کامیتش روی `git pull --rebase` مرد — rebase روی
state/queue/archive تداخل خورد، push ناممکن شد و state محلی با دو
پیام از دست رفت. state یک فایل متنی برای rebase نیست؛ رکوردهای
پست‌شده union می‌شوند (`common.merge_state_data`).

این اسکریپت همان قانون را برای کامیت پیاده می‌کند:
  1. `sync_remote_state` — fetch + ادغام union رکوردهای راه‌دور در
     فایل‌های محلی (اگر fetch نشد، با خطای بلند fail می‌شود؛ state
     محلی نجات نمی‌یابد، ولی علت روشن است).
  2. راستی‌آزمایی: همه posted_message_ids راه‌دور باید در فایل ادغام‌شده
     باشند — اگر نباشند، کامیت نمی‌شود (جلوگیری از اینکه merge بعدی
     رکورد راه‌دور را بی‌صدا بیندازد).
  3. `git add` + `git commit` (اگر چیزی برای کامیت نیست، خروج ۰).
  3.۵. برگرداندن فایل‌های غیر‌داده از راه‌دور (حادثه ۲۰۲۶-۱۱-۲۴،
     پایین را ببین) — ورکر فقط data/ و logs/ را می‌نویسد، پس بقیه
     فایل‌ها باید دقیقاً همان origin/main باشند.
  4. `git merge -s ours origin/main` — remote را به‌عنوان mergeشده
     ثبت می‌کند بدون اینکه درخت (که همین حالا union شده) را دست
     بزند؛ پس push دیگر non-fast-forward نمی‌خورد.
  5. `git push`؛ اگر خورد (ران دیگری هم‌زمان کامیت کرد)، از قدم ۱
     تکرار می‌شود (حداکثر ۳ تلاش).

حادثه دوم (۲۴ نوامبر ۲۰۲۶، مرج 3c34da3): ورکر انتشار از کلون کهنه
(55bc1b5، پیش از بسته نقد ۴) push کرد؛ `merge -s ours` درخت کهنه
را کامل نگه داشت و تغییرهای کد/داکِ راه‌دور (رتبه وضعیت، بانک v1.3،
تست‌ها، README، AGENTS.md) از main برگشتند — چون sync فقط data/ و
logs/ را union می‌کند و قدم ۴ هیچ فایلی را از راه‌دور برنمی‌گرداند.
داده‌ها سالم ماندند (union آرشیو کپشن‌های درست‌شده را نگه داشت)، ولی
کد و داک برگشتند. از آن پس قدم ۳٫۵ پیش از merge، همه فایل‌های غیر
از data/ و logs/ را از origin/main می‌گیرد (محتوا + حذف‌ها) و به
همان کامیت اضافه می‌کند — ورکر فقط data/logs را مالک است و هرگز
نباید چیز دیگری را برگرداند.

استفاده (در ورک‌فلو، بعد از git config):
  python scripts/merge_state.py --commit-message "publish: update state/queue/archive [skip ci]"
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (iso_utc, log_error, log_info, log_warn,
                    repo_root, sync_remote_state)

DATA_FILES = ["data/state.json", "data/queue.json", "data/archive.jsonl", "logs/"]


def _git(args: list[str], cwd: Path, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args],
                          capture_output=True, timeout=timeout)


def _remote_posted_ids(root: Path, ref: str) -> set[int] | None:
    """posted_message_ids راه‌دور (برای راستی‌آزمایی قدم ۲). None اگر خوانده نشد."""
    rr = _git(["show", f"{ref}:data/state.json"], root)
    if rr.returncode != 0:
        return None
    try:
        remote = json.loads(rr.stdout.decode("utf-8"))
    except ValueError:
        return None
    return set(remote.get("posted_message_ids", []))


def _remote_log_lines(root: Path, ref: str, rel: str) -> set[str] | None:
    """خط‌های لاگ راه‌دور (برای راستی‌آزمایی قدم ۲). None اگر خوانده نشد."""
    rr = _git(["show", f"{ref}:{rel}"], root)
    if rr.returncode != 0:
        return None
    return {l.strip() for l in rr.stdout.decode("utf-8").splitlines() if l.strip()}


def _non_data_files(root: Path, ref: str) -> list[str] | None:
    """فایل‌های غیر‌داده در ref (نه data/ و نه logs/)؛ None اگر خوانده نشد.
    فهرست را در پایتون فیلتر می‌کنیم چون `:!` (exclude) در بعضی
    دستورهای git پشتیبانی نمی‌شود و checkout روی pathspecِ خالی خطا
    می‌دهد (وقتی ریپو فقط data/ و logs/ دارد — مثل ریپوهای تست)."""
    rr = _git(["ls-tree", "-r", "--name-only", ref], root)
    if rr.returncode != 0:
        return None
    return [l for l in rr.stdout.decode("utf-8").splitlines()
            if l and not l.startswith("data/") and not l.startswith("logs/")]


def _restore_non_data_files(root: Path, ref: str) -> bool | None:
    """فایل‌های غیر‌داده را از ref برگردان (قدم ۳٫۵، حادثه ۲۰۲۶-۱۱-۲۴):
    `merge -s ours` درخت محلی را کامل نگه می‌دارد؛ اگر کلون کهنه
    باشد، تغییرهای کد/داکِ راه‌دور بی‌صدا برمی‌گردند — چون sync فقط
    data/ و logs/ را union می‌کند. ورکر فقط data/ و logs/ را
    می‌نویسد، پس همه فایل‌های دیگر باید دقیقاً همان ref باشند.
    محتوا را از ref می‌گیریم و فایل‌هایی را که ref حذف کرده پاک
    می‌کنیم؛ تغییرها در index می‌مانند تا caller به کامیت اضافه کند.
    True اگر چیزی تغییر کرد، False اگر چیزی برای برگرداندن نبود،
    None اگر خطا بود (caller باید abort کند، نه اینکه درخت کهنه را push کند)."""
    files = _non_data_files(root, ref)
    if files is None:
        log_error("merge_state: could not list files in " + ref)
        return None
    if files:
        co = _git(["checkout", ref, "--", *files], root)
        if co.returncode != 0:
            log_error("merge_state: checkout non-data files from " + ref + " failed: "
                      + co.stderr.decode("utf-8", "replace")[:300])
            return None
    # فایل‌های غیر‌داده که ref حذف کرده ولی در HEAD محلی هنوز هستند
    diff = _git(["diff", "--name-only", "--diff-filter=D", "HEAD", ref], root)
    if diff.returncode == 0:
        for rel in diff.stdout.decode("utf-8").splitlines():
            rel = rel.strip()
            if not rel or rel.startswith("data/") or rel.startswith("logs/"):
                continue
            rm = _git(["rm", "-q", "--", rel], root)
            if rm.returncode != 0:
                log_error(f"merge_state: git rm {rel} failed: "
                          + rm.stderr.decode("utf-8", "replace")[:300])
                return None
    return _git(["diff", "--cached", "--quiet"], root).returncode != 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="merge-based commit of state/queue/archive (anti-race)")
    ap.add_argument("--commit-message", required=True,
                    help="پیام کامیت state (مثل publish: update state/queue/archive [skip ci])")
    ap.add_argument("--attempts", type=int, default=3,
                    help="حداکثر تلاش push (پیش‌فرض ۳)")
    ap.add_argument("--ref", default="origin/main",
                    help="مرجع راه‌دور (پیش‌فرض origin/main)")
    ap.add_argument("--repo-dir", default=None,
                    help="ریپو (پیش‌فرض: ریپوی همین اسکریپت؛ برای تست)")
    args = ap.parse_args(argv)
    root = Path(args.repo_dir) if args.repo_dir else repo_root()
    data = root / "data"

    for attempt in range(1, args.attempts + 1):
        # ۱. fetch + ادغام union — اول fetch را جدا چک کن: sync از
        # ۲۰۲۶-۱۱-۲۳ در صورت عدم تغییر False برمی‌گرداند (دیگر نشانه خطا
        # نیست)، پس خطای fetch جداگانه abort می‌کند تا کامیت با state
        # کهنه (مسابقه فانتوم ۱۵/۱۶) تکرار نشود.
        fetch = _git(["fetch", "origin", "main"], root)
        if fetch.returncode != 0:
            log_error("merge_state: could not fetch origin/main — aborting "
                      "(state stays local-only; next run will re-sync)")
            return 1
        changed = sync_remote_state(state_path=data / "state.json",
                                    queue_path=data / "queue.json",
                                    archive_path=data / "archive.jsonl",
                                    ref=args.ref, repo_dir=root)
        log_info(f"merge_state: sync changed={changed}")
        # ۲. راستی‌آزمایی: هیچ رکورد پست‌شده راه‌دور نباید گم شده باشد
        remote_ids = _remote_posted_ids(root, args.ref)
        if remote_ids is not None:
            local_state = json.loads(
                (data / "state.json").read_text(encoding="utf-8"))
            missing = remote_ids - set(local_state.get("posted_message_ids", []))
            if missing:
                log_error("merge_state: merged state is MISSING remote posted ids "
                          f"{sorted(missing)} — refusing to commit")
                return 1
        # بسته لاگ ۲۰۲۶-۱۱-۲۳: هیچ خط لاگ راه‌دور هم نباید گم شده باشد
        # (همان قانونی که جلوی گم‌شدن خط‌های ۲۳/۲۴/۲۵ را می‌گیرد).
        for rel in ("logs/publish-log.md", "logs/fetch-log.md"):
            remote_lines = _remote_log_lines(root, args.ref, rel)
            if remote_lines is None:
                continue
            lp = root / rel
            local_lines = {l.strip() for l in
                           (lp.read_text(encoding="utf-8").splitlines()
                            if lp.exists() else []) if l.strip()}
            missing_log = remote_lines - local_lines
            if missing_log:
                log_error(f"merge_state: merged {rel} is MISSING "
                          f"{len(missing_log)} remote line(s) — refusing to commit")
                return 1
        # ۳. stage + commit
        add = _git(["add", *[f for f in DATA_FILES if (root / f).exists()]], root)
        if add.returncode != 0:
            log_error("merge_state: git add failed: "
                      + add.stderr.decode("utf-8", "replace")[:300])
            return 1
        if _git(["diff", "--cached", "--quiet"], root).returncode == 0:
            log_info("merge_state: nothing to commit")
            return 0
        commit = _git(["commit", "-m", args.commit_message], root)
        if commit.returncode != 0:
            log_error("merge_state: git commit failed: "
                      + commit.stderr.decode("utf-8", "replace")[:300])
            return 1
        # ۳٫۵. فایل‌های غیر‌داده را از راه‌دور برگردان (حادثه ۲۰۲۶-۱۱-۲۴):
        # `merge -s ours` درخت محلی را کامل نگه می‌دارد، پس اگر کلون
        # کهنه باشد، کد/داکِ راه‌دور برمی‌گردد. ورکر فقط data/ و logs/
        # را می‌نویسد — بقیه باید دقیقاً همان origin/main باشند.
        restored = _restore_non_data_files(root, args.ref)
        if restored is None:
            log_error("merge_state: could not restore non-data files "
                      "— refusing to push a stale tree")
            return 1
        if restored:
            amend = _git(["commit", "--amend", "--no-edit"], root)
            if amend.returncode != 0:
                log_error("merge_state: git commit --amend failed: "
                          + amend.stderr.decode("utf-8", "replace")[:300])
                return 1
            log_info("merge_state: restored non-data files from "
                     + args.ref + " (amended into the state commit)")
        # ۴. ثبت remote به‌عنوان mergeشده، بدون دست‌زدن به درخت
        merge = _git(["merge", "-s", "ours", args.ref], root)
        if merge.returncode != 0:
            log_error("merge_state: git merge -s ours failed: "
                      + merge.stderr.decode("utf-8", "replace")[:300])
            return 1
        # ۵. push؛ اگر خورد، از قدم ۱ تکرار کن
        push = _git(["push", "origin", "main"], root)
        if push.returncode == 0:
            log_info(f"merge_state: pushed on attempt {attempt} ({iso_utc()})")
            return 0
        log_warn(f"merge_state: push failed on attempt {attempt} "
                 "— retrying with a fresh merge")
    log_error("merge_state: push failed after all attempts "
              "— state stays local-only; next run will re-sync")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
