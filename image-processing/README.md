# Image processing

Code for processing the microscopy images acquired from flat-agar 96-well plates. The main entry point is [`extract_focused_slices.py`](extract_focused_slices.py), a CLI that selects the sharpest brightfield slice from each ND2 z-stack and exports it (with an optional matching fluorescence slice) as an 8-bit image. The [`extract-focused-demo.ipynb`](extract-focused-demo.ipynb) notebook walks through the same steps on a single example well.

## Data

Images are multichannel z-stacks, acquired on a Nikon Ni-E upright widefield fluorescence microscope fitted with a Photometrics Kinetix sCMOS camera (6.5 μm pixel size). We used either a 2× objective, which captures a full well in a single frame, or a 4× objective with 2×2 tiling. Plates were imaged once per day using the brightfield and TRITC filtersets, and each acquisition is saved as an ND2 file.

A few example wells are included under [`data/`](data), organized by acquisition timestamp (`YYYYMMDD_HHMMSS_fff/`). The table below maps each figure panel in the [pub](https://doi.org/10.57844/arcadia-h01v-2nxt) to its source file:

| Figure panel | File |
| --- | --- |
| Fig 2 — worm-plates A | `20260605_152922_245/WellC06_Channelbrightfield,TRITC_Seq0021.nd2` |
| Fig 2 — worm-plates B | `20260605_152922_245/WellH03_Channelbrightfield,TRITC_Seq0061.nd2` |
| Fig 3 — optimization C, day 0 | `20260602_115455_450/WellH03_Channelbrightfield,TRITC_Seq0061.nd2` |
| Fig 3 — optimization C, day 1 | `20260603_142758_017/WellH03_Channelbrightfield,TRITC_Seq0061.nd2` |
| Fig 3 — optimization C, day 3 | `20260605_152922_245/WellH03_Channelbrightfield,TRITC_Seq0061.nd2` |

## Script

`extract_focused_slices.py` batch-processes a directory of ND2 z-stacks. For each file it:

1. **Loads** the brightfield z-stack as a `(Z, Y, X)` array via [`arcadia-microscopy-tools`](https://github.com/Arcadia-Science/arcadia-microscopy-tools).
2. **Restricts** attention to a circular ROI centered on the image — the well — so that focus scoring ignores the surrounding plastic and out-of-well artifacts.
3. **Scores focus** on each slice by summing [Sobel](https://scikit-image.org/docs/stable/api/skimage.filters.html#skimage.filters.sobel) edge energy inside the ROI, and picks the slice with the greatest edge energy as the in-focus plane. The stack is downsampled before edge detection to keep this fast.
4. **Rescales** the chosen slice by percentile and saves it as an 8-bit image. If requested, the fluorescence slice at the same z-index is exported alongside it.

See [`extract-focused-demo.ipynb`](extract-focused-demo.ipynb) to watch each of these steps run on one example well, including the per-slice edge-energy curve used to locate the focus peak.

### Usage

Run from the repository root (the environment is managed with [uv](https://docs.astral.sh/uv/); see the [top-level README](../README.md) for setup):

```bash
uv run python image-processing/extract_focused_slices.py /path/to/nd2_dir \
    --output-dir /path/to/output
```

By default the script searches `input_dir` recursively for `*.nd2` files, uses the `BRIGHTFIELD` channel to detect and export focus, writes JPEGs to `<input_dir>/focused/`, and skips files whose output already exists. To also export the matching fluorescence slice:

```bash
uv run python image-processing/extract_focused_slices.py /path/to/nd2_dir \
    --output-dir /path/to/output --save-fluorescence
```

Fluorescence slices are written to a `fluorescence/` subdirectory of the output directory.

### Options

| Option | Default | Description |
| --- | --- | --- |
| `input_dir` | *(required)* | Directory to search for ND2 files. |
| `-o`, `--output-dir` | `<input_dir>/focused` | Directory to write focused images to. |
| `--channel` | `BRIGHTFIELD` | Channel used to determine focus and to export. |
| `--save-fluorescence` | off | Also export the fluorescence slice at the same focus index. |
| `--fluorescence-channel` | `TRITC` | Fluorescence channel to export when `--save-fluorescence` is set. |
| `--pattern` | `*.nd2` | Glob pattern for input files. |
| `--no-recursive` | off | Do not search subdirectories. |
| `--radius-margin` | `250` | Pixels subtracted from the half-min image dimension to set the ROI radius. |
| `--edge-downsample` | `4` | Downsample factor applied before edge detection for focus scoring. |
| `--percentile-range LOW HIGH` | `0.1 99.9` | Percentile range for intensity rescaling. |
| `--format` | `jpg` | Output image format/extension. |
| `--overwrite` | off | Overwrite existing output files instead of skipping them. |
| `--dry-run` | off | Detect focus and report actions without writing any files. |

Run with `--help` to see this list at the command line.
