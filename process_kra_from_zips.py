from pathlib import Path
import csv
import json
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFilter
import numpy as np


ZIPS_DIR = Path("peppercarrot_zips")
TMP_DIR = Path(".tmp/kra_extracted")

OUTPUT_DIR = Path("processed_png")
NEEDS_REVIEW_DIR = Path("processed_png_needs_review")
REPORT_DIR = Path("processing_report")

CLEAN_TMP_BEFORE_RUN = True
CLEAN_OUTPUT_BEFORE_RUN = False

ONLY_PAGE_KRA = True

FRAME_LAYER_KEYWORDS = [
    "frame",
    "panel-frame",
    "panel frame",
]

SVG_ALPHA_THRESHOLD = 1
RASTER_ALPHA_THRESHOLD = 8

WHITE_THRESHOLD = 238
WHITE_MAX_CHANNEL_DIFFERENCE = 22

MIN_VISUAL_MASK_COVERAGE = 0.01
MAX_VISUAL_MASK_COVERAGE = 0.70

MIN_RASTER_MASK_COVERAGE = 0.005
MAX_RASTER_MASK_COVERAGE = 0.80


def is_page_kra(path: Path) -> bool:
    return re.search(r"p\d+\.kra$", path.name.lower()) is not None


def episode_name_from_zip(zip_path: Path) -> str:
    if zip_path.name.endswith("_art-pack.zip"):
        return zip_path.name.replace("_art-pack.zip", "")
    return zip_path.stem


def safe_extract_kra_files(zip_path: Path, episode_tmp_dir: Path):
    extracted = []

    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.namelist():
            if not member.lower().endswith(".kra"):
                continue

            member_path = Path(member)

            if ONLY_PAGE_KRA and not is_page_kra(member_path):
                continue

            safe_parts = [
                part
                for part in member_path.parts
                if part not in ("..", ".", "")
            ]

            if not safe_parts:
                continue

            output_path = episode_tmp_dir.joinpath(*safe_parts)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with z.open(member) as src, open(output_path, "wb") as dst:
                shutil.copyfileobj(src, dst)

            extracted.append(output_path)

    return extracted


def clean_layer_name(name: str) -> str:
    return name.lower().strip().replace("_", "-").replace(" ", "-")


def is_frame_like_layer(layer: dict) -> bool:
    name = clean_layer_name(layer.get("name", ""))

    if name in ["frame", "panel-frame", "panel"]:
        return True

    if "frame" in name and "keyframe" not in name:
        return True

    return False


def parse_matrix(transform: str):
    if not transform:
        return 1, 0, 0, 1, 0, 0

    match = re.search(r"matrix\(([^)]+)\)", transform)
    if not match:
        return 1, 0, 0, 1, 0, 0

    values = [
        float(x)
        for x in re.split(r"[,\s]+", match.group(1).strip())
        if x
    ]

    if len(values) != 6:
        return 1, 0, 0, 1, 0, 0

    return values


def transform_point(x, y, matrix):
    a, b, c, d, e, f = matrix
    return (
        a * x + c * y + e,
        b * x + d * y + f,
    )


def get_krita_info(zip_file):
    if "maindoc.xml" not in zip_file.namelist():
        raise RuntimeError("maindoc.xml not found")

    maindoc = zip_file.read("maindoc.xml").decode("utf-8", errors="ignore")
    root = ET.fromstring(maindoc)

    ns = {"k": "http://www.calligra.org/DTD/krita"}

    image = root.find(".//k:IMAGE", ns)
    if image is None:
        raise RuntimeError("IMAGE info not found in maindoc.xml")

    width = int(image.attrib["width"])
    height = int(image.attrib["height"])

    layers = []

    for layer in root.findall(".//k:layer", ns):
        layers.append(dict(layer.attrib))

    return width, height, layers


def find_layer_file(zip_file, layer_filename: str):
    if not layer_filename:
        return None

    for name in zip_file.namelist():
        if name.endswith(f"/{layer_filename}") or name == layer_filename:
            return name

    return None


def find_frame_svg(zip_file, frame_filename: str):
    if not frame_filename:
        return None

    possible_endings = [
        f"/layers/{frame_filename}.shapelayer/content.svg",
        f"{frame_filename}.shapelayer/content.svg",
    ]

    for name in zip_file.namelist():
        for ending in possible_endings:
            if name.endswith(ending):
                return zip_file.read(name).decode("utf-8", errors="ignore")

    return None


