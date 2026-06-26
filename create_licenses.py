from pathlib import Path
import csv
import json
import re
import shutil
from datetime import date

import requests
from bs4 import BeautifulSoup


ZIPS_DIR = Path("peppercarrot_zips")
LICENSES_DIR = Path("licenses")

ABOUT_URL = "https://www.peppercarrot.com/en/about/index.html"
PHILOSOPHY_URL = "https://www.peppercarrot.com/en/philosophy/index.html"

PROJECT_NAME = "Pepper&Carrot"
PROJECT_URL = "https://www.peppercarrot.com/"
LICENSE_NAME = "Creative Commons Attribution 4.0 International"
LICENSE_SHORT = "CC BY 4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"

CHANGES_MADE = (
    "Downloaded original Pepper&Carrot art-pack zip archives and organized them "
    "as a dataset. No original authorship is claimed. No endorsement is implied."
)

ROLE_NAMES = [
    "Art",
    "Scenario",
    "Translation",
    "English Translation",
    "Proofreading",
    "Correctors",
    "Corrections",
    "Beta-readers",
    "Beta-readers and corrections",
    "Script-doctor",
    "Dialogue Improvements",
    "Brainstorming",
    "Contribution",
    "Inspiration",
    "Special Thanks",
]


def fetch_html(url: str) -> str:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace(" ,", ",")
    text = text.replace(" .", ".")
    return text.strip(" .")


def parse_zip_name(path: Path):
    match = re.match(r"ep(\d{2})_(.+?)_art-pack\.zip$", path.name)

    if not match:
        return None

    episode_number = int(match.group(1))
    slug_without_ep = match.group(2)
    slug = f"ep{episode_number:02d}_{slug_without_ep}"

    return episode_number, slug


def build_source_url(slug: str) -> str:
    return f"https://www.peppercarrot.com/0_sources/{slug}/zip/{slug}_art-pack.zip"


def get_people_from_text(text: str):
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = text.replace(" and ", ", ")
    text = text.replace(";", ",")

    parts = [clean_text(part) for part in text.split(",")]
    return [part for part in parts if part]


def parse_credit_block(block: str):
    roles = {}

    role_pattern = "|".join(
        re.escape(role)
        for role in sorted(ROLE_NAMES, key=len, reverse=True)
    )

    matches = list(re.finditer(rf"({role_pattern})\s*:", block))

    if not matches:
        return roles

    for i, match in enumerate(matches):
        role = match.group(1)
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(block)

        value = clean_text(block[start:end])

        if value:
            roles[role] = {
                "raw": value,
                "people": get_people_from_text(value),
            }

    return roles


def parse_episode_credits_from_about_html(html: str):
    soup = BeautifulSoup(html, "html.parser")

    full_text = soup.get_text("\n")
    full_text = full_text.replace("\xa0", " ")

    episode_header_re = re.compile(
        r"Episode\s+(\d+)\s*:\s*(.+?)\s*\(published on ([^)]+)\)",
        re.IGNORECASE,
    )

    headers = list(episode_header_re.finditer(full_text))
    episodes = {}

    for index, header in enumerate(headers):
        number = int(header.group(1))
        title = clean_text(header.group(2))
        published_on = clean_text(header.group(3))

        start = header.end()
        end = headers[index + 1].start() if index + 1 < len(headers) else len(full_text)

        block = full_text[start:end]
        block = clean_text(block)

        language_notes = []

        if "English (original version)" in block:
            language_notes.append("English (original version)")

        roles = parse_credit_block(block)

        episodes[number] = {
            "episode_number": number,
            "episode_title": title,
            "published_on": published_on,
            "credit_roles": roles,
            "language_notes": language_notes,
            "raw_credit_block": block,
        }

    return episodes


def clean_original_version_notes(official_credits):
    for episode in official_credits.values():
        roles = episode.get("credit_roles", {})
        notes = episode.setdefault("language_notes", [])

        for role_data in roles.values():
            raw = role_data.get("raw", "")

            if "English (original version)" in raw:
                raw = raw.replace(". English (original version)", "")
                raw = raw.replace("English (original version)", "")
                raw = clean_text(raw)

                role_data["raw"] = raw
                role_data["people"] = [
                    person
                    for person in get_people_from_text(raw)
                    if "English (original version)" not in person
                ]

                if "English (original version)" not in notes:
                    notes.append("English (original version)")

        raw_block = episode.get("raw_credit_block", "")
        raw_block = raw_block.replace(". English (original version)", "")
        raw_block = raw_block.replace("English (original version)", "")
        episode["raw_credit_block"] = clean_text(raw_block)


def build_attribution_text(item):
    parts = [
        f"{PROJECT_NAME}, Episode {item['episode_number']:02d}: {item['episode_title']}",
        f"Source: {item['source_url']}",
        f"License: {LICENSE_NAME} ({LICENSE_URL})",
    ]

    for role, value in item["credit_roles"].items():
        parts.append(f"{role}: {value['raw']}")

    if item["language_notes"]:
        for note in item["language_notes"]:
            parts.append(f"Note: {note}")

    parts.append(f"Changes: {CHANGES_MADE}")
    parts.append("No endorsement by the original authors or contributors is implied.")

    return " | ".join(parts)


