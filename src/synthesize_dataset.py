"""
Synthesize dataset variants from processed Pepper&Carrot pages.

Nine variants are produced per page:

  transparent/              — clean artwork, transparent borders              (target)
  white/                    — raw merged image, white borders intact          (input)
  black/                    — artwork on solid black background               (input)
  jpeg/                     — white borders + JPEG compression                (input)
  framed/                   — white bg + 1px black panel outline              (input)
  framed_jpeg/              — white bg + 1px frame + JPEG compression;
                              hardest case: borders, frame, and noise         (input)
  transparent_framed/       — transparent + 1px black panel outline           (input)
  transparent_jpeg/         — transparent + JPEG artifacts on RGB, alpha kept (input)
  transparent_framed_jpeg/  — transparent + 1px frame + JPEG compression;
                              frame loses true black as in real manhwa scans  (input)
"""

import argparse
import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from tqdm import tqdm

from process_kra import (
    TMP_DIR,
    OUTPUT_DIR,
    REPORT_DIR,
    get_krita_info,
    choose_border_layer,
    build_raster_mask,
    build_svg_mask,
    build_group_mask,
    load_merged_image,
    find_svg,
)

SYNTH_DIR = Path("data/synthesized")
JPEG_QUALITY = 15  # aggressive — artifacts visible under careful inspection


def load_kra_data(kra_path: Path):
    """Return (mask_L, merged_RGBA) for the given KRA file, or (None, None) on failure."""
    with zipfile.ZipFile(kra_path) as z:
        width, height, layers, xml_root = get_krita_info(z)
        border_layer = choose_border_layer(layers)
        if border_layer is None:
            return None, None

        nodetype = border_layer.get("nodetype", "")
        filename = border_layer.get("filename", "")

        if nodetype == "shapelayer":
            svg = find_svg(z, filename)
            if not svg:
                return None, None
            mask = build_svg_mask(svg, width, height)
        elif nodetype == "paintlayer":
            mask = build_raster_mask(z, border_layer, width, height)
        elif nodetype == "grouplayer":
            mask = build_group_mask(z, xml_root, filename, width, height)
        else:
            return None, None

        merged = load_merged_image(z).convert("RGBA")

    return mask, merged


def panel_edge(transparent: Image.Image) -> np.ndarray:
    """
    Return a boolean mask of the 1px ring of content pixels at the panel boundary
    (outermost artwork pixels adjacent to the transparent border).
    Drawing black here guarantees no gap between artwork and frame.
    """
    alpha = np.array(transparent.getchannel("A"))
    border = Image.fromarray((alpha == 0).astype(np.uint8) * 255)
    dilated = np.array(border.filter(ImageFilter.MaxFilter(3))) > 0
    return dilated & (alpha > 0)


def make_black_variant(transparent: Image.Image) -> Image.Image:
    """Composite artwork onto a solid black background."""
    bg = Image.new("RGBA", transparent.size, (0, 0, 0, 255))
    bg.alpha_composite(transparent)
    return bg


def make_jpeg_variant(merged: Image.Image) -> Image.Image:
    """White-border image with heavy JPEG compression to introduce visible artifacts."""
    buf = io.BytesIO()
    merged.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
    buf.seek(0)
    return Image.open(buf).copy().convert("RGBA")


def make_framed_variant(transparent: Image.Image) -> Image.Image:
    """Artwork on white background with a 1px black outline at each panel boundary."""
    bg = Image.new("RGBA", transparent.size, (255, 255, 255, 255))
    bg.alpha_composite(transparent)
    arr = np.array(bg)
    arr[panel_edge(transparent)] = [0, 0, 0, 255]
    return Image.fromarray(arr)


def make_transparent_framed_variant(transparent: Image.Image) -> Image.Image:
    """Transparent PNG with a 1px black outline at each panel boundary, no white fill."""
    arr = np.array(transparent.copy())
    arr[panel_edge(transparent)] = [0, 0, 0, 255]
    return Image.fromarray(arr)


def make_transparent_jpeg_variant(transparent: Image.Image) -> Image.Image:
    """Transparent PNG with JPEG compression artifacts on the RGB channels, alpha preserved."""
    alpha = transparent.getchannel("A")
    buf = io.BytesIO()
    transparent.convert("RGB").save(buf, format="JPEG", quality=JPEG_QUALITY)
    buf.seek(0)
    compressed_rgb = Image.open(buf).copy()
    compressed_rgb.putalpha(alpha)
    return compressed_rgb