def choose_frame_layer(layers):
    frame_like = [layer for layer in layers if is_frame_like_layer(layer)]

    if not frame_like:
        return None

    def score(layer):
        name = clean_layer_name(layer.get("name", ""))
        nodetype = layer.get("nodetype", "")

        value = 0

        if name == "frame":
            value += 100
        if name == "panel-frame":
            value += 95
        if "panel-frame" in name:
            value += 80
        if "frame" in name:
            value += 60

        if nodetype == "shapelayer":
            value += 10
        if nodetype == "paintlayer":
            value += 8

        if layer.get("visible", "1") == "1":
            value += 5

        return value

    frame_like.sort(key=score, reverse=True)
    return frame_like[0]


def build_svg_frame_mask(svg_text, canvas_width, canvas_height):
    svg_root = ET.fromstring(svg_text)

    viewbox = svg_root.attrib.get("viewBox")
    if not viewbox:
        raise RuntimeError("SVG viewBox not found")

    _, _, vb_width, vb_height = [float(x) for x in viewbox.split()]

    scale_x = canvas_width / vb_width
    scale_y = canvas_height / vb_height

    mask = Image.new("L", (canvas_width, canvas_height), 0)
    draw = ImageDraw.Draw(mask)

    svg_ns = "{http://www.w3.org/2000/svg}"
    rect_count = 0

    for rect in svg_root.findall(f".//{svg_ns}rect"):
        rect_count += 1

        x = float(rect.attrib.get("x", 0))
        y = float(rect.attrib.get("y", 0))
        w = float(rect.attrib.get("width", 0))
        h = float(rect.attrib.get("height", 0))

        matrix = parse_matrix(rect.attrib.get("transform", ""))

        points = [
            transform_point(x, y, matrix),
            transform_point(x + w, y, matrix),
            transform_point(x + w, y + h, matrix),
            transform_point(x, y + h, matrix),
        ]

        points = [
            (
                round(px * scale_x),
                round(py * scale_y),
            )
            for px, py in points
        ]

        draw.polygon(points, fill=255)

    if rect_count == 0:
        raise RuntimeError("No rect shapes found in frame SVG")

    return mask


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

    tile_width = int(header["TILEWIDTH"])
    tile_height = int(header["TILEHEIGHT"])
    pixel_size = int(header["PIXELSIZE"])

    return pos, tile_count, tile_width, tile_height, pixel_size


def decode_krita_paint_layer(zip_file, layer_filename: str, canvas_width: int, canvas_height: int):
    layer_path = find_layer_file(zip_file, layer_filename)

    if not layer_path:
        raise RuntimeError(f"paint layer data not found for '{layer_filename}'")

    data = zip_file.read(layer_path)

    pos, tile_count, tile_width, tile_height, pixel_size = parse_krita_tile_header(data)

    if pixel_size < 4:
        raise RuntimeError(f"Unsupported pixel size: {pixel_size}")

    canvas = Image.new("RGBA", (canvas_width, canvas_height), (0, 0, 0, 0))
    tile_plane_size = tile_width * tile_height
    expected_size = tile_plane_size * pixel_size

    for _ in range(tile_count):
        line_end = data.index(b"\n", pos)
        line = data[pos:line_end].decode("utf-8", errors="ignore")
        pos = line_end + 1

        parts = line.split(",")

        if len(parts) != 4:
            raise RuntimeError(f"Bad tile line: {line}")

        tile_x = int(parts[0])
        tile_y = int(parts[1])
        compression = parts[2]
        payload_size = int(parts[3])

        payload = data[pos:pos + payload_size]
        pos += payload_size

        if compression == "LZF":
            raw = lzf_decompress(payload)
        elif compression == "RAW":
            raw = payload
        else:
            raise RuntimeError(f"Unsupported tile compression: {compression}")

        # В Krita tile data часто есть 1 служебный байт перед данными пикселей.
        if len(raw) == expected_size + 1:
            raw = raw[1:]

        if len(raw) < expected_size:
            raw = raw + b"\x00" * (expected_size - len(raw))

        if len(raw) > expected_size:
            raw = raw[:expected_size]

        arr = np.frombuffer(raw, dtype=np.uint8)

        # В Krita этот paint layer хранится как planar data:
        # R plane, G plane, B plane, A plane.
        planes = [
            arr[i * tile_plane_size:(i + 1) * tile_plane_size].reshape(
                tile_height,
                tile_width,
            )
            for i in range(pixel_size)
        ]

        rgba = np.dstack(planes[:4])
        tile_image = Image.fromarray(rgba, "RGBA")

        canvas.alpha_composite(tile_image, (tile_x, tile_y))

    return canvas


def mask_coverage(mask: Image.Image) -> float:
    arr = np.array(mask, dtype=np.uint8)
    return float((arr > 0).sum()) / float(arr.size)


