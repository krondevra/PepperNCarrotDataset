"""
Generate README assets from ep01 E01P02.

  assets/pipeline.png        — before/after panel
  assets/variants_grid.png   — grid of all variants
  assets/variants_demo.gif   — animated GIF of all variants

Run from project root: python3 src/make_assets.py
"""

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

RENDERS = Path("data/preprocessing/renders/ep01_Potion-of-Flight")
DATASET = Path("data/dataset/ep01_Potion-of-Flight")
ASSETS  = Path("assets")
ASSETS.mkdir(exist_ok=True)

PAGE = "E01P02.png"
DARK = (28, 28, 28)

def load_font(size, bold=True):
    for path in [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else '-Regular'}.ttf",
    ]:
        try: return ImageFont.truetype(path, size)
        except: pass
    return ImageFont.load_default()

FONT_LG = load_font(20)
FONT_SM = load_font(15, bold=False)

def fit_width(img, w):
    return img.resize((w, int(img.height * w / img.width)), Image.LANCZOS)

def checker_bg(size, sq=12):
    bg = Image.new("RGBA", size, (200, 200, 200, 255))
    d = ImageDraw.Draw(bg)
    for y in range(0, size[1], sq):
        for x in range(0, size[0], sq):
            if (x//sq + y//sq) % 2 == 0:
                d.rectangle([x, y, x+sq-1, y+sq-1], fill=(240, 240, 240, 255))
    return bg

def on_bg(img, color=None):
    bg = checker_bg(img.size) if color is None else Image.new("RGBA", img.size, color+(255,))
    bg.alpha_composite(img); return bg

def panel_bounds(path):
    alpha = np.array(Image.open(path).convert("RGBA").getchannel("A"))
    center = alpha[:, alpha.shape[1]//10: 9*alpha.shape[1]//10]
    rows = center.max(axis=1) > 0
    panels, in_p, s = [], False, 0
    for i, v in enumerate(rows):
        if v and not in_p: s=i; in_p=True
        elif not v and in_p: panels.append((s,i)); in_p=False
    if in_p: panels.append((s, len(rows)))
    return max(panels, key=lambda p: p[1]-p[0]) if panels else (0, alpha.shape[0])

def crop(img, y1, y2, gap=18):
    return img.crop((0, max(0,y1-gap), img.width, min(img.height,y2+gap)))

def label_bar(w, top, sub=""):
    lh = 44 if sub else 34
    b = Image.new("RGBA", (w, lh), DARK+(255,))
    d = ImageDraw.Draw(b)
    d.text((10,7), top, font=FONT_LG, fill=(245,245,245))
    if sub: d.text((10,28), sub, font=FONT_SM, fill=(155,155,155))
    return b

def with_label(img, top, sub=""):
    bar = label_bar(img.width, top, sub)
    out = Image.new("RGBA", (img.width, img.height+bar.height), DARK+(255,))
    out.paste(bar, (0,0)); out.paste(img, (0,bar.height)); return out

Y1, Y2 = panel_bounds(RENDERS / "cleaned" / PAGE)

# (folder, source, transparent, label, sublabel)
VARIANTS = [
    ("cleaned",              "renders", True,  "cleaned",              "target — transparent borders"),
    ("initial",              "renders", False, "initial",              "raw KRA export"),
    ("black",                "dataset", False, "black",                "black background"),
    ("framed",               "dataset", False, "framed",               "white bg + 1px frame"),
    ("framed_cleaned",       "dataset", True,  "framed cleaned",       "transparent bg + 1px frame"),
    ("framed_jpeg",          "dataset", False, "framed jpeg",          "white bg + frame + JPEG q15"),
    ("framed_jpeg_cleaned",  "dataset", True,  "framed jpeg cleaned",  "transparent bg + frame + JPEG q15"),
    ("gradient_border",      "dataset", False, "gradient border",      "borders black→white"),
    ("gradient_border_inv",  "dataset", False, "gradient border inv",  "borders white→black"),
    ("jpeg",                 "dataset", False, "jpeg",                 "initial + JPEG q15"),
    ("jpeg_cleaned",         "dataset", True,  "jpeg cleaned",         "cleaned + JPEG artifacts"),
    ("sfx_overlay",          "dataset", False, "sfx overlay",          "Korean SFX on initial"),
    ("sfx_overlay_cleaned",  "dataset", True,  "sfx overlay cleaned",  "SFX on cleaned (RGBA)"),
    ("bubble_overlay",       "dataset", False, "bubble overlay",       "speech bubbles on initial"),
    ("bubble_overlay_cleaned","dataset",True,  "bubble overlay cleaned","bubbles on cleaned (RGBA)"),
]

def get_path(folder, source):
    p = (RENDERS if source == "renders" else DATASET) / folder / PAGE
    return p if p.exists() else None

def render_panel(folder, source, transparent, w):
    p = get_path(folder, source)
    if p is None: return None
    raw = crop(Image.open(p).convert("RGBA"), Y1, Y2)
    vis = on_bg(raw) if transparent else on_bg(raw, (255,255,255))
    return fit_width(vis, w)

# ── GRID ──────────────────────────────────────────────────────────────────────
print("Building variants_grid.png ...")
CELL_W, COLS, PAD = 360, 3, 6
ZOOM_SRC, ZOOM_SCALE = 16, 5
ZOOM_DSP = ZOOM_SRC * ZOOM_SCALE
INSET_PAD = 4

cells = []
for folder, source, transp, lbl, sub in VARIANTS:
    vis = render_panel(folder, source, transp, CELL_W)
    if vis is None: continue
    ph = vis.height
    zx1 = CELL_W * 82 // 100
    zy1 = ph - ZOOM_SRC
    zoom = vis.crop((zx1, zy1, zx1+ZOOM_SRC, ph)).resize((ZOOM_DSP,ZOOM_DSP), Image.NEAREST)
    vis_r = vis.convert("RGB")
    d = ImageDraw.Draw(vis_r)
    d.rectangle([zx1-2, zy1-2, zx1+ZOOM_SRC-1, ph-1], outline=(255,60,60), width=2)
    ix, iy = CELL_W-ZOOM_DSP-INSET_PAD, ph-ZOOM_DSP-INSET_PAD-30
    vis_r.paste(zoom.convert("RGB"), (ix, iy))
    d.rectangle([ix-2, iy-2, ix+ZOOM_DSP, iy+ZOOM_DSP], outline=(255,60,60), width=2)
    cells.append(with_label(Image.fromarray(np.array(vis_r)).convert("RGBA"), lbl, sub).convert("RGB"))

ROWS = (len(cells)+COLS-1)//COLS
cH = cells[0].height
GW = COLS*CELL_W+(COLS+1)*PAD; GH = ROWS*cH+(ROWS+1)*PAD
grid = Image.new("RGB", (GW,GH), (55,55,55))
for i, cell in enumerate(cells):
    r,c = divmod(i, COLS)
    grid.paste(cell, (PAD+c*(CELL_W+PAD), PAD+r*(cH+PAD)))
grid.save(ASSETS/"variants_grid.png")
print(f"  -> {GW}x{GH}, {COLS}x{ROWS} ({len(cells)} cells)")

# ── GIF ───────────────────────────────────────────────────────────────────────
print("Building variants_demo.gif ...")
MAIN_W, LABEL_H = 580, 44
frames = []
for folder, source, transp, lbl, sub in VARIANTS:
    vis = render_panel(folder, source, transp, MAIN_W)
    if vis is None: continue
    ph = vis.height
    zx1 = MAIN_W * 82 // 100
    zy1 = ph - ZOOM_SRC*2
    zoom = vis.crop((zx1, zy1, zx1+ZOOM_SRC*2, ph)).resize((ZOOM_DSP,ZOOM_DSP), Image.NEAREST)
    vis_r = vis.convert("RGB")
    d = ImageDraw.Draw(vis_r)
    d.rectangle([zx1-2, zy1-2, zx1+ZOOM_SRC*2-1, ph-1], outline=(255,60,60), width=2)
    ix, iy = MAIN_W-ZOOM_DSP-INSET_PAD, ph-ZOOM_DSP-INSET_PAD-45
    vis_r.paste(zoom.convert("RGB"), (ix, iy))
    d.rectangle([ix-2, iy-2, ix+ZOOM_DSP, iy+ZOOM_DSP], outline=(255,60,60), width=2)
    canvas = Image.new("RGB", (MAIN_W, LABEL_H+ph), DARK)
    canvas.paste(label_bar(MAIN_W, lbl, sub).convert("RGB"), (0,0))
    canvas.paste(vis_r, (0, LABEL_H))
    frames.append(canvas.convert("P", palette=Image.ADAPTIVE, colors=256))

frames[0].save(ASSETS/"variants_demo.gif", save_all=True, append_images=frames[1:],
               duration=2000, loop=0, optimize=False)
print(f"  -> {MAIN_W}x{frames[0].height}, {len(frames)} frames")

# ── PIPELINE ──────────────────────────────────────────────────────────────────
print("Building pipeline.png ...")
HW, AW = 400, 56
before = fit_width(on_bg(crop(Image.open(RENDERS/"initial"/PAGE).convert("RGBA"),Y1,Y2),(255,255,255)), HW)
after  = fit_width(on_bg(crop(Image.open(RENDERS/"cleaned"/PAGE).convert("RGBA"),Y1,Y2)), HW)
bl = with_label(before, "Before", "raw KRA export — borders intact")
al = with_label(after,  "After",  "transparent borders — training target")
H = max(bl.height, al.height); W = HW*2+AW
pipe = Image.new("RGB", (W,H), DARK)
pipe.paste(bl.convert("RGB"), (0,0)); pipe.paste(al.convert("RGB"), (HW+AW,0))
d = ImageDraw.Draw(pipe)
my = H//2; ax0,ax1 = HW+8, HW+AW-8
d.line([(ax0,my),(ax1,my)], fill=(180,180,180), width=3)
d.polygon([(ax1,my-8),(ax1,my+8),(ax1+8,my)], fill=(180,180,180))
pipe.save(ASSETS/"pipeline.png")
print(f"  -> {W}x{H}")
print("Done.")
