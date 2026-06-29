import csv
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import cairosvg
import numpy as np
from PIL import Image


TMP_DIR     = Path("data/preprocessing/kra")
RENDERS_DIR = Path("data/preprocessing/renders")
REPORT_DIR = Path("reports")

ONLY_PAGE_KRA = True

# Files with known quality issues that must not appear in the dataset.
# The processed PNG is deleted if it already exists on disk.
BLACKLISTED = {
    "E03P02.kra": "unclipped artwork bleed produces artifact bands in the border mask",
}

# Raster border layer: pixel counts as border if alpha > this and RGB >= WHITE_THRESHOLD
RASTER_ALPHA_THRESHOLD = 8
RASTER_WHITE_THRESHOLD = 200

# Sanity check: mask must cover between MIN and MAX fraction of the canvas
MIN_MASK_COVERAGE = 0.005
MAX_MASK_COVERAGE = 0.80


# ---------------------------------------------------------------------------
# KRA layer helpers
# ---------------------------------------------------------------------------

def is_page_kra(path: Path) -> bool:
    return re.search(r"p\d+\.kra$", path.name.lower()) is not None


def clean_layer_name(name: str) -> str:
    return name.lower().strip().replace("_", "-").replace(" ", "-")


def is_border_layer(layer: dict) -> bool:
    name = clean_layer_name(layer.get("name", ""))
    if name in ("frame", "panel-frame", "panel"):
        return True
    if "frame" in name and "keyframe" not in name:
        return True
    return False


def get_krita_info(zip_file):
    maindoc = zip_file.read("maindoc.xml").decode("utf-8", errors="ignore")
    root = ET.fromstring(maindoc)
    ns = {"k": "http://www.calligra.org/DTD/krita"}

    image = root.find(".//k:IMAGE", ns)
    if image is None:
        raise RuntimeError("IMAGE element not found in maindoc.xml")

    width = int(image.attrib["width"])
    height = int(image.attrib["height"])
    layers = [dict(l.attrib) for l in root.findall(".//k:layer", ns)]
    return width, height, layers, root


def choose_border_layer(layers: list):
    candidates = [l for l in layers if is_border_layer(l)]
    if not candidates:
        return None

    def score(layer):
        name = clean_layer_name(layer.get("name", ""))
        nodetype = layer.get("nodetype", "")
        s = 0
        if name == "frame":
            s += 100
        elif name == "panel-frame":
            s += 95
        elif "panel-frame" in name:
            s += 80
        elif "frame" in name:
            s += 60
        if nodetype == "shapelayer":
            s += 10
        elif nodetype == "paintlayer":
            s += 8
        if layer.get("visible", "1") == "1":
            s += 5
        return s

    candidates.sort(key=score, reverse=True)
    return candidates[0]


# ---------------------------------------------------------------------------
# SVG border mask (shapelayer)
# ---------------------------------------------------------------------------

def find_svg(zip_file, filename: str):
    for name in zip_file.namelist():
        if name.endswith(f"/layers/{filename}.shapelayer/content.svg"):
            return zip_file.read(name).decode("utf-8", errors="ignore")
        if name.endswith(f"{filename}.shapelayer/content.svg"):
            return zip_file.read(name).decode("utf-8", errors="ignore")
    return None


def build_svg_mask(svg_text: str, canvas_w: int, canvas_h: int) -> Image.Image:
    png_data = cairosvg.svg2png(
        bytestring=svg_text.encode("utf-8"),
        output_width=canvas_w,
        output_height=canvas_h,
    )
    rendered = Image.open(io.BytesIO(png_data)).convert("RGBA")
    # SVG shapes are white-filled on a transparent background.
    # The alpha channel directly gives us the border mask.
    return rendered.getchannel("A")


# ---------------------------------------------------------------------------
# Raster border mask (paintlayer)
# ---------------------------------------------------------------------------

def find_layer_file(zip_file, filename: str):
    for name in zip_file.namelist():
        if name.endswith(f"/{filename}") or name == filename:
            return name
    return None