def make_framed_jpeg_variant(transparent: Image.Image, merged: Image.Image) -> Image.Image:
    """White-border image with 1px black frame drawn first, then JPEG compressed."""
    arr = np.array(merged.convert("RGB"), dtype=np.uint8)
    arr[panel_edge(transparent)] = [0, 0, 0]
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=JPEG_QUALITY)
    buf.seek(0)
    return Image.open(buf).copy().convert("RGBA")


def make_transparent_framed_jpeg_variant(transparent: Image.Image) -> Image.Image:
    """
    Transparent + 1px black frame + JPEG compression on RGB.
    The frame loses true black due to JPEG artifacts, matching real manhwa scan behaviour.
    """
    alpha = transparent.getchannel("A")
    # Draw the frame on the RGB, then compress — frame pixels bleed into near-black
    arr = np.array(transparent.convert("RGB"), dtype=np.uint8)
    arr[panel_edge(transparent)] = [0, 0, 0]
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="JPEG", quality=JPEG_QUALITY)
    buf.seek(0)
    compressed_rgb = Image.open(buf).copy()
    compressed_rgb.putalpha(alpha)
    return compressed_rgb


def process_page(kra_path: Path, processed_png: Path, synth_ep_dir: Path):
    stem = processed_png.stem
    filename = f"{stem}.png"

    transparent = Image.open(processed_png).convert("RGBA")

    for d in ("transparent", "white", "black", "jpeg", "framed", "framed_jpeg",
              "transparent_framed", "transparent_jpeg", "transparent_framed_jpeg"):
        (synth_ep_dir / d).mkdir(parents=True, exist_ok=True)

    transparent.save(synth_ep_dir / "transparent" / filename, "PNG")
    make_black_variant(transparent).save(synth_ep_dir / "black" / filename, "PNG")
    make_framed_variant(transparent).save(synth_ep_dir / "framed" / filename, "PNG")
    make_transparent_framed_variant(transparent).save(synth_ep_dir / "transparent_framed" / filename, "PNG")
    make_transparent_jpeg_variant(transparent).save(synth_ep_dir / "transparent_jpeg" / filename, "PNG")
    make_transparent_framed_jpeg_variant(transparent).save(synth_ep_dir / "transparent_framed_jpeg" / filename, "PNG")

    mask, merged = load_kra_data(kra_path)
    if mask is None:
        print(f"  {stem}: mask unavailable — white/jpeg/framed_jpeg variants skipped")
        return

    merged.save(synth_ep_dir / "white" / filename, "PNG")
    make_jpeg_variant(merged).save(synth_ep_dir / "jpeg" / filename, "PNG")
    make_framed_jpeg_variant(transparent, merged).save(synth_ep_dir / "framed_jpeg" / filename, "PNG")

    pass


def main():
    parser = argparse.ArgumentParser(
        description="Generate dataset variants from processed Pepper&Carrot pages."
    )
    parser.add_argument(
        "episodes",
        nargs="*",
        help="Episode prefix(es) to process (default: ep01). Use 'all' for every episode.",
    )
    args = parser.parse_args()
    targets = args.episodes or ["ep01"]

    report_path = REPORT_DIR / "processing_report.json"
    if not report_path.exists():
        print("No processing report found — run process_kra.py first.")
        return
    with open(report_path) as f:
        report = json.load(f)
    saved_names = {r["kra_file"] for r in report if r["status"] == "saved"}

    if targets == ["all"]:
        ep_dirs = sorted(d for d in OUTPUT_DIR.iterdir() if d.is_dir())
    else:
        ep_dirs = []
        for t in targets:
            matched = sorted(d for d in OUTPUT_DIR.iterdir() if d.is_dir() and d.name.startswith(t))
            if not matched:
                print(f"Warning: no episode directory matching '{t}'")
            ep_dirs.extend(matched)

    if not ep_dirs:
        print(f"No episode directories found in {OUTPUT_DIR}")
        return

    all_pages = []
    for ep_dir in ep_dirs:
        for png in sorted(ep_dir.glob("*.png")):
            kra_name = png.stem + ".kra"
            if kra_name not in saved_names:
                continue
            kra_files = list(Path(TMP_DIR).rglob(kra_name))
            if kra_files:
                all_pages.append((ep_dir, kra_files[0], png))

    with tqdm(total=len(all_pages), unit="page") as bar:
        for ep_dir, kra_path, png in all_pages:
            synth_ep_dir = SYNTH_DIR / ep_dir.name
            bar.set_description(f"{ep_dir.name}/{png.name}")
            process_page(kra_path, png, synth_ep_dir)
            bar.update(1)


if __name__ == "__main__":
    main()
