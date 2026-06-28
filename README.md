# Pepper & Carrot Dataset

> **Special thanks to [David Revoy](https://www.davidrevoy.com/)** — creator of [Pepper & Carrot](https://www.peppercarrot.com/), the open-source webcomic released under CC BY 4.0. His decision to publish not only the finished pages but the original Krita source files with full layer structure made this kind of deep, programmatic extraction possible. Without that openness, a dataset of this quality and variety simply could not exist.

A pipeline to extract clean, border-free comic panel artwork from Pepper & Carrot, packaged as a multi-variant dataset for ML training.

The goal: teach a U-Net model to remove comic panel borders from manhwa-style pages — handling white borders, black borders, JPEG compression artifacts, and inked frame lines as input, with clean transparent-border artwork as the target.

---

## Pipeline

```
download_chapters.py  →  extract_kra.py  →  process_kra.py  →  synthesize_dataset.py
   fetch source            unzip .kra         detect & remove        generate 9 ML
   .kra files              archives           border layer           training variants
```

![Before and after border removal](assets/pipeline.png)

---

## Dataset Variants

Each processed page produces **9 variants** stored as `data/synthesized/<episode>/<variant>/<page>.png`. All input variants map to the same `transparent/` target — the clean artwork with borders removed.

![All 9 variants](assets/variants_grid.png)

*Animated preview cycling through all variants:*

![Variants demo](assets/variants_demo.gif)

### Variant reference

| Folder | Role | Description |
|---|---|---|
| `transparent/` | **Target** | Clean artwork, borders fully transparent |
| `white/` | Input | Raw merged image from the KRA file — white borders intact |
| `black/` | Input | Artwork composited on solid black background |
| `framed/` | Input | White background + 1px black outline at each panel edge |
| `jpeg/` | Input | White borders + heavy JPEG compression (quality 15) |
| `framed_jpeg/` | Input | White bg + 1px frame + JPEG — hardest case, all artifacts combined |
| `transparent_framed/` | Input | Transparent + 1px black outline at each panel edge |
| `transparent_jpeg/` | Input | Transparent + JPEG artifacts on RGB channels, alpha preserved |
| `transparent_framed_jpeg/` | Input | Transparent + 1px frame + JPEG — frame loses true black, as in real manhwa scans |

#### Why so many variants?

Real-world manhwa chapters are distributed as JPEG images where black frame lines are never true `#000000` — JPEG compression bleeds colour into adjacent pixels. A model trained only on clean white-border inputs will fail on these. The matrix of variants covers every combination of background style, frame presence, and JPEG degradation, forcing the model to learn the semantic concept "this is a border" rather than memorising a specific colour value.

---

## Version history & decisions

Each version reflects a specific problem encountered and the decision made to solve it.
Version scheme: `v1.X.Y` — `X` is the feature group, `Y` is the iteration within it.

### v1.0.0 · Initial setup
Download pipeline (`download_chapters.py`) and license attribution scraper (`create_licenses.py`). Established the project structure and `.gitignore`.

### v1.1.0 – v1.1.1 · KRA border extraction
First working extraction from `.kra` ZIP archives — parse `maindoc.xml`, decode Krita tile data, apply border mask to `mergedimage.png`. Added scored layer selection (prefers `shapelayer` over `paintlayer`), SVG rendering via cairosvg, and batch episode processing.

Established the three border layer types present in Krita files: `paintlayer` (raster white stroke), `shapelayer` (SVG vector), and `grouplayer` (composited children).

### v1.2.0 – v1.2.2 · Code structure
Split monolithic script into `extract_kra.py` and `process_kra.py`. Unified all data paths under `data/`. Renamed report output directory to `reports/`.

### v1.3.0 · LZF prefix fix
Krita tile data uses LZF compression with a 1-byte version prefix before the compressed payload. Feeding the full buffer to the decompressor caused failures across 19 files. Fix: skip byte 0 before decompressing.

### v1.3.1 · Grouplayer border support + `--retry-errors`
Some episodes wrap the border layer in a group. Added `build_group_mask` which composites all descendant paintlayers and thresholds on alpha (group border strokes are black, not white — so the white-pixel check used for raster layers would return empty masks). Added `--retry-errors` flag to reprocess only failed files without rerunning the full ~18-minute pipeline.

### v1.3.2 · Skip empty border masks
E28P00 has an SVG border layer with coordinates in global document space (Y=7334–27067) far outside the 795px canvas viewport. The resulting mask has zero coverage. Rather than raising an error, treat it as skipped — consistent with all other P00 (cover) files which have no border layer.

### v1.4.0 – v1.4.1 · Blacklist + synthesize_dataset
E03P02 has unclipped artwork bleed: the flat merged image exposes artwork from adjacent panels in the gutter bands. This is unfixable without re-rendering individual panel layer groups from the KRA source. Added `BLACKLISTED` dict in `process_kra.py` — blacklisted pages are skipped and any existing output PNG is deleted.

Introduced `synthesize_dataset.py` to generate the multi-variant training set. All scripts moved to `src/`.

### v1.4.2 · Complete input matrix
Added `framed_jpeg` and the three `transparent_*` variants to cover every combination of background, frame, and JPEG degradation. Added tqdm progress bar.

### v1.5.0 · README and visual assets
README with pipeline overview, variant table, version history, and usage instructions. Visual assets: `pipeline.png` (before/after), `variants_demo.gif` (animated), `variants_grid.png` (3×3 grid). Special thanks to David Revoy.

### v1.5.1 – v1.5.3 · Asset refinements
Single panel per frame (first panel detected from transparent alpha). GIF zoom inset moved to bottom-right corner, source zone straddling the artwork/border boundary. Variants grid updated with per-cell zoom insets. `make_assets.py` moved to `src/`. Language stats fixed via `.gitattributes`.

---

## How to run

```bash
pip install -r requirements.txt

# 1. Download source files
python3 src/download_chapters.py

# 2. Extract .kra archives
python3 src/extract_kra.py

# 3. Process: detect and remove border layers
python3 src/process_kra.py

# 4. Generate training variants
python3 src/synthesize_dataset.py all
```

To reprocess only files that errored:
```bash
python3 src/process_kra.py --retry-errors
```

To synthesize a specific episode:
```bash
python3 src/synthesize_dataset.py ep03
```

---

## Output structure

```
data/
  processed_png/
    ep01_Potion-of-Flight/
      E01P01.png          ← clean transparent output
      ...
  synthesized/
    ep01_Potion-of-Flight/
      transparent/E01P01.png
      white/E01P01.png
      black/E01P01.png
      framed/E01P01.png
      jpeg/E01P01.png
      framed_jpeg/E01P01.png
      transparent_framed/E01P01.png
      transparent_jpeg/E01P01.png
      transparent_framed_jpeg/E01P01.png
```

All variant folders map 1:1 by filename to `transparent/`, making dataloader pairing trivial:
```python
input_path  = Path("data/synthesized/ep01_Potion-of-Flight/framed_jpeg/E01P01.png")
target_path = Path("data/synthesized/ep01_Potion-of-Flight/transparent/E01P01.png")
```

---

## License

**Pipeline code** (all `.py` files) — [MIT License](LICENSE) © 2026 Devids Kronbergs.

**Artwork and generated dataset** — derived from [Pepper & Carrot](https://www.peppercarrot.com/) by [David Revoy](https://www.davidrevoy.com/), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Attribution: **"Pepper & Carrot" by David Revoy**.