def lzf_decompress(data: bytes) -> bytes:
    ip = 0
    output = bytearray()
    data_len = len(data)

    while ip < data_len:
        ctrl = data[ip]
        ip += 1

        if ctrl < 32:
            length = ctrl + 1
            output.extend(data[ip:ip + length])
            ip += length
        else:
            length = ctrl >> 5
            ref = len(output) - ((ctrl & 0x1F) << 8) - 1
            if length == 7:
                length += data[ip]
                ip += 1
            ref -= data[ip]
            ip += 1
            for _ in range(length + 2):
                if ref < 0 or ref >= len(output):
                    raise RuntimeError("bad LZF back-reference")
                output.append(output[ref])
                ref += 1

    return bytes(output)


def parse_krita_tile_header(data: bytes):
    pos = 0
    header = {}

    while True:
        line_end = data.index(b"\n", pos)
        line = data[pos:line_end].decode("utf-8", errors="ignore")
        pos = line_end + 1

        if line.startswith("DATA "):
            tile_count = int(line.split()[1])
            break

        if " " in line:
            key, value = line.split(" ", 1)
            header[key] = value

    return (
        pos,
        tile_count,
        int(header["TILEWIDTH"]),
        int(header["TILEHEIGHT"]),
        int(header["PIXELSIZE"]),
    )


def decode_krita_paint_layer(zip_file, filename: str, canvas_w: int, canvas_h: int) -> Image.Image:
    path = find_layer_file(zip_file, filename)
    if not path:
        raise RuntimeError(f"layer tile data not found: {filename!r}")

    data = zip_file.read(path)
    pos, tile_count, tile_w, tile_h, pixel_size = parse_krita_tile_header(data)

    if pixel_size < 4:
        raise RuntimeError(f"unsupported pixel size {pixel_size}")

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    plane_size = tile_w * tile_h
    expected = plane_size * pixel_size

    for _ in range(tile_count):
        line_end = data.index(b"\n", pos)
        line = data[pos:line_end].decode("utf-8", errors="ignore")
        pos = line_end + 1

        parts = line.split(",")
        if len(parts) != 4:
            raise RuntimeError(f"bad tile descriptor: {line!r}")

        tile_x = int(parts[0])
        tile_y = int(parts[1])
        compression = parts[2]
        payload_size = int(parts[3])

        payload = data[pos:pos + payload_size]
        pos += payload_size

        if compression == "LZF":
            raw = lzf_decompress(payload[1:])  # byte 0 is a version prefix, not LZF data
        elif compression == "RAW":
            raw = payload
        else:
            raise RuntimeError(f"unsupported tile compression: {compression!r}")
        if len(raw) < expected:
            raw = raw + b"\x00" * (expected - len(raw))
        if len(raw) > expected:
            raw = raw[:expected]

        arr = np.frombuffer(raw, dtype=np.uint8)
        planes = [
            arr[i * plane_size:(i + 1) * plane_size].reshape(tile_h, tile_w)
            for i in range(pixel_size)
        ]

        tile_img = Image.fromarray(np.dstack(planes[:4]), "RGBA")
        canvas.alpha_composite(tile_img, (tile_x, tile_y))

    return canvas


def build_raster_mask(zip_file, layer: dict, canvas_w: int, canvas_h: int) -> Image.Image:
    img = decode_krita_paint_layer(zip_file, layer["filename"], canvas_w, canvas_h)
    arr = np.array(img, dtype=np.uint8)

    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]

    # White border layer: pixel is border if it's opaque and all channels are bright
    is_border = (alpha > RASTER_ALPHA_THRESHOLD) & np.all(rgb >= RASTER_WHITE_THRESHOLD, axis=2)
    return Image.fromarray(is_border.astype(np.uint8) * 255, "L")


