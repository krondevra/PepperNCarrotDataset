"""
Apply SFX and bubble overlays to synthesized panel frames.

Creates four new input variants per episode:
  sfx_overlay/               — Korean SFX on white panel (RGB)
  sfx_overlay_transparent/   — same overlays on transparent artwork (RGBA)
  bubble_overlay/            — speech bubbles/boxes on white panel (RGB)
  bubble_overlay_transparent/— same overlays on transparent artwork (RGBA)

Overlay positions are identical between white and transparent pairs
(same seed, same plan) so they form clean training pairs.
Target for all four remains transparent/ (clean artwork, no overlays).

Placement strategy (per detected panel):
  ~75% edge   — overlay straddles the panel's top or bottom frame line
  ~25% inner  — overlay sits in a corner/side background region of the panel

Panel bounds are detected from the transparent/ alpha channel.
Seed is deterministic per panel: hash(episode + filename + variant).

Usage:
  python3 src/synthesize_overlays.py ep01      # one episode (test)
  python3 src/synthesize_overlays.py all       # all episodes
"""

import sys, random
import numpy as np
from pathlib import Path
from PIL import Image

SYNTH   = Path("data/synthesized")
SFX_DIR = Path("data/overlays/sfx")
BUB_DIR = Path("data/overlays/bubbles")

# Probability that a given panel receives an overlay
SFX_PROB = 0.80   # most panels get an SFX
BUB_PROB = 0.55   # roughly half get a bubble
EDGE_PROB = 0.75  # of those, most are edge-placed

# ── panel detection ───────────────────────────────────────────────────────────

