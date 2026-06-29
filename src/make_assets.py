"""
Generate README assets:
  assets/variants_demo.gif   — animated GIF cycling through all 11 dataset variants
  assets/sample_demo.gif     — animated GIF showing initial→cleaned across 6 episodes
  assets/pipeline.png        — before/after single panel, dark background
  assets/variants_grid.png   — 3×4 grid, single panel per variant

Run from project root: python3 src/make_assets.py
Requires: data/preprocessing/renders/ and data/dataset/ep01_Potion-of-Flight/
"""

from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont

RENDERS = Path("data/preprocessing/renders")
DATASET = Path("data/dataset")
ASSETS  = Path("assets")
ASSETS.mkdir(exist_ok=True)

EP   = "ep01_Potion-of-Flight"
PAGE = "E01P02.png"

DARK = (28, 28, 28)

# ── fonts ─────────────────────────────────────────────────────────────────────
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

FONT_LG = load_font(20)
FONT_SM = load_font(15, bold=False)

# ── helpers ───────────────────────────────────────────────────────────────────
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


def detect_first_panel_bounds(cleaned_path: Path):
    img   = Image.open(cleaned_path).convert("RGBA")
    alpha = np.array(img.getchannel("A"))
    w     = alpha.shape[1]
    center = alpha[:, w // 10: 9 * w // 10]
    has_content = center.max(axis=1) > 0
    start, end, in_panel = None, img.height, False
    for i, v in enumerate(has_content):
        if v and not in_panel:
            start = i; in_panel = True
        elif not v and in_panel:
            end = i; break
    return start or 0, end


PANEL_Y1, PANEL_Y2 = detect_first_panel_bounds(RENDERS / EP / "cleaned" / PAGE)
PANEL_GAP = 18


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


# (folder, source, role, description)
# source: "renders" → RENDERS/EP/{folder}/PAGE  |  "dataset" → DATASET/EP/{folder}/PAGE
VARIANTS = [
    ("cleaned",              "renders", "Target", "transparent borders — clean artwork"),
    ("initial",              "renders", "Input",  "raw KRA export, borders intact"),
    ("black",                "dataset", "Input",  "black background"),
    ("framed",               "dataset", "Input",  "white bg + 1px black frame"),
    ("framed_cleaned",       "dataset", "Input",  "transparent bg + 1px frame"),
    ("framed_jpeg",          "dataset", "Input",  "white bg + frame + JPEG q15"),
    ("framed_jpeg_cleaned",  "dataset", "Input",  "transparent bg + frame + JPEG q15"),
    ("gradient_border",      "dataset", "Input",  "borders filled black→white gradient"),
    ("gradient_border_inv",  "dataset", "Input",  "borders filled white→black gradient"),
    ("jpeg",                 "dataset", "Input",  "initial render + JPEG q15"),
    ("jpeg_cleaned",         "dataset", "Input",  "cleaned artwork + JPEG artifacts"),
]


def variant_path(folder, source):
    if source == "renders":
        return RENDERS / EP / folder / PAGE
    return DATASET / EP / folder / PAGE


def has_transparency(folder):
    return "cleaned" in folder


# ══════════════════════════════════════════════════════════════════════════════
# GIF 1 — variants_demo: all 11 variants of one panel with zoom inset
# ══════════════════════════════════════════════════════════════════════════════
print("Building variants_demo.gif ...")

MAIN_W     = 580
ZOOM_SCALE = 5
ZOOM_SRC   = 20
ZOOM_DSP   = ZOOM_SRC * ZOOM_SCALE
INSET_PAD  = 4
LABEL_H    = 44

frames = []
for folder, source, role, desc in VARIANTS:
    src = variant_path(folder, source)
    if not src.exists():
        print(f"  missing {src}"); continue

    raw   = Image.open(src).convert("RGBA")
    panel = crop_panel(raw)
    vis   = composite_on_bg(panel) if has_transparency(folder) else composite_on_bg(panel, (255, 255, 255))
    vis   = fit_width(vis, MAIN_W)
    ph    = vis.height

    border_start_x = int(MAIN_W * (2481 - 102) / 2481)
    shift = ZOOM_SRC // 4
    zx1 = min(border_start_x - ZOOM_SRC // 2 + shift, MAIN_W - ZOOM_SRC)
    zx2 = zx1 + ZOOM_SRC
    zy1, zy2 = ph - ZOOM_SRC, ph

    zoom_crop = vis.crop((zx1, zy1, zx2, zy2))
    zoom_big  = zoom_crop.resize((ZOOM_DSP, ZOOM_DSP), Image.NEAREST)

    vis_m = vis.copy().convert("RGB")
    draw  = ImageDraw.Draw(vis_m)
    draw.rectangle([zx1 - 2, zy1 - 2, zx2 - 1, zy2 - 1], outline=(255, 60, 60), width=2)
    ix = MAIN_W - ZOOM_DSP - INSET_PAD
    iy = ph     - ZOOM_DSP - INSET_PAD - 45
    vis_m.paste(zoom_big.convert("RGB"), (ix, iy))
    draw.rectangle([ix - 2, iy - 2, ix + ZOOM_DSP, iy + ZOOM_DSP], outline=(255, 60, 60), width=2)

    canvas = Image.new("RGB", (MAIN_W, LABEL_H + ph), DARK)
    bar = label_bar(MAIN_W, f"{folder.replace('_', ' ')}  —  {role}", desc)
    canvas.paste(bar.convert("RGB"), (0, 0))
    canvas.paste(vis_m, (0, LABEL_H))

    frames.append(canvas.convert("P", palette=Image.ADAPTIVE, colors=256))

frames[0].save(
    ASSETS / "variants_demo.gif",
    save_all=True, append_images=frames[1:],
    duration=2000, loop=0, optimize=False,
)
print(f"  -> assets/variants_demo.gif  ({len(frames)} frames, {MAIN_W}×{frames[0].height})")


# ══════════════════════════════════════════════════════════════════════════════
# GIF 2 — sample_demo: initial → cleaned pairs from 6 different episodes
# ══════════════════════════════════════════════════════════════════════════════
print("Building sample_demo.gif ...")

SAMPLE_EPS = [
    "ep01_Potion-of-Flight",
    "ep06_The-Potion-Contest",
    "ep10_Summer-Special",
    "ep15_The-Crystal-Ball",
    "ep20_The-Picnic",
    "ep25_There-are-no-Shortcuts",
]

HALF_W  = 360
ARROW_W = 40
TOTAL_W = HALF_W * 2 + ARROW_W
S_LABEL = 44
S_EP_H  = 32

sample_frames = []
for ep_name in SAMPLE_EPS:
    ep_renders = RENDERS / ep_name
    if not ep_renders.exists():
        print(f"  skip {ep_name}: no renders"); continue

    pages = sorted((ep_renders / "cleaned").glob("*.png"))
    if len(pages) < 2:
        page_name = pages[0].name if pages else None
    else:
        page_name = pages[1].name  # P02 — first proper content page

    if not page_name:
        print(f"  skip {ep_name}: no pages"); continue

    init_path    = ep_renders / "initial" / page_name
    cleaned_path = ep_renders / "cleaned" / page_name
    if not init_path.exists() or not cleaned_path.exists():
        print(f"  skip {ep_name}: missing renders"); continue

    # Detect first panel bounds for this episode/page
    p_y1, p_y2 = detect_first_panel_bounds(cleaned_path)
    gap = 18

    def crop_ep(img):
        y1 = max(0, p_y1 - gap)
        y2 = min(img.height, p_y2 + gap)
        return img.crop((0, y1, img.width, y2))

    raw_init    = Image.open(init_path).convert("RGBA")
    raw_cleaned = Image.open(cleaned_path).convert("RGBA")

    init_vis    = fit_width(composite_on_bg(crop_ep(raw_init),    (255, 255, 255)), HALF_W)
    cleaned_vis = fit_width(composite_on_bg(crop_ep(raw_cleaned), None),            HALF_W)

    H = max(init_vis.height, cleaned_vis.height)

    ep_label_h = S_EP_H
    frame_h    = ep_label_h + S_LABEL + H

    canvas = Image.new("RGB", (TOTAL_W, frame_h), DARK)
    draw   = ImageDraw.Draw(canvas)

    # Episode name bar across full width
    ep_short = ep_name.replace("-", " ").replace("_", "  ")
    draw.text((8, 6), ep_short, font=FONT_SM, fill=(180, 180, 180))

    # Column labels
    init_bar    = label_bar(HALF_W, "initial",  "raw KRA export — borders intact")
    cleaned_bar = label_bar(HALF_W, "cleaned",  "border-removed RGBA — training target")
    canvas.paste(init_bar.convert("RGB"),    (0,              ep_label_h))
    canvas.paste(cleaned_bar.convert("RGB"), (HALF_W + ARROW_W, ep_label_h))

    # Panel images
    canvas.paste(init_vis.convert("RGB"),    (0,              ep_label_h + S_LABEL))
    canvas.paste(cleaned_vis.convert("RGB"), (HALF_W + ARROW_W, ep_label_h + S_LABEL))

    # Arrow
    mid_y  = ep_label_h + S_LABEL + H // 2
    ax0, ax1 = HALF_W + 6, HALF_W + ARROW_W - 6
    draw.line([(ax0, mid_y), (ax1, mid_y)], fill=(180, 180, 180), width=3)
    draw.polygon([(ax1, mid_y - 8), (ax1, mid_y + 8), (ax1 + 8, mid_y)], fill=(180, 180, 180))

    sample_frames.append(canvas.convert("P", palette=Image.ADAPTIVE, colors=256))
    print(f"  {ep_name}  ({page_name})")

if sample_frames:
    sample_frames[0].save(
        ASSETS / "sample_demo.gif",
        save_all=True, append_images=sample_frames[1:],
        duration=2500, loop=0, optimize=False,
    )
    print(f"  -> assets/sample_demo.gif  ({len(sample_frames)} frames, {TOTAL_W}×{sample_frames[0].height})")
else:
    print("  No frames — check that renders exist for sampled episodes")


# ══════════════════════════════════════════════════════════════════════════════
# PIPELINE — before / after, dark background
# ══════════════════════════════════════════════════════════════════════════════
print("Building pipeline.png ...")

HALF_W_P = 400
ARROW_W_P = 56

def load_panel(folder, source, bg_color=None):
    raw = Image.open(variant_path(folder, source)).convert("RGBA")
    return fit_width(composite_on_bg(crop_panel(raw), bg_color), HALF_W_P)

before = load_panel("initial",  "renders", (255, 255, 255))
after  = load_panel("cleaned",  "renders", None)

before_lab = stack_label(before, "Before", "raw KRA export — borders intact")
after_lab  = stack_label(after,  "After",  "transparent borders — training target")

H = max(before_lab.height, after_lab.height)
W = HALF_W_P * 2 + ARROW_W_P

pipeline = Image.new("RGB", (W, H), DARK)
pipeline.paste(before_lab.convert("RGB"), (0, 0))
pipeline.paste(after_lab.convert("RGB"),  (HALF_W_P + ARROW_W_P, 0))

draw  = ImageDraw.Draw(pipeline)
mid_y = H // 2
ax0, ax1 = HALF_W_P + 8, HALF_W_P + ARROW_W_P - 8
draw.line([(ax0, mid_y), (ax1, mid_y)], fill=(180, 180, 180), width=3)
draw.polygon([(ax1, mid_y - 8), (ax1, mid_y + 8), (ax1 + 8, mid_y)], fill=(180, 180, 180))

pipeline.save(ASSETS / "pipeline.png")
print(f"  -> assets/pipeline.png  ({W}×{H})")


# ══════════════════════════════════════════════════════════════════════════════
# GRID — 3×4, one panel per variant cell
# ══════════════════════════════════════════════════════════════════════════════
print("Building variants_grid.png ...")

CELL_W       = 360
COLS         = 3
PAD_G        = 6
GRID_ZOOM_SRC = 16
GRID_ZOOM_DSP = GRID_ZOOM_SRC * 5

cells = []
for folder, source, role, desc in VARIANTS:
    src = variant_path(folder, source)
    if not src.exists():
        continue
    raw   = Image.open(src).convert("RGBA")
    panel = crop_panel(raw)
    vis   = composite_on_bg(panel) if has_transparency(folder) else composite_on_bg(panel, (255, 255, 255))
    vis   = fit_width(vis, CELL_W)
    ph    = vis.height

    border_start_x = int(CELL_W * (2481 - 102) / 2481)
    shift = GRID_ZOOM_SRC // 4
    zx1 = min(border_start_x - GRID_ZOOM_SRC // 2 + shift, CELL_W - GRID_ZOOM_SRC)
    zx2 = zx1 + GRID_ZOOM_SRC
    zy1, zy2 = ph - GRID_ZOOM_SRC, ph

    zoom_big = vis.crop((zx1, zy1, zx2, zy2)).resize((GRID_ZOOM_DSP, GRID_ZOOM_DSP), Image.NEAREST)

    vis_m = vis.copy().convert("RGB")
    draw  = ImageDraw.Draw(vis_m)
    draw.rectangle([zx1-2, zy1-2, zx2-1, zy2-1], outline=(255, 60, 60), width=2)
    ix = CELL_W - GRID_ZOOM_DSP - INSET_PAD
    iy = ph     - GRID_ZOOM_DSP - INSET_PAD - 30
    vis_m.paste(zoom_big.convert("RGB"), (ix, iy))
    draw.rectangle([ix-2, iy-2, ix+GRID_ZOOM_DSP, iy+GRID_ZOOM_DSP], outline=(255, 60, 60), width=2)

    cell = stack_label(Image.fromarray(np.array(vis_m)).convert("RGBA"),
                       folder.replace("_", " "), f"{role} — {desc}")
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
print(f"  -> assets/variants_grid.png  ({GW}×{GH}, {COLS}×{ROWS})")

print("\nDone.")