def build_group_mask(zip_file, xml_root, group_filename: str, canvas_w: int, canvas_h: int) -> Image.Image:
    ns = {"k": "http://www.calligra.org/DTD/krita"}
    group_el = next(
        (l for l in xml_root.findall(".//k:layer", ns)
         if l.attrib.get("filename") == group_filename),
        None,
    )
    if group_el is None:
        raise RuntimeError(f"grouplayer element not found for filename {group_filename!r}")

    paint_layers = [
        dict(child.attrib)
        for child in group_el.findall(".//k:layer", ns)
        if child.attrib.get("nodetype") == "paintlayer"
    ]
    if not paint_layers:
        raise RuntimeError(f"no paintlayer children found in grouplayer {group_filename!r}")

    composite = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    for child in paint_layers:
        layer_img = decode_krita_paint_layer(zip_file, child["filename"], canvas_w, canvas_h)
        composite.alpha_composite(layer_img)

    arr = np.array(composite, dtype=np.uint8)
    # Frame layers contain only border strokes (no mixed content), so any opaque pixel is border
    is_border = arr[:, :, 3] > RASTER_ALPHA_THRESHOLD
    return Image.fromarray(is_border.astype(np.uint8) * 255, "L")


# ---------------------------------------------------------------------------
# Mask application
# ---------------------------------------------------------------------------

def mask_coverage(mask: Image.Image) -> float:
    arr = np.array(mask, dtype=np.uint8)
    return float((arr > 0).sum()) / float(arr.size)


def apply_border_mask(image: Image.Image, mask: Image.Image) -> Image.Image:
    result = image.convert("RGBA")
    old_alpha = result.getchannel("A")
    transparent = Image.new("L", result.size, 0)
    # Where mask=255 (border) → alpha becomes 0 (transparent)
    # Where mask=0 (content) → alpha is unchanged
    result.putalpha(Image.composite(transparent, old_alpha, mask))
    return result



def load_merged_image(zip_file) -> Image.Image:
    if "mergedimage.png" not in zip_file.namelist():
        raise RuntimeError("mergedimage.png not found")
    with zip_file.open("mergedimage.png") as f:
        return Image.open(f).convert("RGBA")


def build_output_path(kra_path: Path) -> Path:
    relative = kra_path.relative_to(TMP_DIR)
    ep_name  = relative.parts[0]
    return RENDERS_DIR / ep_name / "transparent" / f"{relative.stem}.png"


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------

def process_kra(kra_path: Path) -> dict:
    if kra_path.name in BLACKLISTED:
        reason = BLACKLISTED[kra_path.name]
        output_path = build_output_path(kra_path)
        if output_path.exists():
            output_path.unlink()
            print(f"Deleted {output_path.name}: {reason}")
        return {
            "status": "skipped",
            "mode": None,
            "coverage": None,
            "border_layer_name": None,
            "border_layer_type": None,
            "reason": f"blacklisted: {reason}",
            "output": None,
        }

    with zipfile.ZipFile(kra_path, "r") as z:
        width, height, layers, xml_root = get_krita_info(z)
        border_layer = choose_border_layer(layers)

        if border_layer is None:
            return {
                "status": "skipped",
                "mode": None,
                "coverage": None,
                "border_layer_name": None,
                "border_layer_type": None,
                "reason": "no border layer found",
                "output": None,
            }

        nodetype = border_layer.get("nodetype", "")
        layer_name = border_layer.get("name", "")
        layer_filename = border_layer.get("filename", "")

        if nodetype == "shapelayer":
            svg = find_svg(z, layer_filename)
            if svg is None:
                raise RuntimeError(
                    f"SVG not found for shapelayer {layer_name!r} (filename: {layer_filename!r})"
                )
            mask = build_svg_mask(svg, width, height)
            mode = "svg_border"

        elif nodetype == "paintlayer":
            mask = build_raster_mask(z, border_layer, width, height)
            mode = "raster_border"

        elif nodetype == "grouplayer":
            mask = build_group_mask(z, xml_root, layer_filename, width, height)
            mode = "raster_border"

        else:
            raise RuntimeError(f"unsupported border layer nodetype: {nodetype!r}")

        coverage = mask_coverage(mask)

        if coverage == 0:
            return {
                "status": "skipped",
                "mode": None,
                "coverage": 0.0,
                "border_layer_name": layer_name,
                "border_layer_type": nodetype,
                "reason": "border mask is empty",
                "output": None,
            }

        if not (MIN_MASK_COVERAGE <= coverage <= MAX_MASK_COVERAGE):
            raise RuntimeError(
                f"border mask coverage {coverage:.4f} outside expected range "
                f"[{MIN_MASK_COVERAGE}, {MAX_MASK_COVERAGE}]"
            )

        image = load_merged_image(z)
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.LANCZOS)

        result = apply_border_mask(image, mask)

        output_path = build_output_path(kra_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output_path, "PNG")

        white_path = output_path.parent.parent / "white" / output_path.name
        white_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(white_path, "PNG")

        return {
            "status": "saved",
            "mode": mode,
            "coverage": round(coverage, 4),
            "border_layer_name": layer_name,
            "border_layer_type": nodetype,
            "reason": None,
            "output": str(output_path),
        }


