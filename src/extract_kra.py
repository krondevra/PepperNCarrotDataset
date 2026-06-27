from pathlib import Path
import re
import shutil
import zipfile


ZIPS_DIR = Path("data/peppercarrot_zips")
TMP_DIR = Path("data/kra_extracted")

ONLY_PAGE_KRA = True
CLEAN_TMP_BEFORE_RUN = False


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


def main():
    if CLEAN_TMP_BEFORE_RUN and TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    zip_files = sorted(ZIPS_DIR.glob("*.zip"))

    if not zip_files:
        print(f"No .zip files found in {ZIPS_DIR}")
        return

    total = 0

    for zip_path in zip_files:
        episode_name = episode_name_from_zip(zip_path)
        episode_tmp_dir = TMP_DIR / episode_name

        print(f"Extracting: {zip_path.name}")
        extracted = safe_extract_kra_files(zip_path, episode_tmp_dir)
        total += len(extracted)
        print(f"  {len(extracted)} .kra files")

    print(f"\nTotal: {total} .kra files → {TMP_DIR}")


if __name__ == "__main__":
    main()
