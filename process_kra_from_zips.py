from pathlib import Path
import zipfile
import xml.etree.ElementTree as ET
import re
import shutil
from PIL import Image, ImageDraw


ZIPS_DIR = Path("peppercarrot_zips")
TMP_DIR = Path(".tmp/kra_extracted")
OUTPUT_DIR = Path("processed_png")

FRAME_LAYER_NAME = "frame"

# True = обрабатывать только страницы вроде E01P01.kra, E02P03.kra
# False = пробовать обработать все .kra
ONLY_PAGE_KRA = True

CLEAN_TMP_BEFORE_RUN = True


def is_page_kra(path: Path) -> bool:
    return re.search(r"p\d+\.kra$", path.name.lower()) is not None


def safe_extract_kra_files(zip_path: Path, episode_tmp_dir: Path):
    extracted = []

    with zipfile.ZipFile(zip_path, "r") as z:
        for member in z.namelist():
            if not member.lower().endswith(".kra"):
                continue

            member_path = Path(member)

            if ONLY_PAGE_KRA and not is_page_kra(member_path):
                continue

            # Защита от странных путей внутри zip
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

    frame_filename = None

    for layer in root.findall(".//k:layer", ns):
        layer_name = layer.attrib.get("name", "")
        if layer_name.lower() == FRAME_LAYER_NAME.lower():
            frame_filename = layer.attrib.get("filename")
            break

    return width, height, frame_filename


def find_frame_svg(zip_file, frame_filename):
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


def transform_point(x, y, matrix):
    a, b, c, d, e, f = matrix
    return (
        a * x + c * y + e,
        b * x + d * y + f,
    )


def build_frame_mask(svg_text, canvas_width, canvas_height):
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


def process_kra(kra_path: Path, output_path: Path):
    with zipfile.ZipFile(kra_path, "r") as z:
        names = z.namelist()

        if "mergedimage.png" not in names:
            return False, "mergedimage.png not found"

        width, height, frame_filename = get_krita_info(z)

        if not frame_filename:
            return False, f"layer '{FRAME_LAYER_NAME}' not found"

        svg_text = find_frame_svg(z, frame_filename)

        if not svg_text:
            return False, f"frame SVG for '{frame_filename}' not found"

        with z.open("mergedimage.png") as f:
            image = Image.open(f).convert("RGBA")

    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)

    frame_mask = build_frame_mask(svg_text, width, height)

    old_alpha = image.getchannel("A")
    transparent = Image.new("L", image.size, 0)

    final_alpha = Image.composite(transparent, old_alpha, frame_mask)
    image.putalpha(final_alpha)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG")

    return True, "saved"


def episode_name_from_zip(zip_path: Path):
    name = zip_path.name

    if name.endswith("_art-pack.zip"):
        return name.replace("_art-pack.zip", "")

    return zip_path.stem


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


def process_all_kra(kra_files):
    saved_count = 0
    skipped_count = 0
    error_count = 0

    for kra_path in kra_files:
        try:
            relative = kra_path.relative_to(TMP_DIR)
            output_path = OUTPUT_DIR / relative.with_suffix(".png")

            ok, message = process_kra(kra_path, output_path)

            if ok:
                saved_count += 1
                print(f"Saved: {output_path}")
            else:
                skipped_count += 1
                print(f"Skip {kra_path.name}: {message}")

        except Exception as e:
            error_count += 1
            print(f"Error in {kra_path}: {e}")

    print("\nDone.")
    print(f"Saved PNG: {saved_count}")
    print(f"Skipped: {skipped_count}")
    print(f"Errors: {error_count}")


def main():
    if CLEAN_TMP_BEFORE_RUN and TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    kra_files = extract_all_kra()

    if not kra_files:
        print("No .kra files extracted.")
        return

    print(f"\nTotal extracted .kra files: {len(kra_files)}")
    print("\nProcessing .kra files...")

    process_all_kra(kra_files)


if __name__ == "__main__":
    main()
