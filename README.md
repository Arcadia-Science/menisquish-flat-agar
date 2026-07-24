# menisquish-flat-agar

This repository accompanies the pub ["Flat agar and optimized media enable high-throughput *C. elegans* imaging in 96-well plates"](https://doi.org/10.57844/arcadia-h01v-2nxt). It contains the automation and image-processing code used to prepare, seed, and image *C. elegans* in flat-agar 96-well plates: Opentrons liquid-handling protocols for bleach synchronization, OP50 agar spotting, and worm plating, plus a script for extracting the best-focus slice from brightfield z-stacks acquired on those plates.

## Installation and setup

This package uses [uv](https://docs.astral.sh/uv/) to manage dependencies. Clone the repo and sync the locked environment:

```bash
git clone https://github.com/Arcadia-Science/menisquish-flat-agar.git
cd menisquish-flat-agar
uv sync
```

This installs the image-processing dependencies. The Opentrons protocols are intentionally kept out of this environment because modern `opentrons` pins `numpy<2`, which conflicts with the `numpy>=2` required by the image-processing stack. Install them in a *separate* virtual environment — do not run this inside the `.venv` created by `uv sync` above (see [`opentrons/README.md`](opentrons/README.md)):

```bash
python -m venv .venv-opentrons
source .venv-opentrons/bin/activate  # on Windows: .venv-opentrons\Scripts\activate
pip install -r opentrons/requirements.txt
```

For running the protocols on a robot, uploading custom labware, and installing the Opentrons App, refer to the [Opentrons documentation](https://docs.opentrons.com/) — in particular the [Python Protocol API reference](https://docs.opentrons.com/v2/).

## Overview

### Description of the folder structure

- `opentrons/` — Opentrons liquid-handling protocols and their custom labware definitions. See [`opentrons/README.md`](opentrons/README.md) for robot models, API levels, labware upload instructions, and per-protocol notes.
  - `bowie_celegans_bleach_sync_var-col_v1.py` — Flex 96-channel bleach synchronization across a variable number of worm columns.
  - `hopsy_p20multi_op50_agar_spotting_centrifuge_v4.py` — OT-2 P20 8-channel spotting of OP50 bacterial suspension onto agar columns.
  - `hopsy_p20multi_worm_plating_centrifuge_v4.py` — OT-2 P20 8-channel transfer of a worm trace from a deep-well plate to a flat-agar plate.
  - `labware/` — Custom labware JSON files to upload to the Opentrons App before running the protocols.
- `image-processing/` — Python code for processing microscopy images acquired from the plates.
  - `extract_focused_slices.py` — CLI that, for each ND2 z-stack, selects the sharpest brightfield slice within a circular well ROI and exports it (and optionally the matching fluorescence slice) as an 8-bit image.

### Methods

1. **Bleach synchronization** — Gravid adults are bleach-synchronized on an Opentrons Flex using all 96 channels at once, isolating age-matched embryos (`bowie_celegans_bleach_sync_var-col_v1.py`).
2. **OP50 spotting** — A 1 µL trace of OP50 bacterial suspension is spotted onto each column of a flat-agar 96-well plate with an OT-2 P20 8-channel pipette (`hopsy_p20multi_op50_agar_spotting_centrifuge_v4.py`).
3. **Worm plating** — A small trace of synchronized worms is transferred from a deep-well source plate onto the seeded agar plate (`hopsy_p20multi_worm_plating_centrifuge_v4.py`).
4. **Imaging** — Plates are imaged as brightfield (and optional fluorescence) z-stacks, saved as ND2 files.
5. **Focus extraction** — For each ND2 stack, the in-focus z-slice is chosen as the one with the greatest Sobel edge energy inside a circular ROI centered on the well, then rescaled by percentile and saved as an 8-bit image (`image-processing/extract_focused_slices.py`).

Example focus-extraction run:

```bash
uv run python image-processing/extract_focused_slices.py /path/to/nd2_dir \
    --output-dir /path/to/output
```

Run with `--help` to see all options (channel selection, ROI radius, edge-detection downsampling, percentile range, output format, dry run, and overwrite behavior).

### Compute Specifications

The image-processing script runs on a standard laptop or workstation and requires no GPU. It was developed and run on macOS with Python 3.12. Memory needs scale with the size of the ND2 z-stacks being loaded; a machine with 16 GB of RAM is comfortable for typical stacks. The Opentrons protocols run on the robots' onboard software (or the Opentrons App simulator) and have no additional compute requirements.

## Data

A few example ND2 z-stacks are checked into [`image-processing/data/`](image-processing/data) using [Git LFS](https://git-lfs.com), organized by acquisition timestamp and mapped to the pub's figure panels; see the [Data section of `image-processing/README.md`](image-processing/README.md#data) for the imaging setup and the file-to-figure-panel table. Install Git LFS once per machine (`git lfs install`) before cloning, or run `git lfs pull` in an existing clone, so the tracked files are fetched instead of left as pointers. Other ND2 files are excluded from version control via `.gitignore` to keep the repository small; `image-processing/data/**/*.nd2` is the sole exception.

## Contributing

See how we recognize [feedback and contributions to our code](https://github.com/Arcadia-Science/arcadia-software-handbook/blob/main/guides-and-standards/guide--credit-for-contributions.md).
