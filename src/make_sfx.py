"""
Generate Korean manhwa SFX + expression overlay images.
Output: data/overlays/sfx/  (RGBA PNG, transparent background)

Each word is rendered in 7 style variants:
  (none)       black fill, white outline
  _inv         white fill, black outline
  _blur        Gaussian blur of normal
  _inv_blur    Gaussian blur of inverted
  _grad        black→white gradient fill, white outline
  _color_black black→random colour gradient, white outline
  _color_white white→random colour gradient, white outline

Requires: data/fonts/NotoSansKR-Bold.ttf
  curl -sL 'https://fonts.gstatic.com/s/notosanskr/v39/PbyxFmXiEBPT4ITbgNA5Cgms3VYcOA-vvnIzzg01eLQ.ttf' \\
       -o data/fonts/NotoSansKR-Bold.ttf

Run from project root: python3 src/make_sfx.py
"""

import math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pathlib import Path

FONT_PATH = Path("data/fonts/NotoSansKR-Bold.ttf")
OUT       = Path("data/overlays/sfx")
OUT.mkdir(parents=True, exist_ok=True)

if not FONT_PATH.exists():
    raise FileNotFoundError(
        f"Korean font missing at {FONT_PATH}. Run:\n"
        "  curl -sL 'https://fonts.gstatic.com/s/notosanskr/v39/"
        "PbyxFmXiEBPT4ITbgNA5Cgms3VYcOA-vvnIzzg01eLQ.ttf' "
        "-o data/fonts/NotoSansKR-Bold.ttf"
    )

random.seed(17)
np.random.seed(17)

CW, CH = 700, 500

SFX = {
    "simple": ["쿵", "펑", "탁", "퍽", "빵", "쫙"],
    "double": ["번쩍", "우르", "슈웅", "파직", "뻐걱", "쾅쾅"],
    "long":   ["우르르", "슈아아", "콰아앙", "파바박"],
}
EXPR = {
    "exclaim": ["야", "아", "어", "헐", "뭐", "왜"],
    "emotion": ["이런", "아이고", "세상에", "젠장", "제기랄"],
    "rude":    ["닥쳐", "꺼져", "망할", "씨발", "개새끼"],
    "scream":  ["아아아", "야아아", "으아아", "이이이"],
}

# ── renderers ─────────────────────────────────────────────────────────────────

def _text_canvas(text, font_size, outline_w):
    font = ImageFont.truetype(str(FONT_PATH), font_size)
    tmp  = Image.new("RGBA", (1, 1))
    bb   = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    pad  = outline_w * 3 + 4
    cw, ch = tw + pad * 2, th + pad * 2
    return font, cw, ch, cw // 2, ch // 2


def _draw_outline(draw, cx, cy, text, font, outline_w, outline_rgba):
    for dx in range(-outline_w, outline_w + 1):
        for dy in range(-outline_w, outline_w + 1):
            if dx * dx + dy * dy <= outline_w * outline_w:
                draw.text((cx + dx, cy + dy), text, font=font,
                          fill=outline_rgba, anchor="mm")


def render_solid(text, font_size, outline_w, angle, fill_rgba, outline_rgba):
    font, cw, ch, cx, cy = _text_canvas(text, font_size, outline_w)
    img  = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _draw_outline(draw, cx, cy, text, font, outline_w, outline_rgba)
    draw.text((cx, cy), text, font=font, fill=fill_rgba, anchor="mm")
    return img.rotate(angle, expand=True, resample=Image.BICUBIC)