def detect_panels(transparent_path):
    """
    Return list of (y1, y2) content-row bounds for each panel,
    detected via the alpha channel of the transparent variant.
    """
    img   = Image.open(transparent_path).convert("RGBA")
    alpha = np.array(img.getchannel("A"))
    W     = alpha.shape[1]
    # Use central columns to avoid false hits from thin border artifacts
    center = alpha[:, W // 8 : 7 * W // 8]
    has_content = center.max(axis=1) > 0

    panels, in_panel, start = [], False, 0
    for i, v in enumerate(has_content):
        if v and not in_panel:
            start = i;  in_panel = True
        elif not v and in_panel:
            panels.append((start, i));  in_panel = False
    if in_panel:
        panels.append((start, len(has_content)))
    return panels, img.width, img.height


# ── placement helpers ─────────────────────────────────────────────────────────

def _place_edge(pw, panel, ow, oh, rng):
    """
    Place overlay straddling the top or bottom frame line of the panel.
    Center of overlay is at the panel border ± small jitter.
    """
    y1, y2 = panel
    border_y = rng.choice([y1, y2])
    jitter   = rng.randint(-oh // 6, oh // 6)
    cy = border_y + jitter
    # Allow partial clip at left/right edges too
    cx = rng.randint(ow // 4, pw - ow // 4)
    return cx - ow // 2, cy - oh // 2


def _place_background(pw, panel, ow, oh, rng):
    """
    Place overlay in a corner/side of the panel (avoids the central subject).
    """
    y1, y2 = panel
    ph = y2 - y1
    margin_y = max(oh // 4, int(ph * 0.08))

    qx = rng.choice([0, 1])
    qy = rng.choice([0, 1])

    if qx == 0:
        lo_x, hi_x = ow // 4, max(ow // 4 + 1, pw // 3)
    else:
        lo_x, hi_x = min(2 * pw // 3, pw - ow // 4 - 1), pw - ow // 4
    cx = rng.randint(min(lo_x, hi_x - 1), max(lo_x + 1, hi_x))

    if qy == 0:
        lo, hi = y1 + margin_y, y1 + ph // 3
    else:
        lo, hi = y1 + 2 * ph // 3, y2 - margin_y
    cy = rng.randint(min(lo, hi - 1), max(lo + 1, hi))

    return cx - ow // 2, cy - oh // 2


def _paste_overlay(result, ov_path, x, y, new_w, new_h):
    """Load, resize and alpha-composite one overlay onto result."""
    ov = Image.open(ov_path).convert("RGBA")
    ov = ov.resize((new_w, new_h), Image.LANCZOS)
    pw, ph = result.size
    sx = max(0, -x);  sy = max(0, -y)
    dx = max(0,  x);  dy = max(0,  y)
    w  = min(new_w - sx, pw - dx)
    h  = min(new_h - sy, ph - dy)
    if w > 0 and h > 0:
        crop = ov.crop((sx, sy, sx + w, sy + h))
        tmp  = Image.new("RGBA", result.size, (0, 0, 0, 0))
        tmp.paste(crop, (dx, dy))
        result = Image.alpha_composite(result, tmp)
    return result


def _plan_overlays(overlay_paths, panels, pw, rng, overlay_prob, edge_prob):
    """
    Decide placement for each panel and return a list of
    (ov_path, x, y, new_w, new_h) — one entry per panel that gets an overlay.
    Separating planning from rendering lets the same plan be applied to both
    the white and transparent base images with identical positions.
    """
    plan = []
    for panel in panels:
        if rng.random() > overlay_prob:
            continue
        ov_path = rng.choice(overlay_paths)
        panel_h = panel[1] - panel[0]
        scale   = rng.uniform(0.30, 0.68)
        new_h   = max(60, int(panel_h * scale))
        probe   = Image.open(ov_path)
        new_w   = max(50, int(probe.width * new_h / probe.height))

        if rng.random() < edge_prob:
            x, y = _place_edge(pw, panel, new_w, new_h, rng)
        else:
            x, y = _place_background(pw, panel, new_w, new_h, rng)

        plan.append((ov_path, x, y, new_w, new_h))
    return plan


def apply_plan(base_rgba, plan):
    """Composite a pre-computed overlay plan onto base_rgba."""
    result = base_rgba.copy()
    for ov_path, x, y, new_w, new_h in plan:
        result = _paste_overlay(result, ov_path, x, y, new_w, new_h)
    return result


# ── per-episode processing ────────────────────────────────────────────────────

def _seed(ep_name, filename, tag):
    return hash(ep_name + filename + tag) & 0xFFFFFFFF


def flatten_white(img):
    bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
    bg.alpha_composite(img)
    return bg.convert("RGB")


def process_episode(ep_dir, sfx_files, bub_files):
    src_dir   = ep_dir / "white"
    trans_dir = ep_dir / "transparent"
    if not src_dir.exists() or not trans_dir.exists():
        print(f"  skip {ep_dir.name}: missing white/ or transparent/")
        return

    pages = sorted(src_dir.glob("*.png"))
    if not pages:
        print(f"  skip {ep_dir.name}: no pages")
        return

    print(f"\n{ep_dir.name}  ({len(pages)} pages)")
    for variant in ("sfx_overlay", "sfx_overlay_transparent",
                    "bubble_overlay", "bubble_overlay_transparent"):
        (ep_dir / variant).mkdir(exist_ok=True)

    for page_path in pages:
        fname  = page_path.name
        t_path = trans_dir / fname
        if not t_path.exists():
            print(f"    skip {fname}: no transparent variant")
            continue

        panels, pw, ph = detect_panels(t_path)
        if not panels:
            print(f"    skip {fname}: no panels detected")
            continue

        panel_white = Image.open(page_path).convert("RGBA")
        panel_trans = Image.open(t_path).convert("RGBA")

        if sfx_files:
            plan = _plan_overlays(sfx_files, panels, pw,
                                  random.Random(_seed(ep_dir.name, fname, "sfx")),
                                  SFX_PROB, EDGE_PROB)
            flatten_white(apply_plan(panel_white, plan)).save(
                ep_dir / "sfx_overlay" / fname)
            apply_plan(panel_trans, plan).save(
                ep_dir / "sfx_overlay_transparent" / fname)       # RGBA PNG

        if bub_files:
            plan = _plan_overlays(bub_files, panels, pw,
                                  random.Random(_seed(ep_dir.name, fname, "bub")),
                                  BUB_PROB, EDGE_PROB)
            flatten_white(apply_plan(panel_white, plan)).save(
                ep_dir / "bubble_overlay" / fname)
            apply_plan(panel_trans, plan).save(
                ep_dir / "bubble_overlay_transparent" / fname)     # RGBA PNG

        print(f"    {fname}  ({len(panels)} panels)")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"

    sfx_files = sorted(SFX_DIR.glob("*.png"))
    bub_files = sorted(BUB_DIR.glob("*.png"))

    if not sfx_files:
        print(f"WARNING: no SFX overlays in {SFX_DIR}. Run: python3 src/make_sfx.py")
    if not bub_files:
        print(f"WARNING: no bubble overlays in {BUB_DIR}. Run: python3 src/make_bubbles.py")
    if not sfx_files and not bub_files:
        sys.exit(1)

    print(f"Loaded {len(sfx_files)} SFX + {len(bub_files)} bubble overlays.")

    if arg == "all":
        episodes = sorted(d for d in SYNTH.iterdir() if d.is_dir())
    else:
        episodes = sorted(d for d in SYNTH.iterdir()
                          if d.is_dir() and arg in d.name)

    if not episodes:
        print(f"No episodes matching '{arg}' in {SYNTH}")
        sys.exit(1)

    print(f"Processing {len(episodes)} episode(s) ...")
    for ep in episodes:
        process_episode(ep, sfx_files, bub_files)

    print("\nDone.")


if __name__ == "__main__":
    main()
