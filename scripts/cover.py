#!/usr/bin/env python3
"""Automatic V3 cover builder for the «اخبار دنیای انیمه» Telegram channel.

Locked format (ARCHITECTURE.md §5, user-approved 2026-11-20): 1080x1350 JPEG,
dark background #0B0E14, champagne-gold serif English title, twin gold frame,
hollow gold diamond watermark + «انیمه‌خبر» bottom-left inside the frame,
English anime name + rating when available, Persian category/subtitle.

Two image modes — the choice is made HERE, in code, not on paper:

* ``source``  — the article's own og:image / RSS enclosure, cover-cropped and
  darkened, used ONLY when the source is explicitly allow-listed
  (``SOURCE_IMAGE_ALLOWLIST``) or the caller passes an explicit
  ``image_license`` of ``press-kit`` / ``cc-by`` / ``cc0`` / ``public-domain``.
  Attribution is NOT a licence, so the allow-list is EMPTY by default.
* ``symbolic`` — the DEFAULT. A Pillow-drawn cover: deterministic gradient,
  geometric gold motifs and typography only. No poster, key visual, episode
  still or fan-art is ever copied. This is the §7.2-compliant default.

Why Pillow and not Playwright (measured, 2026-11-21):
* Pillow 10.2 is already present; a cover renders in ~0.3 s with ~150 MB RAM,
  no browser, no download, no extra dependency. Pillow ships libraqm here
  (``features.check('raqm') == True``), so Persian RTL shaping works natively.
* Playwright is NOT installed in this environment and no Chromium binary
  exists: each Actions run would need ``pip install playwright`` +
  ``playwright install chromium`` (~150 MB download, ~60-90 s) plus a browser
  launch (~1-2 s, ~300 MB RAM) per cover, for output that is pixel-identical
  in purpose to the Pillow render. The v2 estimate in ARCHITECTURE.md §7.1
  already prices a Playwright publisher run at ~3 min vs seconds for Pillow.
* Playwright stays only as a documented fallback (option 2) for the day a
  cover needs real HTML/CSS layout that Pillow cannot express; there is no
  such need today.

No AI, no API, no token at runtime. Only dependency: Pillow (+ requests,
only to fetch a source image when explicitly allowed).

Public interface:
    build_cover(item: dict, out_path: str) -> str
        item keys: title_en (str, required), category (str, required),
        persian_subtitle (str, required), rating (str|float|None, optional),
        image_url (str|None, optional), source (str|None, optional),
        image_license (str|None, optional).
        Returns the JPEG path (1080x1350). Never raises for a bad image:
        any source-image failure falls back to symbolic mode.
        The mode actually used is recorded on ``build_cover.last_build``
        (dict with keys: mode, reason, image_url, source).
"""
from __future__ import annotations

import hashlib
import io
import math
import os
import random
import textwrap

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, features

W, H = 1080, 1350
DARK = (11, 14, 20)            # #0B0E14 — locked V3 background
DARK2 = (18, 23, 34)           # gradient end
GOLD = (201, 168, 106)         # #C9A86A channel gold
GOLD_BRIGHT = (216, 190, 138)  # champagne for text
GOLD_DIM = (150, 124, 78)

# Category accent colours (ARCHITECTURE.md §3 palette, muted to fit Midnight Gold)
CATEGORY_COLORS = {
    "فصل جدید": (96, 165, 250),
    "فیلم": (248, 113, 113),
    "تریلر": (74, 222, 128),
    "استودیو": (192, 132, 252),
    "مانگا و اقتباس": (251, 146, 60),
    "رویداد": (244, 114, 182),
    "خبر روز": (250, 204, 21),
}
DEFAULT_ACCENT = (201, 168, 106)

# ---------------------------------------------------------------------------
# Image-use policy (§7.2). EMPTY by default on purpose: a source image is
# used only if the source is on this list (press-kit / CC licence confirmed
# in writing) or the caller passes image_license in the allowed set.
# Live check 2026-11-21: NONE of the 8 v2 sources qualifies — every og:image
# sampled was an official key visual, episode still or manga-cover art
# (MAL: official key visual with © line; ANN: manga-cover crop;
# AnimeCorner: episode still; AnimeTV/FandomPost/Honey's: official art).
# Add a source here ONLY with a written permission / press-kit note + date.
# ---------------------------------------------------------------------------
SOURCE_IMAGE_ALLOWLIST = frozenset()  # type: ignore[var-annotated]
ALLOWED_IMAGE_LICENSES = frozenset({"press-kit", "cc-by", "cc0", "public-domain"})

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "assets", "fonts")
_VAZIR = os.path.join(_FONT_DIR, "Vazirmatn-Variable.ttf")
_PLAYFAIR = os.path.join(_FONT_DIR, "PlayfairDisplay-Variable.ttf")

