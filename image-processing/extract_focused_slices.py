"""Extract the best-focus slice from brightfield ND2 z-stacks.

For each ND2 file found under an input directory this script:

1. Loads the brightfield z-stack.
2. Restricts attention to a circular ROI centered on the image (the well).
3. Picks the in-focus z-slice as the one with the greatest Sobel edge energy.
4. Rescales the focused slice by percentile and saves it as an 8-bit image.

Optionally, the fluorescence slice at the same z-index can also be exported.

Example:

    uv run python image-processing/extract_focused_slices.py /path/to/nd2_dir \
        --output-dir /path/to/output --save-fluorescence
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import skimage as ski
from arcadia_microscopy_tools import ImageOperation, MicroscopyImage, Pipeline
from arcadia_microscopy_tools.operations import rescale_by_percentile
from tqdm.auto import tqdm


def downsample(arr: np.ndarray, factor: int) -> np.ndarray:
    """Strided subsampling of the last two axes."""
    return arr[..., ::factor, ::factor]


def apply_circular_mask(
    intensities: np.ndarray,
    cy: float,
    cx: float,
    radius: float,
    padding: int = 0,
) -> np.ndarray:
    """Mask pixels outside a circular ROI to NaN and crop to its bounding box.

    Args:
        intensities: Array whose last two axes are (Y, X).
        cy, cx: Circle center in pixels.
        radius: Circle radius in pixels.
        padding: Extra pixels beyond the circle bounding box on each side.
    """
    h, w = intensities.shape[-2:]
    mask = np.zeros((h, w), dtype=bool)
    rr, cc = ski.draw.disk((cy, cx), radius, shape=(h, w))
    mask[rr, cc] = True

    out = intensities.astype(np.float32, copy=True)
    out[..., ~mask] = np.nan

    r0 = int(max(cy - radius - padding, 0))
    r1 = int(min(cy + radius + padding + 1, h))
    c0 = int(max(cx - radius - padding, 0))
    c1 = int(min(cx + radius + padding + 1, w))
    return out[..., r0:r1, c0:c1]


def find_focus_index(
    intensities: np.ndarray,
    cy: float,
    cx: float,
    radius: float,
    edge_downsample: int,
) -> int:
    """Return the z-index of the sharpest slice within the circular ROI."""
    edge = Pipeline(
        [
            ImageOperation(downsample, factor=edge_downsample),
            ImageOperation(ski.filters.sobel),
        ],
        parallel=True,
    )
    masked = apply_circular_mask(intensities, cy, cx, radius)
    edges = edge(masked)
    edges_sum = np.nansum(edges, axis=(1, 2))
    return int(edges_sum.argmax())


def to_ubyte(image: np.ndarray) -> np.ndarray:
    """Rescale a float image to the full 0-255 uint8 range."""
    return ski.exposure.rescale_intensity(image, out_range=(0, 255)).astype(np.uint8)


def find_nd2_files(input_dir: Path, pattern: str, recursive: bool) -> list[Path]:
    globber = input_dir.rglob if recursive else input_dir.glob
    return sorted(globber(pattern))


def build_output_name(nd2_path: Path, suffix: str) -> str:
    """Build the output filename for an ND2 file: its stem plus the given suffix."""
    return f"{nd2_path.stem}{suffix}"


def process_file(
    nd2_path: Path,
    output_dir: Path,
    args: argparse.Namespace,
) -> str | None:
    """Process a single ND2 file. Returns a status string for logging, or None on skip."""
    preprocess = Pipeline(
        [ImageOperation(rescale_by_percentile, percentile_range=tuple(args.percentile_range))]
    )
    ext = args.format if args.format.startswith(".") else f".{args.format}"

    bf_name = build_output_name(nd2_path, ext)
    bf_out = output_dir / bf_name
    fl_out = None
    if args.save_fluorescence:
        fl_dir = output_dir / "fluorescence"
        fl_out = fl_dir / build_output_name(nd2_path, ext)

    if not args.overwrite and bf_out.exists() and (fl_out is None or fl_out.exists()):
        return f"skip (exists): {bf_out.name}"

    zstack = MicroscopyImage.from_nd2_path(nd2_path)
    intensities = zstack.get_channel_intensities(args.channel)

    cy = intensities.shape[1] // 2
    cx = intensities.shape[2] // 2
    radius = args.radius
    max_radius = min(intensities.shape[1:3]) // 2
    if radius > max_radius:
        return f"skip (radius {radius} > max {max_radius} for image size): {nd2_path.name}"

    focus_index = find_focus_index(intensities, cy, cx, radius, args.edge_downsample)

    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        focused = preprocess(intensities[focus_index])
        ski.io.imsave(bf_out, to_ubyte(focused))

        if fl_out is not None:
            fluor = zstack.get_channel_intensities(args.fluorescence_channel)
            fl_focused = preprocess(fluor[focus_index])
            fl_out.parent.mkdir(parents=True, exist_ok=True)
            ski.io.imsave(fl_out, to_ubyte(fl_focused))

    return f"z={focus_index:>3} -> {bf_out.name}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_dir",
        type=Path,
        help="Directory to search for ND2 files.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write focused images to (default: <input_dir>/focused).",
    )
    parser.add_argument(
        "--channel",
        default="BRIGHTFIELD",
        help="Channel used to determine focus and to export (default: BRIGHTFIELD).",
    )
    parser.add_argument(
        "--save-fluorescence",
        action="store_true",
        help="Also export the fluorescence slice at the same focus index.",
    )
    parser.add_argument(
        "--fluorescence-channel",
        default="TRITC",
        help="Fluorescence channel to export when --save-fluorescence is set (default: TRITC).",
    )
    parser.add_argument(
        "--pattern",
        default="*.nd2",
        help="Glob pattern for input files (default: *.nd2).",
    )
    parser.add_argument(
        "--no-recursive",
        dest="recursive",
        action="store_false",
        help="Do not search subdirectories.",
    )
    parser.add_argument(
        "--radius",
        type=int,
        default=450,
        help="Radius in pixels of the circular well ROI, centered on the image "
        "(default: 450).",
    )
    parser.add_argument(
        "--edge-downsample",
        type=int,
        default=4,
        help="Downsample factor applied before edge detection for focus scoring (default: 4).",
    )
    parser.add_argument(
        "--percentile-range",
        type=float,
        nargs=2,
        metavar=("LOW", "HIGH"),
        default=[0.1, 99.9],
        help="Percentile range for intensity rescaling (default: 0.1 99.9).",
    )
    parser.add_argument(
        "--format",
        default="jpg",
        help="Output image format/extension (default: jpg).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files (default: skip files that already exist).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect focus and report actions without writing any files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.input_dir.is_dir():
        print(f"error: input directory not found: {args.input_dir}", file=sys.stderr)
        return 1

    if args.output_dir is None:
        args.output_dir = args.input_dir / "focused"

    nd2_files = find_nd2_files(args.input_dir, args.pattern, args.recursive)
    if not nd2_files:
        print(
            f"error: no files matching '{args.pattern}' in {args.input_dir} "
            f"({'recursive' if args.recursive else 'non-recursive'})",
            file=sys.stderr,
        )
        return 1

    print(f"Found {len(nd2_files)} ND2 file(s). Writing to {args.output_dir}")
    if args.dry_run:
        print("Dry run: no files will be written.")

    failures = 0
    for nd2_path in tqdm(nd2_files, unit="file"):
        try:
            status = process_file(nd2_path, args.output_dir, args)
            if status:
                tqdm.write(f"{nd2_path.name}: {status}")
        except Exception as exc:  # noqa: BLE001 - keep going through the batch
            failures += 1
            tqdm.write(f"{nd2_path.name}: FAILED ({exc})")

    if failures:
        print(f"Completed with {failures} failure(s).", file=sys.stderr)
        return 1
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
