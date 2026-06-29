"""
Generate speech bubble / text box overlay images.
Output: data/overlays/bubbles/  (RGBA PNG, transparent background)

Shapes:
  burst_bubble.png          — action burst with rays
  oval_tail_{dir}.png       — oval speech bubble, 5 tail directions
  thought_bubble.png        — cloud chain / thought bubble
  sfx_blob.png              — dark amoeba blob with SFX text
  rect_box.png              — double-bordered rectangle (normal + inverted)
  rect_box_inv.png
  cloud_bubble.png          — smooth cloud outline with curved tail

Run from project root: python3 src/make_bubbles.py
"""

import math, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

random.seed(42)

OUT = Path("data/overlays/bubbles")
OUT.mkdir(parents=True, exist_ok=True)

SW, SH = 520, 380

LOREM       = "Lorem ipsum\ndolor sit amet\nconsectetur"
LOREM_SHORT = "Lorem,\ndolor sit amet."
LOREM_SFX   = "LO-O-O-REM!"
LOREM_BOX   = "Lorem ipsum\ndolor sit amet?"

# ── font loader ───────────────────────────────────────────────────────────────

def load_font(size, bold=True):
    suffix = "-Bold" if bold else "-Regular"
    for p in [
        f"/usr/share/fonts/noto/NotoSans{suffix}.ttf",
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{suffix}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{suffix}.ttf",
    ]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ── shared drawing helpers ────────────────────────────────────────────────────

def draw_cloud_oval(draw, cx, cy, rw, rh, n_bumps=11, bump_pct=0.16,
                    fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), lw=3):
    """Smooth outward cloud bumps via half-sine normal-offset along the ellipse."""
    n_pts = n_bumps * 32
    pts   = []
    for j in range(n_pts):
        t     = j / n_pts
        angle = 2 * math.pi * t
        ex    = cx + rw * math.cos(angle)
        ey    = cy + rh * math.sin(angle)
        nx, ny = math.cos(angle) / rw, math.sin(angle) / rh
        n_len  = math.sqrt(nx * nx + ny * ny)
        nx, ny = nx / n_len, ny / n_len
        bump = bump_pct * min(rw, rh) * max(0.0, math.sin(math.pi * n_bumps * t))
        pts.append((ex + nx * bump, ey + ny * bump))
    draw.polygon(pts, fill=fill, outline=outline, width=lw)


def rgba(r, g=None, b=None, a=255):
    if g is None:
        return (r, r, r, a)
    return (r, g, b, a)


def save(img, name):
    p = OUT / f"{name}.png"
    img.save(p)
    print(f"  -> {p.name}")


# ═════════════════════════════════════════════════════════════════════════════
# BUBBLE GENERATORS  (all output RGBA, transparent background)
# ═════════════════════════════════════════════════════════════════════════════

