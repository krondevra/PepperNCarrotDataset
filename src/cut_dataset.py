"""
Cut a random subset of pages from data/dataset/ for quick ML training runs,
split into non-overlapping train/val sets.

Source: data/dataset/{episode}/{variant}/{page}.png
Output: {output}/train/{episode}/{variant}/{page}.png
        {output}/val/{episode}/{variant}/{page}.png

Selects N pages at random (fixed seed for reproducibility) from across the
whole dataset, holds out a fraction of them for validation, then copies
every variant file that exists for each selected page — so both splits keep
the same folder layout as data/dataset/ and every training pair stays intact.
"""

import argparse
import random
import shutil
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, it, desc="", **kw):
            self._it = list(it); self._desc = desc; self._n = 0
            print(f"{desc}: 0/{len(self._it)}", end="\r", flush=True)
        def __iter__(self):
            for x in self._it:
                yield x
                self._n += 1
                print(f"{self._desc}: {self._n}/{len(self._it)}", end="\r", flush=True)
            print()
        def set_postfix(self, **kw): pass
        @staticmethod
        def write(msg): print(msg)

DATASET_DIR = Path("data/dataset")


def collect_pages(dataset_dir: Path):
    """Return sorted list of (episode_dir, page_stem) pairs, one per unique page."""
    pages = []
    for ep_dir in sorted(d for d in dataset_dir.iterdir() if d.is_dir()):
        variant_dirs = sorted(d for d in ep_dir.iterdir() if d.is_dir())
        page_stems = set()
        for variant_dir in variant_dirs:
            page_stems.update(p.stem for p in variant_dir.glob("*.png"))
        for stem in sorted(page_stems):
            pages.append((ep_dir, stem))
    return pages


def copy_page(ep_dir: Path, stem: str, output_dir: Path):
    variant_dirs = sorted(d for d in ep_dir.iterdir() if d.is_dir())
    for variant_dir in variant_dirs:
        src = variant_dir / f"{stem}.png"
        if not src.exists():
            continue
        dst_dir = output_dir / ep_dir.name / variant_dir.name
        dst_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst_dir / src.name)


def copy_split(pages, output_dir: Path, desc: str):
    output_dir.mkdir(parents=True, exist_ok=True)
    bar = tqdm(pages, unit="page", desc=desc)
    for ep_dir, stem in bar:
        bar.set_postfix(ep=ep_dir.name.split("_")[0], page=stem)
        copy_page(ep_dir, stem, output_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Copy a random subset of dataset pages (all variants) into "
                     "non-overlapping train/ and val/ folders for ML training."
    )
    parser.add_argument(
        "samples",
        help="Number of pages to sample from across the whole dataset, or 'all' for every page.",
    )
    parser.add_argument(
        "--val-split", type=float, default=0.1,
        help="Fraction of sampled pages held out for validation (default: 0.1).",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
        help="Random seed for reproducible sampling (default: 42).",
    )
    parser.add_argument(
        "--source", type=Path, default=DATASET_DIR,
        help="Dataset directory to sample from (default: data/dataset).",
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/dataset_split"),
        help="Output directory; train/ and val/ subfolders are created inside it "
             "(default: data/dataset_split).",
    )
    args = parser.parse_args()

    if not args.source.exists():
        print(f"Dataset directory not found: {args.source}")
        return

    if not 0.0 <= args.val_split < 1.0:
        print(f"--val-split must be in [0.0, 1.0), got {args.val_split}")
        return

    pages = collect_pages(args.source)
    if not pages:
        print(f"No pages found under {args.source}")
        return

    total = len(pages) if args.samples == "all" else int(args.samples)
    if total > len(pages):
        print(f"Requested {total} samples but only {len(pages)} pages exist — using all of them.")
        total = len(pages)

    rng = random.Random(args.seed)
    selected = rng.sample(pages, total)  # unique pages in random order, no overlap possible

    val_count = round(total * args.val_split)
    val_pages, train_pages = selected[:val_count], selected[val_count:]
    train_pages.sort(key=lambda ep_stem: (ep_stem[0].name, ep_stem[1]))
    val_pages.sort(key=lambda ep_stem: (ep_stem[0].name, ep_stem[1]))

    copy_split(train_pages, args.output / "train", "cut_dataset[train]")
    copy_split(val_pages, args.output / "val", "cut_dataset[val]")

    print(f"\nDone. {len(train_pages)} train pages + {len(val_pages)} val pages copied to {args.output}")


if __name__ == "__main__":
    main()