_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "Chrome/120 Safari/537.36"}


def _font(path: str, weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a variable font at a named weight; fall back to default weight."""
    fnt = ImageFont.truetype(path, size)
    try:
        fnt.set_variation_by_name(weight)
    except Exception:
        pass
    return fnt


def _wrap(draw: ImageDraw.ImageDraw, text: str, fnt, max_w: int,
          direction: str | None = None) -> list[str]:
    """Greedy word wrap by rendered width (RTL-aware when direction='rtl')."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip() if cur else w
        kw = {"font": fnt}
        if direction:
            kw.update({"direction": direction, "language": "fa"})
        if draw.textlength(trial, **kw) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def decide_image_mode(item: dict) -> tuple[str, str]:
    """Return ('source'|'symbolic', reason). The policy decision, in code."""
    url = (item.get("image_url") or "").strip()
    if not url:
        return "symbolic", "no image_url supplied"
    source = (item.get("source") or "").strip()
    lic = (item.get("image_license") or "").strip().lower()
    if source in SOURCE_IMAGE_ALLOWLIST:
        return "source", f"source {source!r} is allow-listed (press-kit/CC on file)"
    if lic in ALLOWED_IMAGE_LICENSES:
        return "source", f"explicit image_license={lic!r}"
    if lic:
        return "symbolic", (f"image_license={lic!r} is not an allowed licence; "
                            "attribution is not a licence (§7.2)")
    return "symbolic", (f"source {source or 'unknown'!r} is not allow-listed; "
                        "og:image is normally an official key visual / still (§7.2)")


def _fetch_source_image(url: str) -> Image.Image | None:
    """Download + validate a source image. None on ANY failure (never raises)."""
    try:
        r = requests.get(url, headers=_UA, timeout=15, stream=True)
        if r.status_code != 200:
            return None
        ctype = (r.headers.get("content-type") or "").lower()
        if not any(t in ctype for t in ("image/jpeg", "image/png", "image/webp")):
            return None
        data = r.content
        if len(data) > 8 * 1024 * 1024:
            return None
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.size[0] < 400 or im.size[1] < 300:
            return None
        return im.convert("RGB")
    except Exception:
        return None


def _cover_crop(im: Image.Image, w: int, h: int) -> Image.Image:
    """Centre-crop to the target aspect ratio, then resize (Lanczos)."""
    tw, th = w, h
    sw, sh = im.size
    scale = max(tw / sw, th / sh)
    im = im.resize((round(sw * scale), round(sh * scale)), Image.LANCZOS)
    x = (im.size[0] - tw) // 2
    y = (im.size[1] - th) // 2
    return im.crop((x, y, x + tw, y + th))


def _darken(im: Image.Image) -> Image.Image:
    """Darken a source photo so gold V3 type reads on it (V3 is dark-first)."""
    im = ImageEnhance.Brightness(im).enhance(0.55)
    im = ImageEnhance.Color(im).enhance(0.75)
    ov = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(ov)
    # top gradient (title zone) + bottom gradient (subtitle/watermark zone)
    for y in range(0, 420):
        d.line([(0, y), (W, y)], fill=int(150 * (1 - y / 420)))
    for y in range(H - 420, H):
        d.line([(0, y), (W, y)], fill=int(170 * ((y - (H - 420)) / 420)))
    black = Image.new("RGB", im.size, (0, 0, 0))
    return Image.composite(black, im, ov)


def _symbolic_background(seed_text: str, accent) -> Image.Image:
    """Deterministic Pillow-only backdrop: gradient + gold geometry + grain.

    Seeded from the title hash, so the same news item always renders the
    same cover (ARCHITECTURE.md principle 3: deterministic, no bare random).
    """
    seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:8], 16)
    rnd = random.Random(seed)

    base = Image.new("RGB", (W, H), DARK)
    # vertical gradient DARK -> DARK2 -> DARK
    grad = Image.new("RGB", (1, H))
    px = grad.load()
    for y in range(H):
        t = y / H
        f = math.sin(t * math.pi)  # 0 at edges, 1 mid-frame
        px[0, y] = tuple(int(DARK[i] + (DARK2[i] - DARK[i]) * f) for i in range(3))
    base = grad.resize((W, H))

    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    cx, cy = W // 2, 700  # motif centre: middle band, clear of title/subtitle

    # radial glow around the motif centre (accent, very soft)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for r in range(420, 0, -6):
        a = int(14 * (1 - r / 420))
        gd.ellipse([cx - r, cy - r, cx + r, cy + r],
                   fill=accent + (a,))
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    ov = Image.alpha_composite(ov, glow)
    d = ImageDraw.Draw(ov)

    # concentric thin gold rings
    for r, a in ((300, 60), (240, 90), (180, 120)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GOLD + (a,), width=2)
    # large hollow diamond (echoes the channel mark, scaled up)
    R = 150
    d.polygon([(cx, cy - R), (cx + R, cy), (cx, cy + R), (cx - R, cy)],
              outline=GOLD + (150,), width=3)
    d.polygon([(cx, cy - R + 26), (cx + R - 26, cy), (cx, cy + R - 26),
               (cx - R + 26, cy)], outline=GOLD + (70,), width=2)
    # small diamond at the centre
    r = 14
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
              outline=GOLD_BRIGHT + (220,), width=2)
    d.ellipse([cx - 3, cy - 3, cx + 3, cy + 3], fill=GOLD_BRIGHT + (220,))
    # orbit ticks
    for k in range(12):
        ang = 2 * math.pi * k / 12 + 0.35
        x1 = cx + int(268 * math.cos(ang)); y1 = cy + int(268 * math.sin(ang))
        x2 = cx + int(284 * math.cos(ang)); y2 = cy + int(284 * math.sin(ang))
        d.line([(x1, y1), (x2, y2)], fill=GOLD + (110,), width=3)
    # deterministic gold dust (seeded — same item, same dust)
    for _ in range(90):
        x = rnd.randint(60, W - 60)
        y = rnd.randint(380, 1180)
        s = rnd.choice((1, 1, 2, 2, 3))
        a = rnd.randint(40, 150)
        d.ellipse([x, y, x + s, y + s], fill=GOLD_BRIGHT + (a,))
    # faint diagonal hairlines, top-left / bottom-right
    for i in range(5):
        off = 120 + i * 46
        d.line([(off, 380), (off + 260, 640)], fill=GOLD + (18,), width=1)

    return Image.alpha_composite(base.convert("RGBA"), ov).convert("RGB")