def render_gradient(text, font_size, outline_w, angle, mode):
    font, cw, ch, cx, cy = _text_canvas(text, font_size, outline_w)

    # text alpha mask
    mask_img = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask_img).text((cx, cy), text, font=font, fill=255, anchor="mm")
    mask = np.array(mask_img)

    # gradient
    if mode == "grad":
        direction = random.choice(["v", "h", "d"])
        if direction == "v":
            base = np.linspace(0, 255, ch)[:, np.newaxis] * np.ones((1, cw))
        elif direction == "h":
            base = np.ones((ch, 1)) * np.linspace(0, 255, cw)[np.newaxis, :]
        else:
            v = np.linspace(0, 255, ch)[:, np.newaxis]
            h = np.linspace(0, 255, cw)[np.newaxis, :]
            base = (v + h) / 2
        if random.random() > 0.5:
            base = 255 - base
        base = base.astype(np.uint8)
        r = g = b = base
    else:
        rand_c = np.array([random.randint(80, 255),
                           random.randint(80, 255),
                           random.randint(80, 255)])
        anchor = np.array([0, 0, 0] if mode == "color_black" else [255, 255, 255])
        c1, c2 = (anchor, rand_c) if random.random() > 0.5 else (rand_c, anchor)
        t   = np.linspace(0, 1, ch)[:, np.newaxis]
        rgb = ((1 - t) * c1 + t * c2).astype(np.uint8)
        r   = np.tile(rgb[:, 0:1], (1, cw))
        g   = np.tile(rgb[:, 1:2], (1, cw))
        b   = np.tile(rgb[:, 2:3], (1, cw))

    fill_arr          = np.zeros((ch, cw, 4), dtype=np.uint8)
    fill_arr[:, :, 0] = r
    fill_arr[:, :, 1] = g
    fill_arr[:, :, 2] = b
    fill_arr[:, :, 3] = mask

    img  = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    _draw_outline(draw, cx, cy, text, font, outline_w, (255, 255, 255, 255))
    img.alpha_composite(Image.fromarray(fill_arr, "RGBA"))
    return img.rotate(angle, expand=True, resample=Image.BICUBIC)


def render_layer(text, font_size, outline_w, angle, mode):
    if mode == "normal":
        return render_solid(text, font_size, outline_w, angle,
                            (0, 0, 0, 255), (255, 255, 255, 255))
    if mode == "inv":
        return render_solid(text, font_size, outline_w, angle,
                            (255, 255, 255, 255), (0, 0, 0, 255))
    return render_gradient(text, font_size, outline_w, angle, mode)


def blur_rgba(img, radius=6):
    r, g, b, a = img.split()
    bf = lambda c: c.filter(ImageFilter.GaussianBlur(radius))
    return Image.merge("RGBA", (bf(r), bf(g), bf(b), bf(a)))


def compose(layers, canvas_w=CW, canvas_h=CH):
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    for layer, cx, cy in layers:
        x, y = cx - layer.width // 2, cy - layer.height // 2
        sx, sy = max(0, -x), max(0, -y)
        dx, dy = max(0,  x), max(0,  y)
        w = min(layer.width - sx, canvas_w - dx)
        h = min(layer.height - sy, canvas_h - dy)
        if w > 0 and h > 0:
            canvas.alpha_composite(layer.crop((sx, sy, sx+w, sy+h)), (dx, dy))
    return canvas


