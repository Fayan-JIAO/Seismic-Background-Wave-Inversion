from __future__ import annotations

import argparse
import os
from pathlib import Path

import segyio


COMPONENTS = (
    ("X", 0),
    ("Y", 1),
    ("Z", 2),
)


def find_sgy_files(input_dir: Path) -> list[Path]:
    suffixes = {".sgy", ".segy"}
    return sorted(
        path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in suffixes
    )


def make_spec(source: segyio.SegyFile, trace_count: int) -> segyio.spec:
    spec = segyio.spec()
    spec.samples = source.samples
    spec.format = int(source.format)
    spec.tracecount = trace_count
    spec.endian = "big"
    return spec


def write_component(
    source: segyio.SegyFile,
    source_path: Path,
    output_path: Path,
    component_index: int,
    component_trace_count: int,
) -> None:
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    spec = make_spec(source, component_trace_count)

    try:
        with segyio.create(temp_path, spec) as dst:
            dst.text[0] = source.text[0]
            dst.bin = source.bin
            dst.bin[segyio.BinField.Traces] = component_trace_count

            for output_trace_index, source_trace_index in enumerate(
                range(component_index, source.tracecount, 3)
            ):
                dst.header[output_trace_index] = source.header[source_trace_index]
                dst.trace[output_trace_index] = source.trace[source_trace_index]

            dst.flush()

        os.replace(temp_path, output_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise RuntimeError(
            f"Failed while writing {output_path.name} from {source_path.name}."
        )


def split_file(
    source_path: Path,
    output_root: Path,
    line_name: str,
    expected_traces: int | None,
    overwrite: bool,
) -> tuple[Path, Path, Path]:
    outputs = {
        label: output_root / f"{label}_data" / line_name / f"{label}_{source_path.name}"
        for label, _ in COMPONENTS
    }

    for path in outputs.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} already exists. Use --overwrite to replace it.")

    with segyio.open(
        source_path,
        mode="r",
        strict=False,
        ignore_geometry=True,
        endian="big",
    ) as source:
        trace_count = source.tracecount
        if expected_traces is not None and trace_count != expected_traces:
            raise ValueError(
                f"{source_path.name}: expected {expected_traces} traces, found {trace_count}."
            )
        if trace_count % 3 != 0:
            raise ValueError(f"{source_path.name}: trace count {trace_count} is not divisible by 3.")

        component_trace_count = trace_count // 3
        for label, component_index in COMPONENTS:
            write_component(
                source=source,
                source_path=source_path,
                output_path=outputs[label],
                component_index=component_index,
                component_trace_count=component_trace_count,
            )

    return outputs["X"], outputs["Y"], outputs["Z"]


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Split XYZ-interleaved SEG-Y files into X, Y, and Z SEG-Y files."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=repo_root / "data" / "5m_1",
        help="Directory containing source SGY/SEGY files.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=repo_root / "data",
        help="Directory where X_data, Y_data, and Z_data will be created.",
    )
    parser.add_argument(
        "--line-name",
        default=None,
        help="Survey line name used as the subdirectory under X_data/Y_data/Z_data. "
        "Defaults to the input directory name.",
    )
    parser.add_argument(
        "--expected-traces",
        type=int,
        default=180,
        help="Expected trace count per input file. Use 0 to allow any count divisible by 3.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace output files if they already exist.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only list files that would be processed.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input_dir.resolve()
    output_root = args.output_root.resolve()
    line_name = args.line_name or input_dir.name
    expected_traces = None if args.expected_traces == 0 else args.expected_traces

    if not input_dir.is_dir():
        raise NotADirectoryError(f"Input directory does not exist: {input_dir}")

    source_files = find_sgy_files(input_dir)
    if not source_files:
        raise FileNotFoundError(f"No .sgy or .segy files found in {input_dir}")

    print(f"Input directory: {input_dir}")
    print(f"Found {len(source_files)} SEG-Y file(s).")
    print(f"Output root: {output_root}")
    print(f"Line name: {line_name}")

    if args.dry_run:
        for source_path in source_files:
            print(f"DRY RUN: {source_path.name}")
        return 0

    for source_path in source_files:
        x_path, y_path, z_path = split_file(
            source_path=source_path,
            output_root=output_root,
            line_name=line_name,
            expected_traces=expected_traces,
            overwrite=args.overwrite,
        )
        print(f"OK: {source_path.name} -> {x_path.name}, {y_path.name}, {z_path.name}")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