def validate_mask(mask: Image.Image, min_coverage: float, max_coverage: float):
    coverage = mask_coverage(mask)
    return min_coverage <= coverage <= max_coverage, coverage


def build_raster_frame_mask(zip_file, layer, width, height):
    layer_image = decode_krita_paint_layer(
        zip_file,
        layer["filename"],
        width,
        height,
    )

    alpha = layer_image.getchannel("A")

    mask = alpha.point(
        lambda a: 255 if a > RASTER_ALPHA_THRESHOLD else 0
    )

    valid, coverage = validate_mask(
        mask,
        MIN_RASTER_MASK_COVERAGE,
        MAX_RASTER_MASK_COVERAGE,
    )

    if not valid:
        raise RuntimeError(
            f"raster frame mask coverage is suspicious: {coverage:.3f}"
        )

    return mask, coverage


def build_visual_fallback_mask(image: Image.Image):
    rgba = image.convert("RGBA")
    arr = np.array(rgba, dtype=np.uint8)

    rgb = arr[:, :, :3]
    alpha = arr[:, :, 3]

    min_channel = rgb.min(axis=2)
    max_channel = rgb.max(axis=2)
    channel_diff = max_channel - min_channel

    near_white = (
        (alpha > 0)
        & (min_channel >= WHITE_THRESHOLD)
        & (channel_diff <= WHITE_MAX_CHANNEL_DIFFERENCE)
    )

    mask = Image.fromarray((near_white * 255).astype(np.uint8), "L")

    # Убираем мелкий шум, но оставляем большие белые gutters.
    mask = mask.filter(ImageFilter.MinFilter(3))
    mask = mask.filter(ImageFilter.MaxFilter(7))

    valid, coverage = validate_mask(
        mask,
        MIN_VISUAL_MASK_COVERAGE,
        MAX_VISUAL_MASK_COVERAGE,
    )

    if not valid:
        raise RuntimeError(
            f"visual fallback mask coverage is suspicious: {coverage:.3f}"
        )

    return mask, coverage


def apply_transparency_mask(image: Image.Image, mask: Image.Image):
    result = image.convert("RGBA")

    old_alpha = result.getchannel("A")
    transparent = Image.new("L", result.size, 0)

    final_alpha = Image.composite(transparent, old_alpha, mask)
    result.putalpha(final_alpha)

    return result


def load_merged_image(zip_file):
    if "mergedimage.png" not in zip_file.namelist():
        raise RuntimeError("mergedimage.png not found")

    with zip_file.open("mergedimage.png") as f:
        return Image.open(f).convert("RGBA")


def process_kra(kra_path: Path, output_path: Path, needs_review_path: Path):
    with zipfile.ZipFile(kra_path, "r") as z:
        width, height, layers = get_krita_info(z)
        image = load_merged_image(z)

        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.LANCZOS)

        frame_layer = choose_frame_layer(layers)

        used_mode = None
        coverage = None
        mask = None
        reason = None

        if frame_layer:
            svg_text = find_frame_svg(z, frame_layer.get("filename"))

            if svg_text:
                try:
                    mask = build_svg_frame_mask(svg_text, width, height)
                    coverage = mask_coverage(mask)
                    used_mode = "normal_svg"
                except Exception as e:
                    reason = f"normal_svg failed: {e}"

            if mask is None and frame_layer.get("nodetype") == "paintlayer":
                try:
                    mask, coverage = build_raster_frame_mask(
                        z,
                        frame_layer,
                        width,
                        height,
                    )
                    used_mode = "raster_frame"
                except Exception as e:
                    reason = f"raster_frame failed: {e}"

        if mask is None:
            try:
                mask, coverage = build_visual_fallback_mask(image)
                used_mode = "fallback_visual_needs_review"
            except Exception as e:
                if reason:
                    reason = f"{reason}; fallback_visual failed: {e}"
                else:
                    reason = f"fallback_visual failed: {e}"

        if mask is None:
            return {
                "status": "skipped",
                "mode": None,
                "reason": reason or "no usable mask",
                "coverage": None,
                "frame_layer_name": frame_layer.get("name") if frame_layer else None,
                "frame_layer_type": frame_layer.get("nodetype") if frame_layer else None,
                "frame_layer_filename": frame_layer.get("filename") if frame_layer else None,
                "output": None,
            }

        result = apply_transparency_mask(image, mask)

        if used_mode == "fallback_visual_needs_review":
            needs_review_path.parent.mkdir(parents=True, exist_ok=True)
            result.save(needs_review_path, "PNG")
            output = needs_review_path
            status = "needs_review"
        else:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            result.save(output_path, "PNG")
            output = output_path
            status = "saved"

        return {
            "status": status,
            "mode": used_mode,
            "reason": reason,
            "coverage": coverage,
            "frame_layer_name": frame_layer.get("name") if frame_layer else None,
            "frame_layer_type": frame_layer.get("nodetype") if frame_layer else None,
            "frame_layer_filename": frame_layer.get("filename") if frame_layer else None,
            "output": str(output),
        }