def make_burst():
    BW, BH = 640, 460
    img  = Image.new("RGBA", (BW, BH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = BW // 2, BH // 2
    rw, rh = 155, 95

    def draw_ray(angle, length, base_w):
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        px, py = -sin_a, cos_a
        sx = cx + rw * cos_a;  sy = cy + rh * sin_a
        ex = sx + length * cos_a;  ey = sy + length * sin_a
        hw = base_w / 2
        draw.polygon([(sx + px*hw, sy + py*hw),
                      (sx - px*hw, sy - py*hw), (ex, ey)],
                     fill=(0, 0, 0, 255))

    for i in range(300):
        angle  = 2 * math.pi * i / 300
        length = random.uniform(78, 130)
        base_w = 5.5 if i % 5 == 0 else (2.5 if i % 2 == 0 else 1.5)
        draw_ray(angle, length, base_w)

    draw.ellipse([cx - rw, cy - rh, cx + rw, cy + rh],
                 fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=5)
    draw.text((cx, cy), LOREM, font=load_font(40), fill=(10, 10, 10, 255),
              anchor="mm", align="center")
    save(img, "burst_bubble")


def make_oval_tail(tail_angle, name):
    img  = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SW // 2, SH // 2
    rw, rh = 195, 110
    cos_a, sin_a = math.cos(tail_angle), math.sin(tail_angle)
    ox, oy   = cx + rw * cos_a, cy + rh * sin_a
    tip_x    = ox + 52 * cos_a;  tip_y = oy + 52 * sin_a
    px, py   = -sin_a, cos_a;    hw = 13
    b1 = (ox + px * hw, oy + py * hw)
    b2 = (ox - px * hw, oy - py * hw)
    draw.polygon([b1, b2, (tip_x, tip_y)], fill=(255, 255, 255, 255))
    draw.line([b1, (tip_x, tip_y)], fill=(0, 0, 0, 255), width=3)
    draw.line([b2, (tip_x, tip_y)], fill=(0, 0, 0, 255), width=3)
    draw.ellipse([cx - rw, cy - rh, cx + rw, cy + rh],
                 fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=3)
    draw.text((cx, cy), LOREM_SHORT, font=load_font(50), fill=(10, 10, 10, 255),
              anchor="mm", align="center")
    save(img, name)


def make_thought_bubble():
    img  = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SW // 2, SH // 2 - 35
    rw, rh = 205, 110
    ty_start = cy + rh + 6
    for i, r in enumerate([15, 10, 7, 4]):
        bx = cx + random.uniform(-5, 5)
        by = ty_start + i * 21 + r
        draw.ellipse([bx - r, by - r, bx + r, by + r],
                     fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=2)
    draw.ellipse([cx - rw, cy - rh, cx + rw, cy + rh],
                 fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=3)
    draw.text((cx, cy), LOREM_SHORT, font=load_font(46), fill=(10, 10, 10, 255),
              anchor="mm", align="center")
    save(img, "thought_bubble")


def make_sfx_blob():
    img  = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SW // 2, SH // 2
    pts = []
    for i in range(36):
        angle = 2 * math.pi * i / 36
        r = random.uniform(165, 200) if i % 2 == 0 else random.uniform(110, 138)
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    draw.polygon(pts, fill=(18, 18, 28, 255))
    font    = load_font(58)
    txt_img = Image.new("RGBA", (480, 130), (0, 0, 0, 0))
    td      = ImageDraw.Draw(txt_img)
    tc      = (txt_img.width // 2, txt_img.height // 2)
    for dx in [-4, -2, 2, 4]:
        for dy in [-4, -2, 2, 4]:
            td.text((tc[0]+dx, tc[1]+dy), LOREM_SFX,
                    font=font, fill=(10, 0, 0, 255), anchor="mm")
    td.text(tc, LOREM_SFX, font=font, fill=(215, 25, 25, 255), anchor="mm")
    txt_rot = txt_img.rotate(-18, expand=True, resample=Image.BICUBIC)
    img.alpha_composite(txt_rot, (cx - txt_rot.width // 2, cy - txt_rot.height // 2))
    save(img, "sfx_blob")


def make_rect_box(bg=(255,255,255,255), fg=(10,10,10,255),
                  border=(0,0,0,255), name="rect_box"):
    img  = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    o, i = 28, 46
    draw.rectangle([o, o, SW-o, SH-o], fill=bg, outline=border, width=5)
    draw.rectangle([i, i, SW-i, SH-i], outline=border, width=2)
    draw.text((SW//2, SH//2), LOREM_BOX, font=load_font(48), fill=fg,
              anchor="mm", align="center")
    save(img, name)


def make_cloud_bubble():
    img  = Image.new("RGBA", (SW, SH), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = SW // 2, SH // 2 - 20
    rw, rh = 208, 115
    draw_cloud_oval(draw, cx, cy, rw, rh, n_bumps=11, bump_pct=0.13,
                    fill=(255,255,255,255), outline=(0,0,0,255), lw=3)
    tail_cx = cx + int(rw * 0.45)
    tail_cy = cy + rh + 4
    tail_pts = [(tail_cx, tail_cy), (tail_cx+18, tail_cy+22),
                (tail_cx+38, tail_cy+36), (tail_cx+58, tail_cy+32)]
    draw.line(tail_pts, fill=(255,255,255,255), width=7)
    draw.line(tail_pts, fill=(0,0,0,255), width=3)
    hx, hy = tail_pts[-1]
    draw.ellipse([hx-5, hy-5, hx+5, hy+5],
                 fill=(255,255,255,255), outline=(0,0,0,255), width=2)
    draw.text((cx, cy), LOREM_SHORT, font=load_font(46), fill=(10,10,10,255),
              anchor="mm", align="center")
    save(img, "cloud_bubble")


# ── run all ───────────────────────────────────────────────────────────────────
print("Generating bubble overlay images ...\n")
make_burst()
make_oval_tail(-math.pi / 2,                "oval_tail_up")
make_oval_tail( math.pi / 2,                "oval_tail_down")
make_oval_tail( 0,                          "oval_tail_right")
make_oval_tail( math.pi,                    "oval_tail_left")
make_oval_tail( math.pi / 2 + math.pi / 4, "oval_tail_diag")
make_thought_bubble()
make_sfx_blob()
make_rect_box()
make_rect_box(bg=(10,10,10,255), fg=(245,245,245,255), border=(220,220,220,255),
              name="rect_box_inv")
make_cloud_bubble()

print(f"\nDone. {len(list(OUT.glob('*.png')))} images in {OUT}/")
