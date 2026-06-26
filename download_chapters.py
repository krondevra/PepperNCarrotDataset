from pathlib import Path
from urllib.parse import urljoin
import re
import zipfile

import requests
from bs4 import BeautifulSoup
from tqdm import tqdm


MAIN_URL = "https://www.peppercarrot.com/en/webcomics/peppercarrot.html"
BASE_URL = "https://www.peppercarrot.com"

OUTPUT_DIR = Path("peppercarrot_zips")
MAX_EPISODE = 39

TIMEOUT = 30
CHUNK_SIZE = 1024 * 256


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def find_episode_slugs(html: str):
    soup = BeautifulSoup(html, "html.parser")

    found = set()

    # Ищем slugs в href-ссылках
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        matches = re.findall(r"ep(\d{2})_[A-Za-z0-9_-]+", href)

        for ep_num in matches:
            full_match = re.search(rf"ep{ep_num}_[A-Za-z0-9_-]+", href)
            if full_match:
                slug = full_match.group(0)
                found.add(slug)

    # На всякий случай ищем slugs во всём HTML
    for match in re.finditer(r"ep(\d{2})_[A-Za-z0-9_-]+", html):
        found.add(match.group(0))

    result = []

    for slug in found:
        ep_match = re.match(r"ep(\d{2})_", slug)
        if not ep_match:
            continue

        ep_number = int(ep_match.group(1))

        if 1 <= ep_number <= MAX_EPISODE:
            result.append((ep_number, slug))

    result.sort(key=lambda x: x[0])

    # Убираем дубли по номеру эпизода
    unique = {}
    for ep_number, slug in result:
        unique[ep_number] = slug

    return [(ep_number, unique[ep_number]) for ep_number in sorted(unique)]


def build_zip_url(slug: str) -> str:
    return f"{BASE_URL}/0_sources/{slug}/zip/{slug}_art-pack.zip"


def download_file(url: str, output_path: Path):
    temp_path = output_path.with_suffix(output_path.suffix + ".part")

    headers = {}

    if temp_path.exists():
        downloaded = temp_path.stat().st_size
        headers["Range"] = f"bytes={downloaded}-"
    else:
        downloaded = 0

    with requests.get(url, stream=True, timeout=TIMEOUT, headers=headers) as response:
        if response.status_code == 416:
            return

        response.raise_for_status()

        total_size = response.headers.get("content-length")

        if total_size is not None:
            total_size = int(total_size) + downloaded

        mode = "ab" if downloaded > 0 and response.status_code == 206 else "wb"

        if mode == "wb":
            downloaded = 0

        with open(temp_path, mode) as file:
            with tqdm(
                total=total_size,
                initial=downloaded,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc=output_path.name,
            ) as bar:
                for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                    if chunk:
                        file.write(chunk)
                        bar.update(len(chunk))

    temp_path.rename(output_path)


def is_valid_zip(path: Path) -> bool:
    if not path.exists():
        return False

    try:
        return zipfile.is_zipfile(path)
    except Exception:
        return False


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Reading episode list...")
    html = fetch_html(MAIN_URL)
    episodes = find_episode_slugs(html)

    if not episodes:
        print("No episodes found on the page.")
        return

    print(f"Found episodes: {len(episodes)}")

    missing_numbers = [
        number
        for number in range(1, MAX_EPISODE + 1)
        if number not in {ep_number for ep_number, _ in episodes}
    ]

    if missing_numbers:
        print("Warning: these episode numbers were not found on the page:")
        print(missing_numbers)

    for ep_number, slug in tqdm(episodes, desc="Episodes", unit="episode"):
        zip_url = build_zip_url(slug)
        output_path = OUTPUT_DIR / f"{slug}_art-pack.zip"

        if output_path.exists() and is_valid_zip(output_path):
            print(f"Skip existing valid zip: {output_path.name}")
            continue

        print(f"\nDownloading episode {ep_number:02d}: {slug}")
        print(zip_url)

        try:
            download_file(zip_url, output_path)

            if not is_valid_zip(output_path):
                print(f"Downloaded file is not a valid zip: {output_path.name}")
                output_path.unlink(missing_ok=True)
            else:
                print(f"Saved: {output_path}")

        except Exception as e:
            print(f"Error downloading {slug}: {e}")


if __name__ == "__main__":
    main()