def _twin_frame(im: Image.Image) -> Image.Image:
    """Locked V3 twin gold frame + corner flourishes (matches cover-v3-*.png)."""
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    d.rectangle([28, 28, W - 29, H - 29], outline=GOLD + (255,), width=2)
    d.rectangle([40, 40, W - 41, H - 41], outline=GOLD + (200,), width=1)
    # corner flourishes: small L-brackets on the outer frame
    for (x0, y0, sx, sy) in ((28, 28, 1, 1), (W - 29, 28, -1, 1),
                             (28, H - 29, 1, -1), (W - 29, H - 29, -1, -1)):
        d.line([(x0, y0 + 26 * sy), (x0, y0), (x0 + 26 * sx, y0)],
               fill=GOLD_BRIGHT + (255,), width=3)
    return Image.alpha_composite(im.convert("RGBA"), ov)


def _watermark(im: Image.Image) -> Image.Image:
    """Channel watermark, byte-identical in position to build-v3.py.

    Hollow gold diamond centred on the inner-frame bottom-left corner +
    «انیمه‌خبر», so cropping it off cuts the frame corner itself.
    """
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    cx, cy = 62, 1288
    r = 15
    d.rounded_rectangle([34, 1252, 262, 1322], radius=12, fill=(5, 7, 10, 95))
    d.line([(40, cy), (cx - r - 2, cy)], fill=GOLD + (255,), width=2)
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
              outline=GOLD + (255,), width=3)
    d.polygon([(cx, cy - r + 6), (cx + r - 6, cy), (cx, cy + r - 6),
               (cx - r + 6, cy)], fill=DARK + (255,))
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=GOLD + (255,))
    f_wm = _font(_VAZIR, "ExtraBold", 42)
    x, y = 88, 1300  # anchor "ls": y is the baseline
    d.text((x + 2, y + 2), "انیمه‌خبر", font=f_wm, fill=(0, 0, 0, 140),
           anchor="ls", direction="rtl", language="fa")
    d.text((x, y), "انیمه‌خبر", font=f_wm, fill=GOLD_BRIGHT + (255,),
           anchor="ls", direction="rtl", language="fa")
    return Image.alpha_composite(im.convert("RGBA"), ov)