def make_single(word, fsize, outline, angle, mode):
    return compose([(render_layer(word, fsize, outline, angle, mode),
                     CW // 2, CH // 2)])


def make_stagger(chars, fsize, outline, angle, mode, sx=0.72, sy=0.28):
    n = len(chars)
    layers = []
    for j, ch in enumerate(chars):
        jit = random.uniform(-8, 8)
        cx  = int(CW // 2 + (j - (n-1)/2) * fsize * sx + jit)
        cy  = int(CH // 2 + (j - (n-1)/2) * fsize * sy + jit)
        layers.append((render_layer(ch, fsize, outline,
                                    angle + random.uniform(-3, 3), mode),
                       cx, cy))
    return compose(layers)


def make_pair(w1, w2, fsize, outline, angle, mode):
    l1 = render_layer(w1, fsize, outline, angle, mode)
    l2 = render_layer(w2, fsize, outline, angle + random.uniform(-5, 5), mode)
    return compose([(l1, CW//2 - fsize//2, CH//2 - fsize//3),
                    (l2, CW//2 + fsize//2, CH//2 + fsize//3)])


def save(img, name):
    p = OUT / f"{name}.png"
    img.save(p)
    print(f"  -> {p.name}")


def all_variants(img_fn, name):
    for mode in ("normal", "inv", "grad", "color_black", "color_white"):
        img    = img_fn(mode)
        suffix = "" if mode == "normal" else f"_{mode}"
        save(img, name + suffix)
        if mode in ("normal", "inv"):
            save(blur_rgba(img), name + suffix + "_blur")


# ── parameter generation (fixed seed → reproducible) ─────────────────────────

jobs = []

for i, word in enumerate(SFX["simple"]):
    angle = random.uniform(-28, 28);  fsize = random.randint(160, 210)
    outline = max(6, fsize // 18)
    _w, _a, _f, _o = word, angle, fsize, outline
    jobs.append((f"sfx_{i+1:02d}_{word}",
                 lambda m, w=_w, a=_a, f=_f, o=_o: make_single(w, f, o, a, m)))

for i, word in enumerate(SFX["double"]):
    angle = random.uniform(-32, 32);  fsize = random.randint(130, 170)
    outline = max(5, fsize // 16)
    _w, _a, _f, _o = list(word), angle, fsize, outline
    jobs.append((f"sfx_{i+7:02d}_{word}",
                 lambda m, w=_w, a=_a, f=_f, o=_o: make_stagger(w, f, o, a, m)))

for i, word in enumerate(SFX["long"]):
    angle = random.choice([-35, -28, 28, 35]);  fsize = random.randint(140, 185)
    outline = max(7, fsize // 14)
    _w, _a, _f, _o = list(word), angle, fsize, outline
    jobs.append((f"sfx_{i+13:02d}_{word}",
                 lambda m, w=_w, a=_a, f=_f, o=_o:
                     make_stagger(w, f, o, a, m, sx=0.68, sy=0.32)))

for i, (w1, w2) in enumerate([("번쩍", "쾅"), ("파직", "쿵")]):
    angle = random.uniform(-30, -20)
    _w1, _w2, _a = w1, w2, angle
    jobs.append((f"sfx_{i+17:02d}_{w1}_{w2}",
                 lambda m, w1=_w1, w2=_w2, a=_a:
                     make_pair(w1, w2, 155, 10, a, m)))

idx = 1
for word in EXPR["exclaim"]:
    angle = random.uniform(-38, 38);  fsize = random.randint(200, 250)
    outline = max(8, fsize // 16)
    _w, _a, _f, _o = word, angle, fsize, outline
    jobs.append((f"expr_{idx:02d}_{word}",
                 lambda m, w=_w, a=_a, f=_f, o=_o: make_single(w, f, o, a, m)))
    idx += 1

for word in EXPR["emotion"]:
    angle = random.uniform(-30, 30);  fsize = random.randint(130, 165)
    outline = max(6, fsize // 15)
    _w, _a, _f, _o = list(word), angle, fsize, outline
    jobs.append((f"expr_{idx:02d}_{word}",
                 lambda m, w=_w, a=_a, f=_f, o=_o: make_stagger(w, f, o, a, m)))
    idx += 1

for word in EXPR["rude"]:
    angle = random.choice([-40, -35, 35, 40]);  fsize = random.randint(140, 180)
    outline = max(7, fsize // 14)
    _w, _a, _f, _o = list(word), angle, fsize, outline
    jobs.append((f"expr_{idx:02d}_{word}",
                 lambda m, w=_w, a=_a, f=_f, o=_o: make_stagger(w, f, o, a, m)))
    idx += 1

for word in EXPR["scream"]:
    angle = random.choice([-42, -38, 38, 42]);  fsize = random.randint(150, 200)
    outline = max(7, fsize // 15)
    _w, _a, _f, _o = list(word), angle, fsize, outline
    jobs.append((f"expr_{idx:02d}_{word}",
                 lambda m, w=_w, a=_a, f=_f, o=_o:
                     make_stagger(w, f, o, a, m, sx=0.30, sy=0.80)))
    idx += 1

# ── render ────────────────────────────────────────────────────────────────────
print(f"Generating {len(jobs)} words × 7 variants = {len(jobs)*7} images ...\n")
for name, img_fn in jobs:
    all_variants(img_fn, name)

print(f"\nDone. {len(list(OUT.glob('*.png')))} images in {OUT}/")
