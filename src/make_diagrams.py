"""
Generate diagram assets — transparent PNG, 2× supersample.
  assets/pipeline_diagram.png
  assets/dir_structure.png

python3 src/make_diagrams.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ASSETS = Path("assets")
ASSETS.mkdir(exist_ok=True)

S = 2

BOLD = "/usr/share/fonts/noto/NotoSans-Bold.ttf"
REG  = "/usr/share/fonts/noto/NotoSans-Regular.ttf"

def F(size, bold=False):
    try:
        return ImageFont.truetype(BOLD if bold else REG, size * S)
    except:
        return ImageFont.load_default()

def canvas(w, h):
    return Image.new("RGBA", (w * S, h * S), (0, 0, 0, 0))

def save(img, path):
    w, h = img.width // S, img.height // S
    img.resize((w, h), Image.LANCZOS).save(path)
    print(f"  {path.name}  {w}×{h}")


class D:
    def __init__(self, img):
        self._d = ImageDraw.Draw(img)

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, width=1, r=0):
        xy = [v * S for v in (x0, y0, x1, y1)]
        kw = {}
        if fill:    kw["fill"]    = fill
        if outline: kw["outline"] = outline; kw["width"] = max(1, width * S)
        try:    self._d.rounded_rectangle(xy, radius=r * S, **kw)
        except: self._d.rectangle(xy, **kw)

    def line(self, pts, fill, w=2):
        self._d.line([(x * S, y * S) for x, y in pts], fill=fill, width=w * S)

    def poly(self, pts, fill):
        self._d.polygon([(x * S, y * S) for x, y in pts], fill=fill)

    def circle(self, cx, cy, r, fill=None, outline=None, width=1):
        kw = {}
        if fill:    kw["fill"]    = fill
        if outline: kw["outline"] = outline; kw["width"] = width * S
        self._d.ellipse([(cx-r)*S, (cy-r)*S, (cx+r)*S, (cy+r)*S], **kw)

    def text(self, x, y, msg, f, fill, anchor=None):
        kw = {"anchor": anchor} if anchor else {}
        self._d.text((x * S, y * S), msg, font=f, fill=fill, **kw)

    def textw(self, msg, f):
        return int(self._d.textlength(msg, font=f)) // S


# ── Palette ───────────────────────────────────────────────────────────────────
CARD   = (18, 21, 36, 255)
WHITE  = (235, 238, 252, 255)
MUTED  = (145, 150, 178, 255)
DIM    = (68,  72,  98, 255)
SHADOW = (0, 0, 0, 60)

ACCENT = [
    (80,  145, 255),   # blue
    (130,  90, 255),   # violet
    (225,  70, 145),   # rose
    (38,  195, 130),   # emerald
    (245, 158,  40),   # amber
]

def ac(col, a):  return col + (a,)


# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

F_NUM  = F(42, bold=True)
F_NAME = F(30, bold=True)
F_BUL  = F(25)

STEPS = [
    (ACCENT[0], "download_\nchapters.py", [
        "38 art-pack ZIPs · ~17 GB",
        "from peppercarrot.com",
        "Resumes if interrupted",
    ]),
    (ACCENT[1], "extract_\nkra.py", [
        "Unzips archives → kra/",
        "~350 Krita source files",
        "Delete zips/ after",
    ]),
    (ACCENT[2], "process_\nkra.py", [
        "Detects & removes border",
        "Saves initial/ + cleaned/",
        "Delete kra/ after",
    ]),
    (ACCENT[3], "synthesize_\ndataset.py", [
        "9 training variants/page",
        "281 pages · ~80 min",
        "Output → dataset/",
    ]),
    (ACCENT[4], "synthesize_\noverlays.py", [
        "SFX + bubble overlays",
        "4 variants, pixel-aligned",
        "Deterministic placement",
    ]),
]

CW, CH  = 360, 268
GAP     = 44
PAD_X   = (1380 - 3 * CW - 2 * GAP) // 2
PAD_Y   = 44
CONN_H  = 76

W_P = 1380
H_P = PAD_Y + CH + CONN_H + CH + PAD_Y

img = canvas(W_P, H_P)
dp  = D(img)

row1 = [(PAD_X + i * (CW + GAP), PAD_Y) for i in range(3)]
row2_x0 = (W_P - (2 * CW + GAP)) // 2
row2 = [(row2_x0 + i * (CW + GAP), PAD_Y + CH + CONN_H) for i in range(2)]
all_cards = row1 + row2


def draw_card(dp, x0, y0, col, name_lines, bullets, num):
    x1, y1 = x0 + CW, y0 + CH

    # shadow
    dp.rect(x0 + 7, y0 + 7, x1 + 7, y1 + 7, fill=SHADOW, r=18)
    # card body
    dp.rect(x0, y0, x1, y1, fill=CARD, r=18)
    # coloured top stripe — rounded rect then flat fill to square off bottom
    dp.rect(x0, y0, x1, y0 + 12, fill=ac(col, 255), r=18)
    dp.rect(x0, y0 + 10, x1, y0 + 16, fill=ac(col, 255))

    # step number circle badge — solid fill, no outer rings (avoids corner bleed)
    NR = 24
    bx = x0 + 20 + NR
    by = y0 + 22 + NR
    dp.circle(bx, by, NR, fill=ac(col, 190))
    # anchor="mm" centres the glyph exactly at (bx, by)
    dp.text(bx, by, num, F_NUM, fill=(255, 255, 255, 255), anchor="mm")

    # script name — two short lines, right-aligned
    ny = y0 + 18
    for ln in name_lines:
        lw = dp.textw(ln, F_NAME)
        dp.text(x1 - lw - 16, ny, ln, F_NAME, fill=WHITE)
        ny += 36

    # divider
    div_y = y0 + 20 + len(name_lines) * 36
    dp.line([(x0 + 16, div_y), (x1 - 16, div_y)], fill=ac(col, 55), w=1)
    dy = div_y + 14

    # bullets with a small glow dot
    for bul in bullets:
        dp.circle(x0 + 26, dy + 13, 7, fill=ac(col, 35))
        dp.circle(x0 + 26, dy + 13, 5, fill=ac(col, 215))
        dp.text(x0 + 38, dy, bul, F_BUL, fill=MUTED)
        dy += 32


for i, (x0, y0) in enumerate(all_cards):
    col, name, buls = STEPS[i]
    draw_card(dp, x0, y0, col, name.split("\n"), buls, str(i + 1))


def harrow(dp, x0, y, x1, col):
    dp.line([(x0, y), (x1 - 14, y)], fill=ac(col, 195), w=3)
    dp.poly([(x1 - 14, y - 9), (x1, y), (x1 - 14, y + 9)], fill=ac(col, 240))


for i in range(2):
    harrow(dp, row1[i][0] + CW + 5, PAD_Y + CH // 2,
               row1[i + 1][0] - 5, ACCENT[i + 1])

harrow(dp, row2[0][0] + CW + 5, PAD_Y + CH + CONN_H + CH // 2,
           row2[1][0] - 5, ACCENT[4])

# bent connector: bottom of card[2] → top of card[3]
c2cx = row1[2][0] + CW // 2
c2by = PAD_Y + CH
c3cx = row2[0][0] + CW // 2
c3ty = PAD_Y + CH + CONN_H
midy = (c2by + c3ty) // 2
ec   = ac(ACCENT[3], 175)

dp.line([(c2cx, c2by + 4), (c2cx, midy)],      fill=ec, w=3)
dp.line([(c2cx, midy),     (c3cx, midy)],       fill=ec, w=3)
dp.line([(c3cx, midy),     (c3cx, c3ty - 14)],  fill=ec, w=3)
dp.poly([(c3cx - 9, c3ty - 14), (c3cx + 9, c3ty - 14), (c3cx, c3ty)],
        fill=ac(ACCENT[3], 230))

save(img, ASSETS / "pipeline_diagram.png")


# ══════════════════════════════════════════════════════════════════════════════
#  DIRECTORY — 3 panels  (fonts/ grouped inside overlays/ by convention)
# ══════════════════════════════════════════════════════════════════════════════

F_TITLE = F(34, bold=True)
F_HDR   = F(26, bold=True)
F_DIR   = F(23, bold=True)
F_PLAIN = F(21)
F_ANN   = F(17)
F_SUBT  = F(17)

PCOL_W   = 400
PCOL_GAP = 28
P_PAD_X  = (1380 - 3 * PCOL_W - 2 * PCOL_GAP) // 2
HDR_H    = 66
ITEM_H   = 29
CPADS    = 14
CTOP     = 12
INDENT   = 18
TITLE_H  = 58

SECTIONS = [
    {
        "name": "preprocessing/",
        "sub":  "intermediates — delete after step 3",
        "col":  ACCENT[0],                               # blue
        "items": [
            (0, "renders/",       True,  "sole source for dataset"),
            (1, "ep01/ … ep39/",  False, ""),
            (2, "initial/",       True,  "raw KRA export, borders intact"),
            (2, "cleaned/",       True,  "transparent RGBA  ←  TARGET"),
            (0, "kra/",           False, "~20 GB — delete after step 3"),
            (0, "zips/",          False, "~17 GB — delete after step 2"),
        ],
    },
    {
        "name": "dataset/",
        "sub":  "281 pages × 13 training variants",
        "col":  ACCENT[3],                               # emerald
        "items": [
            (0, "ep01/ … ep39/",           True,  ""),
            (1, "black/",                  False, "solid black background"),
            (1, "framed/",                 False, "white bg + 1px frame"),
            (1, "framed_cleaned/",         False, "transparent + 1px frame"),
            (1, "framed_jpeg/",            False, "frame + JPEG q15"),
            (1, "framed_jpeg_cleaned/",    False, "transparent + frame + JPEG"),
            (1, "gradient_border/",        False, "black→white gradient"),
            (1, "gradient_border_inv/",    False, "white→black gradient"),
            (1, "jpeg/",                   False, "initial + JPEG compression"),
            (1, "jpeg_cleaned/",           False, "cleaned + JPEG artifacts"),
            (1, "sfx_overlay/",            False, "Korean SFX on initial"),
            (1, "sfx_overlay_cleaned/",    False, "SFX on cleaned RGBA"),
            (1, "bubble_overlay/",         False, "bubbles on initial"),
            (1, "bubble_overlay_cleaned/", False, "bubbles on cleaned RGBA"),
        ],
    },
    {
        "name": "overlays/",
        "sub":  "generated once, reused every run",
        "col":  ACCENT[4],                               # amber
        "items": [
            (0, "sfx/",                    True,  "Korean sound-effect overlays"),
            (1, "266 PNGs",                False, "7 style variants each"),
            (0, "bubbles/",                True,  "speech bubble shapes"),
            (1, "11 PNGs",                 False, "box and balloon styles"),
            (0, "fonts/",                  True,  "font files for SFX rendering"),
            (1, "NotoSansKR-Bold.ttf",     False, "Korean typeface"),
        ],
    },
]

max_items = max(len(s["items"]) for s in SECTIONS)
CARD_H   = HDR_H + CTOP + max_items * ITEM_H + CPADS

W2 = 1380
H2 = TITLE_H + CARD_H + 36

img2 = canvas(W2, H2)
d2   = D(img2)

tw2 = d2.textw("data/  directory structure", F_TITLE)
d2.text((W2 - tw2) // 2, 14, "data/  directory structure", F_TITLE, fill=WHITE)

for pi, sec in enumerate(SECTIONS):
    col = sec["col"]
    ca  = ac(col, 255)
    cm  = ac(col, 155)

    px0 = P_PAD_X + pi * (PCOL_W + PCOL_GAP)
    px1 = px0 + PCOL_W
    py0 = TITLE_H
    py1 = py0 + CARD_H
    pcx = (px0 + px1) // 2

    # shadow
    d2.rect(px0 + 6, py0 + 6, px1 + 6, py1 + 6, fill=SHADOW, r=16)
    # card body
    d2.rect(px0, py0, px1, py1, fill=CARD, r=16)

    # header band — rounded rect for top, then flat fill to square off bottom
    # Drawing only within the card (no extra pixels in transparent corner area)
    d2.rect(px0, py0,      px1, py0 + HDR_H, fill=ca, r=16)
    d2.rect(px0, py0 + 16, px1, py0 + HDR_H, fill=ca)

    # header text
    hw = d2.textw(sec["name"], F_HDR)
    d2.text(pcx - hw // 2, py0 + 8, sec["name"], F_HDR, fill=(255, 255, 255, 255))
    sw = d2.textw(sec["sub"], F_SUBT)
    d2.text(pcx - sw // 2, py0 + 42, sec["sub"], F_SUBT, fill=(255, 255, 255, 170))

    iy = py0 + HDR_H + CTOP

    for (indent, name, hi, ann) in sec["items"]:
        f_name = F_DIR if hi else F_PLAIN
        fc     = WHITE if hi else MUTED
        tx     = px0 + CPADS + indent * INDENT

        if hi:
            d2.rect(tx - 4, iy - 2, px1 - CPADS + 3, iy + ITEM_H - 5,
                    fill=ac(col, 32), r=6)

        if indent > 0:
            d2.circle(tx + 5, iy + ITEM_H // 2 - 2,
                      4 if hi else 3, fill=cm)
            tx += 14

        d2.text(tx, iy + 2, name, f_name, fill=fc)

        if ann:
            ne = tx + d2.textw(name, f_name) + 10
            aw = d2.textw(ann, F_ANN)
            if ne + aw <= px1 - CPADS:
                d2.text(ne, iy + 5, ann, F_ANN, fill=DIM)

        iy += ITEM_H

save(img2, ASSETS / "dir_structure.png")
print("Done.")
