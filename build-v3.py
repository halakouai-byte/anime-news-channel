#!/usr/bin/env python3
"""Build v3 covers: overlay channel watermark + Persian line on v2 covers.

- Watermark (IDENTICAL position on all three): gold diamond mark centred on the
  inner-frame bottom-left corner + «انیمه‌خبر» (Vazirmatn ExtraBold) + hairline
  tying the mark to the frame. Cropping it off cuts the frame corner itself.
- Persian line per cover (scene-adapted position, copywriter-approved):
  - Chainsaw: under the title (clear dark zone), baseline y=325
  - Re:Zero: bottom-centre (no room under title: hourglass ring), baseline y=1290
  - MAPPA: under the subtitle (clear gap 245-270), baseline y=272
- Anime/studio names stay English (untouched v2 text). Output 1080x1350 PNG.
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import os

BASE = os.path.expanduser("~/workspace/anime-news-channel/covers")
FONT_DIR = "/tmp/vazir/extracted/fonts/ttf"
GOLD = (201, 168, 106)        # #C9A86A channel gold
GOLD_BRIGHT = (216, 190, 138) # champagne for text
DARK = (11, 14, 20)           # #0B0E14

def font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)

F_WM = font("Vazirmatn-ExtraBold.ttf", 42)

def draw_rtl(draw, xy, text, fnt, fill, anchor="ma"):
    """Draw Persian text with a soft dark shadow for readability."""
    x, y = xy
    draw.text((x + 2, y + 2), text, font=fnt, fill=(0, 0, 0, 140),
              anchor=anchor, direction="rtl", language="fa")
    draw.text((x, y), text, font=fnt, fill=fill + (255,),
              anchor=anchor, direction="rtl", language="fa")

def watermark(im):
    """Fixed-position watermark, identical on every cover."""
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    cx, cy = 62, 1288  # diamond centre: on the inner-frame bottom-left corner
    r = 15
    # soft dark scrim behind the mark+text so gold reads on any background
    d.rounded_rectangle([34, 1252, 262, 1322], radius=12, fill=(5, 7, 10, 95))
    # hairline tying the diamond to the left frame edge
    d.line([(40, cy), (cx - r - 2, cy)], fill=GOLD + (255,), width=2)
    # diamond mark (outline + dark centre + tiny gold dot)
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)],
              outline=GOLD + (255,), width=3)
    d.polygon([(cx, cy - r + 6), (cx + r - 6, cy), (cx, cy + r - 6), (cx - r + 6, cy)],
              fill=DARK + (255,))
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=GOLD + (255,))
    # channel name: anchor "ls" = left + BASELINE, so y is the baseline
    draw_rtl(d, (88, 1300), "انیمه‌خبر", F_WM, GOLD_BRIGHT, anchor="ls")
    return Image.alpha_composite(im.convert("RGBA"), ov)

def persian_line(im, text, size, baseline_y):
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    fnt = font("Vazirmatn-Medium.ttf", size)
    draw_rtl(d, (540, baseline_y), text, fnt, GOLD_BRIGHT, anchor="ma")
    return Image.alpha_composite(im.convert("RGBA"), ov)

JOBS = [
    ("cover-v2-chainsaw-man-reze.png", "cover-v3-chainsaw-man-reze.png",
     "فیلم و سینما • ۱۵۸ میلیون دلار در گیشهٔ جهانی", 34, 325),
    ("cover-v2-rezero-season5.png", "cover-v3-rezero-season5.png",
     "فصل جدید • فصل پنجم تأیید شد", 32, 1235),
    ("cover-v2-cyberagent-mappa.png", "cover-v3-cyberagent-mappa.png",
     "صنعت انیمه • اتحاد دو غول انیمه", 30, 272),
]

for src, dst, text, size, y in JOBS:
    im = Image.open(os.path.join(BASE, src)).convert("RGB")
    assert im.size == (1080, 1350), (src, im.size)
    out = watermark(im)
    out = persian_line(out, text, size, y)
    out.convert("RGB").save(os.path.join(BASE, dst))
    print("wrote", dst, out.size)
print("done")