def collect_local_episodes(official_credits):
    result = []

    for zip_path in sorted(ZIPS_DIR.glob("ep*_art-pack.zip")):
        parsed = parse_zip_name(zip_path)

        if not parsed:
            continue

        episode_number, slug = parsed
        official = official_credits.get(episode_number, {})

        item = {
            "episode_number": episode_number,
            "episode_slug": slug,
            "episode_title": official.get("episode_title", slug),
            "published_on": official.get("published_on"),
            "zip_file": str(zip_path),
            "source_url": build_source_url(slug),
            "project": PROJECT_NAME,
            "project_url": PROJECT_URL,
            "license": LICENSE_NAME,
            "license_short": LICENSE_SHORT,
            "license_url": LICENSE_URL,
            "policy_url": PHILOSOPHY_URL,
            "credits_source_url": ABOUT_URL,
            "changes_made": CHANGES_MADE,
            "credit_roles": official.get("credit_roles", {}),
            "language_notes": official.get("language_notes", []),
            "raw_credit_block": official.get("raw_credit_block", ""),
            "generated_at": str(date.today()),
        }

        item["attribution_text"] = build_attribution_text(item)
        result.append(item)

    return result


def write_json(episodes):
    path = LICENSES_DIR / "episodes_licenses.json"

    with open(path, "w", encoding="utf-8") as file:
        json.dump(episodes, file, indent=2, ensure_ascii=False)


def write_csv(episodes):
    path = LICENSES_DIR / "episodes_licenses.csv"

    rows = []

    for ep in episodes:
        row = ep.copy()
        row["credit_roles"] = json.dumps(ep["credit_roles"], ensure_ascii=False)
        row["language_notes"] = json.dumps(ep["language_notes"], ensure_ascii=False)
        rows.append(row)

    if not rows:
        return

    with open(path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def write_attribution_md(episodes):
    lines = [
        "# Pepper&Carrot Attribution",
        "",
        f"Original project: {PROJECT_NAME}",
        f"Project URL: {PROJECT_URL}",
        f"License: {LICENSE_NAME} ({LICENSE_SHORT})",
        f"License URL: {LICENSE_URL}",
        f"Author policy page: {PHILOSOPHY_URL}",
        f"Credits source: {ABOUT_URL}",
        "",
        "Changes made:",
        "",
        f"- {CHANGES_MADE}",
        "",
        "This dataset does not imply endorsement by David Revoy, Pepper&Carrot, or contributors.",
        "",
        "## Episodes",
        "",
    ]

    for ep in episodes:
        lines.append(f"### Episode {ep['episode_number']:02d}: {ep['episode_title']}")
        lines.append("")
        lines.append(f"- Source zip: {ep['source_url']}")
        lines.append(f"- License: {ep['license_short']}")
        lines.append(f"- Published: {ep.get('published_on') or 'unknown'}")

        if ep["credit_roles"]:
            for role, value in ep["credit_roles"].items():
                lines.append(f"- {role}: {value['raw']}")
        else:
            lines.append("- Credits: not parsed automatically")

        if ep["language_notes"]:
            for note in ep["language_notes"]:
                lines.append(f"- Note: {note}")

        lines.append("")
        lines.append("Attribution text:")
        lines.append("")
        lines.append(f"> {ep['attribution_text']}")
        lines.append("")

    path = LICENSES_DIR / "ATTRIBUTION.md"
    path.write_text("\n".join(lines), encoding="utf-8")


def write_license_file():
    text = f"""# License

Original Pepper&Carrot works are licensed under:

{LICENSE_NAME} ({LICENSE_SHORT})
{LICENSE_URL}

Original project:
{PROJECT_URL}

Author policy page:
{PHILOSOPHY_URL}

Credits source:
{ABOUT_URL}

Dataset changes:
{CHANGES_MADE}

No endorsement:
This dataset does not imply endorsement by David Revoy, Pepper&Carrot,
or any listed contributors.
"""

    path = LICENSES_DIR / "LICENSE_CC_BY_4.0.txt"
    path.write_text(text, encoding="utf-8")


def save_source_snapshots(about_html: str, philosophy_html: str):
    snapshots_dir = LICENSES_DIR / "source_snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    (snapshots_dir / "about_index.html").write_text(about_html, encoding="utf-8")
    (snapshots_dir / "philosophy_index.html").write_text(philosophy_html, encoding="utf-8")


def recreate_output_dir():
    if LICENSES_DIR.exists():
        shutil.rmtree(LICENSES_DIR)

    LICENSES_DIR.mkdir(parents=True, exist_ok=True)


def main():
    recreate_output_dir()

    print("Downloading official credits page...")
    about_html = fetch_html(ABOUT_URL)

    print("Downloading official philosophy/license policy page...")
    philosophy_html = fetch_html(PHILOSOPHY_URL)

    official_credits = parse_episode_credits_from_about_html(about_html)
    clean_original_version_notes(official_credits)

    episodes = collect_local_episodes(official_credits)

    if not episodes:
        print(f"No finished .zip files found in {ZIPS_DIR}")
        return

    write_license_file()
    write_json(episodes)
    write_csv(episodes)
    write_attribution_md(episodes)
    save_source_snapshots(about_html, philosophy_html)

    print(f"Created license metadata for {len(episodes)} local episodes.")
    print(f"Parsed official credits for {len(official_credits)} episodes.")
    print(f"Output folder: {LICENSES_DIR}")

    missing_credits = [
        ep["episode_number"]
        for ep in episodes
        if not ep["credit_roles"]
    ]

    if missing_credits:
        print("Warning: no parsed credits for episodes:")
        print(missing_credits)
    else:
        print("All local episodes have parsed credits.")


if __name__ == "__main__":
    main()