# ---------------------------------------------------------------------------
# Batch processing + report
# ---------------------------------------------------------------------------

def write_report(rows: list):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    with open(REPORT_DIR / "processing_report.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    if rows:
        fieldnames = [
            "kra_file", "episode", "status", "mode", "coverage",
            "border_layer_name", "border_layer_type", "reason", "output",
        ]
        with open(REPORT_DIR / "processing_report.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def process_all_kra(kra_files: list, base_rows: list = None):
    rows = []
    counts = {"saved": 0, "skipped": 0, "error": 0}
    mode_counts = {}

    for kra_path in kra_files:
        relative = kra_path.relative_to(TMP_DIR)
        episode = relative.parts[0] if relative.parts else "unknown"

        try:
            result = process_kra(kra_path)

            row = {
                "kra_file": kra_path.name,
                "episode": episode,
                **result,
            }
            rows.append(row)

            status = result["status"]
            counts[status] = counts.get(status, 0) + 1

            mode = result["mode"] or "none"
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

            if status == "saved":
                print(f"Saved [{mode}] ({result['coverage']:.3f}): {result['output']}")
            else:
                print(f"Skip {kra_path.name}: {result['reason']}")

        except Exception as e:
            counts["error"] += 1
            rows.append({
                "kra_file": kra_path.name,
                "episode": episode,
                "status": "error",
                "mode": None,
                "coverage": None,
                "border_layer_name": None,
                "border_layer_type": None,
                "reason": str(e),
                "output": None,
            })
            print(f"Error {kra_path.name}: {e}")

    if base_rows is not None:
        retried_names = {r["kra_file"] for r in rows}
        merged = [r for r in base_rows if r["kra_file"] not in retried_names] + rows
        write_report(merged)
    else:
        write_report(rows)

    print(f"\nDone.")
    print(f"Saved:   {counts.get('saved', 0)}")
    print(f"Skipped: {counts.get('skipped', 0)}")
    print(f"Errors:  {counts.get('error', 0)}")
    print()
    print("Modes:")
    for mode, count in sorted(mode_counts.items()):
        print(f"  {mode}: {count}")
    print()
    print(f"Report: {REPORT_DIR / 'processing_report.csv'}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry-errors", action="store_true",
                        help="Re-process only files that errored in the last report")
    args = parser.parse_args()

    RENDERS_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if args.retry_errors:
        report_path = REPORT_DIR / "processing_report.json"
        if not report_path.exists():
            print("No existing report found; run without --retry-errors first.")
            return
        with open(report_path, encoding="utf-8") as f:
            base_rows = json.load(f)
        error_names = {r["kra_file"] for r in base_rows if r["status"] == "error"}
        if not error_names:
            print("No errors in the last report.")
            return
        kra_files = sorted(f for f in TMP_DIR.rglob("*.kra") if f.name in error_names)
        print(f"Retrying {len(kra_files)} errored file(s):\n")
        process_all_kra(kra_files, base_rows=base_rows)
        return

    kra_files = sorted(TMP_DIR.rglob("*.kra"))

    if ONLY_PAGE_KRA:
        kra_files = [f for f in kra_files if is_page_kra(f)]

    if not kra_files:
        print(f"No .kra files found in {TMP_DIR}")
        return

    print(f"Found {len(kra_files)} .kra files in {TMP_DIR}\n")
    process_all_kra(kra_files)


if __name__ == "__main__":
    main()