def extract_all_kra():
    zip_files = sorted(ZIPS_DIR.glob("*.zip"))

    if not zip_files:
        print(f"No .zip files found in {ZIPS_DIR}")
        return []

    all_extracted = []

    for zip_path in zip_files:
        episode_name = episode_name_from_zip(zip_path)
        episode_tmp_dir = TMP_DIR / episode_name

        print(f"\nExtracting KRA from: {zip_path.name}")

        extracted = safe_extract_kra_files(zip_path, episode_tmp_dir)
        all_extracted.extend(extracted)

        print(f"Extracted: {len(extracted)} .kra files")

    return all_extracted


def write_report(rows):
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    json_path = REPORT_DIR / "processing_report.json"
    csv_path = REPORT_DIR / "processing_report.csv"

    with open(json_path, "w", encoding="utf-8") as file:
        json.dump(rows, file, indent=2, ensure_ascii=False)

    if rows:
        fieldnames = [
            "kra_file",
            "episode",
            "status",
            "mode",
            "coverage",
            "frame_layer_name",
            "frame_layer_type",
            "frame_layer_filename",
            "reason",
            "output",
        ]

        with open(csv_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)


def process_all_kra(kra_files):
    rows = []

    saved_count = 0
    needs_review_count = 0
    skipped_count = 0
    error_count = 0

    mode_counts = {}

    for kra_path in kra_files:
        relative = kra_path.relative_to(TMP_DIR)
        episode = relative.parts[0] if relative.parts else "unknown"

        output_path = OUTPUT_DIR / relative.with_suffix(".png")
        needs_review_path = NEEDS_REVIEW_DIR / relative.with_suffix(".png")

        try:
            result = process_kra(kra_path, output_path, needs_review_path)

            row = {
                "kra_file": kra_path.name,
                "episode": episode,
                "status": result["status"],
                "mode": result["mode"],
                "coverage": result["coverage"],
                "frame_layer_name": result["frame_layer_name"],
                "frame_layer_type": result["frame_layer_type"],
                "frame_layer_filename": result["frame_layer_filename"],
                "reason": result["reason"],
                "output": result["output"],
            }

            rows.append(row)

            mode = result["mode"] or "none"
            mode_counts[mode] = mode_counts.get(mode, 0) + 1

            if result["status"] == "saved":
                saved_count += 1
                print(f"Saved [{result['mode']}]: {result['output']}")

            elif result["status"] == "needs_review":
                needs_review_count += 1
                print(f"Needs review [{result['mode']}]: {result['output']}")

            else:
                skipped_count += 1
                print(f"Skip {kra_path.name}: {result['reason']}")

        except Exception as e:
            error_count += 1

            rows.append({
                "kra_file": kra_path.name,
                "episode": episode,
                "status": "error",
                "mode": None,
                "coverage": None,
                "frame_layer_name": None,
                "frame_layer_type": None,
                "frame_layer_filename": None,
                "reason": str(e),
                "output": None,
            })

            print(f"Error in {kra_path}: {e}")

    write_report(rows)

    print("\nDone.")
    print(f"Saved PNG: {saved_count}")
    print(f"Needs review: {needs_review_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Errors: {error_count}")
    print("")
    print("Modes:")

    for mode, count in sorted(mode_counts.items()):
        print(f"- {mode}: {count}")

    print("")
    print(f"Report: {REPORT_DIR / 'processing_report.csv'}")
    print(f"Report: {REPORT_DIR / 'processing_report.json'}")


def main():
    if CLEAN_TMP_BEFORE_RUN and TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)

    if CLEAN_OUTPUT_BEFORE_RUN:
        if OUTPUT_DIR.exists():
            shutil.rmtree(OUTPUT_DIR)
        if NEEDS_REVIEW_DIR.exists():
            shutil.rmtree(NEEDS_REVIEW_DIR)
        if REPORT_DIR.exists():
            shutil.rmtree(REPORT_DIR)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    NEEDS_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    kra_files = extract_all_kra()

    if not kra_files:
        print("No .kra files extracted.")
        return

    print(f"\nTotal extracted .kra files: {len(kra_files)}")
    print("\nProcessing .kra files...")

    process_all_kra(kra_files)


if __name__ == "__main__":
    main()
