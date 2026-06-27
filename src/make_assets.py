"""
Generate README assets:
  assets/variants_demo.gif   — animated GIF, 1 panel + zoom inset (bottom-right)
  assets/pipeline.png        — before/after, single panel, dark background
  assets/variants_grid.png   — 3x3 grid, single panel per cell

Run from project root: python3 src/make_assets.py
"""

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

SYNTH  = Path("data/synthesized/ep01_Potion-of-Flight")
ASSETS = Path("assets")
ASSETS.mkdir(exist_ok=True)

PAGE = "E01P02.png"

DARK = (28, 28, 28)

# ── fonts ────────────────────────────────────────────────────────────────────
def load_font(size, bold=True):
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else '-Regular'}.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

FONT_LG  = load_font(20)
FONT_SM  = load_font(15, bold=False)

# ── helpers ──────────────────────────────────────────────────────────────────
def fit_width(img: Image.Image, w: int) -> Image.Image:
    h = int(img.height * w / img.width)
    return img.resize((w, h), Image.LANCZOS)


def checker_bg(size, sq=12, c1=(200, 200, 200), c2=(240, 240, 240)):
    bg = Image.new("RGBA", size, c1 + (255,))
    draw = ImageDraw.Draw(bg)
    for y in range(0, size[1], sq):
        for x in range(0, size[0], sq):
            if (x // sq + y // sq) % 2 == 0:
                draw.rectangle([x, y, x + sq - 1, y + sq - 1], fill=c2 + (255,))
    return bg


def composite_on_bg(img: Image.Image, bg_color=None) -> Image.Image:
    bg = checker_bg(img.size) if bg_color is None else Image.new("RGBA", img.size, bg_color + (255,))
    bg.alpha_composite(img)
    return bg


def detect_first_panel_bounds(ref_path: Path):
    """Y bounds of first content panel, detected via alpha from the transparent variant."""
    img = Image.open(ref_path).convert("RGBA")
    alpha = np.array(img.getchannel("A"))
    w = alpha.shape[1]
    center = alpha[:, w // 10: 9 * w // 10]
    has_content = center.max(axis=1) > 0
    start, end, in_panel = None, img.height, False
    for i, v in enumerate(has_content):
        if v and not in_panel:
            start = i; in_panel = True
        elif not v and in_panel:
            end = i; break
    return start or 0, end


PANEL_Y1, PANEL_Y2 = detect_first_panel_bounds(SYNTH / "transparent" / PAGE)
PANEL_GAP = 18   # extra rows above/below panel (in original image space) to show border strip


def crop_panel(img: Image.Image) -> Image.Image:
    y1 = max(0, PANEL_Y1 - PANEL_GAP)
    y2 = min(img.height, PANEL_Y2 + PANEL_GAP)
    return img.crop((0, y1, img.width, y2))


def label_bar(width, top_text, sub_text="", bg=DARK):
    lh = 44 if sub_text else 34
    bar = Image.new("RGBA", (width, lh), bg + (255,))
    draw = ImageDraw.Draw(bar)
    draw.text((10, 7),  top_text, font=FONT_LG, fill=(245, 245, 245))
    if sub_text:
        draw.text((10, 28), sub_text, font=FONT_SM, fill=(155, 155, 155))
    return bar


def stack_label(img: Image.Image, top_text, sub_text="") -> Image.Image:
    bar = label_bar(img.width, top_text, sub_text)
    out = Image.new("RGBA", (img.width, img.height + bar.height), DARK + (255,))
    out.paste(bar, (0, 0))
    out.paste(img, (0, bar.height))
    return out


# ── variant list ─────────────────────────────────────────────────────────────
VARIANTS = [
    ("transparent",             "Target", "clean artwork, transparent borders"),
    ("white",                   "Input",  "white borders - raw KRA export"),
    ("black",                   "Input",  "black background"),
    ("framed",                  "Input",  "white bg + 1px black frame"),
    ("jpeg",                    "Input",  "white borders + JPEG q15"),
    ("framed_jpeg",             "Input",  "white bg + frame + JPEG q15"),
    ("transparent_framed",      "Input",  "transparent + 1px black frame"),
    ("transparent_jpeg",        "Input",  "transparent + JPEG q15"),
    ("transparent_framed_jpeg", "Input",  "transparent + frame + JPEG q15"),
]


# ══════════════════════════════════════════════════════════════════════════════
# GIF — single panel, zoom inset overlaid at bottom-right corner
# ══════════════════════════════════════════════════════════════════════════════
print("Building variants_demo.gif ...")

MAIN_W     = 580
ZOOM_SCALE = 5
ZOOM_SRC   = 20   # source region in resized image (px)
ZOOM_DSP   = ZOOM_SRC * ZOOM_SCALE   # 100px inset
INSET_PAD  = 4    # inset distance from panel edge
LABEL_H    = 44

frames = []
for folder, role, desc in VARIANTS:
    src = SYNTH / folder / PAGE
    if not src.exists():
        print(f"  missing {src}"); continue

    raw   = Image.open(src).convert("RGBA")
    panel = crop_panel(raw)

    if "transparent" in folder:
        vis = composite_on_bg(panel)
    elif folder == "black":
        vis = composite_on_bg(panel, (0, 0, 0))
    else:
        vis = composite_on_bg(panel, (255, 255, 255))

    vis = fit_width(vis, MAIN_W)
    ph  = vis.height

    # Zoom source: straddle the artwork/border boundary, shifted slightly toward
    # the corner so more of the border area (and its artifacts) is included.
    border_start_x = int(MAIN_W * (2481 - 102) / 2481)  # artwork/border transition
    shift = ZOOM_SRC // 4   # nudge source toward the right corner
    zx1 = min(border_start_x - ZOOM_SRC // 2 + shift, MAIN_W - ZOOM_SRC)
    zx2 = zx1 + ZOOM_SRC
    zy1, zy2 = ph - ZOOM_SRC, ph

    zoom_crop = vis.crop((zx1, zy1, zx2, zy2))
    zoom_big  = zoom_crop.resize((ZOOM_DSP, ZOOM_DSP), Image.NEAREST)

    # Draw red source indicator on panel (flush corner)
    vis_m = vis.copy().convert("RGB")
    draw  = ImageDraw.Draw(vis_m)
    draw.rectangle([zx1 - 2, zy1 - 2, zx2 - 1, zy2 - 1], outline=(255, 60, 60), width=2)

    # Paste zoom inset slightly above bottom-right so the red source box is visible below it
    ix = MAIN_W - ZOOM_DSP - INSET_PAD
    iy = ph      - ZOOM_DSP - INSET_PAD - 45
    vis_m.paste(zoom_big.convert("RGB"), (ix, iy))
    draw.rectangle([ix - 2, iy - 2, ix + ZOOM_DSP, iy + ZOOM_DSP],
                   outline=(255, 60, 60), width=2)

    # Assemble full frame
    canvas = Image.new("RGB", (MAIN_W, LABEL_H + ph), DARK)
    bar = label_bar(MAIN_W, f"{folder.replace('_', ' ')}  -  {role}", desc)
    canvas.paste(bar.convert("RGB"), (0, 0))
    canvas.paste(vis_m, (0, LABEL_H))

    frames.append(canvas.convert("P", palette=Image.ADAPTIVE, colors=256))

frames[0].save(
    ASSETS / "variants_demo.gif",
    save_all=True, append_images=frames[1:],
    duration=2000, loop=0, optimize=False,
)
print(f"  -> assets/variants_demo.gif  ({len(frames)} frames, {MAIN_W}x{frames[0].height})")


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE — before / after, dark background between panels
# ══════════════════════════════════════════════════════════════════════════════
print("Building pipeline.png ...")

HALF_W = 400
ARROW_W = 56

def load_panel(folder, bg_color=None):
    raw = Image.open(SYNTH / folder / PAGE).convert("RGBA")
    return fit_width(composite_on_bg(crop_panel(raw), bg_color), HALF_W)

before = load_panel("white",       (255, 255, 255))
after  = load_panel("transparent", None)

before_lab = stack_label(before, "Before", "white borders - raw KRA export")
after_lab  = stack_label(after,  "After",  "transparent borders - target output")

H = max(before_lab.height, after_lab.height)
W = HALF_W * 2 + ARROW_W

pipeline = Image.new("RGB", (W, H), DARK)
pipeline.paste(before_lab.convert("RGB"), (0, 0))
pipeline.paste(after_lab.convert("RGB"),  (HALF_W + ARROW_W, 0))

draw  = ImageDraw.Draw(pipeline)
mid_y = H // 2
ax0, ax1 = HALF_W + 8, HALF_W + ARROW_W - 8
draw.line([(ax0, mid_y), (ax1, mid_y)], fill=(180, 180, 180), width=3)
draw.polygon([(ax1, mid_y - 8), (ax1, mid_y + 8), (ax1 + 8, mid_y)], fill=(180, 180, 180))

pipeline.save(ASSETS / "pipeline.png")
print(f"  -> assets/pipeline.png  ({W}x{H})")


# ══════════════════════════════════════════════════════════════════════════════
# GRID — 3x3, single panel per cell
# ══════════════════════════════════════════════════════════════════════════════
print("Building variants_grid.png ...")

CELL_W = 360
COLS   = 3
PAD_G  = 6

cells = []
for folder, role, desc in VARIANTS:
    src = SYNTH / folder / PAGE
    if not src.exists():
        continue
    raw   = Image.open(src).convert("RGBA")
    panel = crop_panel(raw)
    if "transparent" in folder:
        vis = composite_on_bg(panel)
    elif folder == "black":
        vis = composite_on_bg(panel, (0, 0, 0))
    else:
        vis = composite_on_bg(panel, (255, 255, 255))
    vis  = fit_width(vis, CELL_W)
    cell = stack_label(vis, folder.replace("_", " "), f"{role} - {desc}")
    cells.append(cell.convert("RGB"))

ROWS   = (len(cells) + COLS - 1) // COLS
cell_h = cells[0].height
GW = COLS * CELL_W + (COLS + 1) * PAD_G
GH = ROWS * cell_h + (ROWS + 1) * PAD_G
grid = Image.new("RGB", (GW, GH), (55, 55, 55))

for i, cell in enumerate(cells):
    row, col = divmod(i, COLS)
    x = PAD_G + col * (CELL_W + PAD_G)
    y = PAD_G + row * (cell_h + PAD_G)
    grid.paste(cell, (x, y))

grid.save(ASSETS / "variants_grid.png")
print(f"  -> assets/variants_grid.png  ({GW}x{GH}, {COLS}x{ROWS})")

print("\nDone.")