def _draw_text(im: Image.Image, item: dict, accent) -> Image.Image:
    """Title (EN serif) + rating + category + Persian subtitle, V3 layout."""
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    title = (item.get("title_en") or "").strip()
    category = (item.get("category") or "").strip()
    subtitle = (item.get("persian_subtitle") or "").strip()
    rating = item.get("rating")

    def shadow_text(xy, text, fnt, fill, anchor="ma", direction=None):
        kw = {"font": fnt, "anchor": anchor}
        if direction:
            kw.update({"direction": direction, "language": "fa"})
        d.text((xy[0] + 2, xy[1] + 2), text, fill=(0, 0, 0, 160), **kw)
        d.text(xy, text, fill=fill + (255,), **kw)

    # — category: small gold line, top centre, inside the frame —
    if category:
        f_cat = _font(_VAZIR, "Bold", 30)
        shadow_text((W // 2, 78), category, f_cat, GOLD, direction="rtl")

    # — English title: Playfair Display Bold, auto-fit, max 2 lines —
    size = 118
    lines = [title]
    while size > 44:
        f_title = _font(_PLAYFAIR, "Bold", size)
        lines = _wrap(d, title, f_title, 920)
        if len(lines) <= 2 and all(
                d.textlength(ln, font=f_title) <= 920 for ln in lines):
            break
        size -= 6
    f_title = _font(_PLAYFAIR, "Bold", size)
    y = 150
    for ln in lines[:2]:
        shadow_text((W // 2, y), ln, f_title, GOLD_BRIGHT)
        y += int(size * 1.08)
    # thin gold rule under the title
    rule_y = y + 18
    d.line([(W // 2 - 130, rule_y), (W // 2 + 130, rule_y)],
           fill=GOLD + (220,), width=2)
    d.polygon([(W // 2, rule_y - 5), (W // 2 + 5, rule_y),
               (W // 2, rule_y + 5), (W // 2 - 5, rule_y)],
              fill=GOLD_BRIGHT + (255,))

    # — rating (locked rule: only a citable rating, beside the English name) —
    if rating is not None and str(rating).strip() != "":
        f_rate = _font(_PLAYFAIR, "Bold", 44)
        shadow_text((W // 2, rule_y + 26), f"★ {rating}", f_rate, GOLD_BRIGHT)
        sub_y = rule_y + 26 + 62
    else:
        sub_y = rule_y + 26

    # — Persian subtitle: Vazirmatn Medium, centred, max 2 lines, above watermark —
    if subtitle:
        f_sub = _font(_VAZIR, "Medium", 36)
        sub_lines = _wrap(d, subtitle, f_sub, 920, direction="rtl")
        # shrink if it would collide with the watermark zone (y > 1230)
        while len(sub_lines) > 2 and f_sub.size > 26:
            f_sub = _font(_VAZIR, "Medium", f_sub.size - 2)
            sub_lines = _wrap(d, subtitle, f_sub, 920, direction="rtl")
        total_h = len(sub_lines[:2]) * int(f_sub.size * 1.25)
        y = 1235 - total_h
        for ln in sub_lines[:2]:
            shadow_text((W // 2, y), ln, f_sub, GOLD_BRIGHT, direction="rtl")
            y += int(f_sub.size * 1.25)

    return Image.alpha_composite(im.convert("RGBA"), ov)


def build_cover(item: dict, out_path: str) -> str:
    """Build one V3 cover (1080x1350 JPEG) from a news item dict.

    See module docstring for the item schema and the image-use policy.
    Returns ``out_path``. Records the decision in ``build_cover.last_build``.
    """
    if not (item.get("title_en") or "").strip():
        raise ValueError("item['title_en'] is required")
    if not (item.get("persian_subtitle") or "").strip():
        raise ValueError("item['persian_subtitle'] is required")

    mode, reason = decide_image_mode(item)
    accent = CATEGORY_COLORS.get((item.get("category") or "").strip(),
                                 DEFAULT_ACCENT)

    src_im = None
    if mode == "source":
        src_im = _fetch_source_image(item["image_url"])
        if src_im is None:
            mode, reason = "symbolic", "source image fetch/validation failed"

    if src_im is not None:
        base = _darken(_cover_crop(src_im, W, H))
    else:
        base = _symbolic_background(item["title_en"], accent)

    out = _twin_frame(base)
    out = _draw_text(out, item, accent)
    out = _watermark(out)

    out_dir = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(out_dir, exist_ok=True)
    out.convert("RGB").save(out_path, "JPEG", quality=90)
    build_cover.last_build = {
        "mode": mode,
        "reason": reason,
        "image_url": item.get("image_url"),
        "source": item.get("source"),
        "out_path": out_path,
        "size": (W, H),
    }
    return out_path


build_cover.last_build = {}


if __name__ == "__main__":
    import json
    import sys
    item = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "title_en": "BanG Dream! Yume∞Mita",
        "category": "فصل جدید",
        "persian_subtitle": "سری تازه انیمه تأیید شد",
        "source": "AnimeCorner",
    }
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/cover-test.jpg"
    print(build_cover(item, out))
    print(build_cover.last_build)
