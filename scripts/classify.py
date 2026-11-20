"""موتور دسته‌بندی قانون‌محور (ARCHITECTURE.md §۳، filter-v2 §۳).

۶ دسته + «خبر روز» (خبر روز را publisher به مهم‌ترین آیتم صف می‌دهد، نه این موتور).
قانون‌محور با کلیدواژه + قوانین تقدم + اصلاح‌های انسانی (category-corrections.json).
آستانه اطمینان ۳ امتیاز: کمتر از آن → HOLD انسانی.

امضاها:
    classify(title, summary) -> (category, score, is_confident)
    detect_event(title, summary) -> event_type
    classify_with_corrections(guid_or_link, title, summary) -> dict
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from common import data_dir, load_json

CONFIDENCE_THRESHOLD = 3

# نوع رویداد دقیق‌تر (filter-v2 §۳.۲) — برای story_key و امتیاز اولویت
_EVENT_PATTERNS: list[tuple[str, list[str]]] = [
    ("trailer", [r"\btrailer\b", r"\bteaser\b", r"\bpv\b", r"key visual",
                 r"trailer 2", "pv 2", "character pv"]),
    ("date", [r"premiere date", r"release date", r"air date", r"broadcast",
              r"debuts on", r"premieres on", r"to air on", r"delayed to",
              r"postponed to", r"rescheduled"]),
    ("casting", [r"\bcast\b", r"voice cast", r"casts ", r"joins the cast",
                 r"additional cast", r"voice actor"]),
    ("box_office", [r"box office", r"earns ", r"grosses", r"tickets sold",
                    r"highest-grossing", r"surpasses .* at the box office"]),
    ("adaptation", [r"manga gets anime", r"light novel.*anime adaptation",
                    r"novel gets anime", r"game gets anime", r"anime adaptation of",
                    r"live-action"]),
    ("award", [r"\baward", r"wins .* award", r"nominated for"]),
    ("event", [r"jump festa", r"anime expo", r"animejapan", r"comiket",
               r"event", r"exhibition", r"stage play", r"concert"]),
    ("announcement", [r"announces", r"announced", r"reveals", r"confirmed",
                      r"green-lit", r"greenlit", r"new season", r"season 2",
                      r"second season", r"sequel", r"new anime", r"film announced",
                      r"\blicenses?\b", r"\blicensed\b",
                      r"gets (a |an )?(tv )?anime", r"gets anime adaptation",
                      r"\bgets\b.*\bpart\b", r"\blaunches\b",
                      r"\bfinal chapter\b"]),
]


def detect_event(title: str, summary: str) -> str:
    text = f"{title or ''} {summary or ''}".lower()
    for event, patterns in _EVENT_PATTERNS:
        for pat in patterns:
            if re.search(pat, text):
                return event
    return "other"


def _load_categories() -> dict:
    return load_json(data_dir() / "categories.json", {"categories": {}, "precedence": []})


def _load_corrections() -> dict:
    return load_json(data_dir() / "category-corrections.json", {"corrections": {}})


def _score_text(text: str, keywords: list[str]) -> int:
    """هر کلیدواژه در تیتر ۲ امتیاز، در خلاصه ۱ امتیاز."""
    title, summary = text
    score = 0
    t = title.lower()
    s = summary.lower()
    for kw in keywords:
        kw = kw.lower()
        if kw in t:
            score += 2
        elif kw in s:
            score += 1
    return score


def classify(title: str, summary: str) -> tuple[str, int, bool]:
    """برمی‌گرداند (دسته، امتیاز اطمینان، آیا اطمینان ≥ ۳)."""
    bank = _load_categories()
    categories = bank.get("categories", {})
    precedence = bank.get("precedence", list(categories.keys()))
    scores = {
        name: _score_text((title or "", summary or ""), spec.get("keywords", []))
        for name, spec in categories.items()
    }
    if not scores or max(scores.values()) == 0:
        # حتی بدون هیچ کلیدواژه، یک رویداد مشخص نشانه خبر واقعی است (امتیاز ۱؛
        # همچنان زیر آستانه ۳ → HOLD، ولی امتیاز صفرِ گمراه‌کننده نیست).
        ev = detect_event(title, summary)
        return "رویداد", (1 if ev != "other" else 0), False
    best_score = max(scores.values())
    tied = [name for name, sc in scores.items() if sc == best_score]
    if len(tied) == 1:
        best = tied[0]
    else:
        best = next((name for name in precedence if name in tied), tied[0])
    # جایزه رویداد مشخص (+۱): خبر واقعی معمولاً یک رویداد قابل تشخیص دارد
    # (اعلام/تریلر/تاریخ/کست/…). بدون آن، تیترهای تک‌کلیدواژه‌ای با امتیاز ۲
    # به‌اشتباه به HOLD می‌رفتند (dry-run ۲۱ نوامبر: ۶۹ HOLD با امتیاز ۰–۲).
    # آستانه اطمینان ۳ سر جایش می‌ماند.
    if detect_event(title, summary) != "other":
        best_score += 1
    return best, best_score, best_score >= CONFIDENCE_THRESHOLD


def classify_with_corrections(key: str, title: str, summary: str) -> dict:
    """دسته‌بندی با override انسانی (category-corrections.json بر همه چیز مقدم است)."""
    corrections = _load_corrections().get("corrections", {})
    if key in corrections:
        entry = corrections[key]
        return {
            "category": entry.get("category", "رویداد"),
            "score": 99,
            "confident": True,
            "source": "human-correction",
            "note": entry.get("note", ""),
        }
    category, score, confident = classify(title, summary)
    return {
        "category": category,
        "score": score,
        "confident": confident,
        "source": "keyword",
        "note": "" if confident else "low-confidence",
    }


if __name__ == "__main__":
    import sys

    title = sys.argv[1] if len(sys.argv) > 1 else ""
    summary = sys.argv[2] if len(sys.argv) > 2 else ""
    print(classify_with_corrections("cli", title, summary))
    print("event:", detect_event(title, summary))
