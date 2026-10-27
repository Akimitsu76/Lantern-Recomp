#!/usr/bin/env python3
"""Convert one explicitly captured original texture to DDS/PNG for local review.

Not an HD texture pack generator or runtime replacement system. Uses the pinned
SDK's offline C++ untile helper, then Pillow solely for standard DDS decoding.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def validate_metadata(meta: dict, raw: bytes) -> None:
    if meta.get("schema") != 1 or meta.get("purpose") != "inspection-only":
        raise ValueError("Not a supported inspection capture")
    if meta.get("gpu_written_pages") is not False:
        raise ValueError("GPU-authored contents are not eligible for this inspector")
    for key in ("width", "height", "base_row_pitch_bytes", "format", "endian", "base_size"):
        if type(meta.get(key)) is not int:
            raise ValueError(f"Invalid {key}")
    if not 64 <= meta["width"] <= 2048 or not 64 <= meta["height"] <= 2048:
        raise ValueError("Unsupported capture dimensions")
    if meta["format"] not in (18, 20) or meta["endian"] not in range(4):
        raise ValueError("Only original DXT1/DXT5 captures are supported")
    if type(meta.get("tiled")) is not bool or meta.get("packed_level") == 0:
        raise ValueError("Unsupported base layout")
    if len(raw) != meta["base_size"] or not 0 < len(raw) <= 16 * 1024 * 1024:
        raise ValueError("Raw capture length mismatch")


def convert_capture(metadata: Path, helper: Path, output: Path, xex: Path) -> Path:
    from PIL import Image

    metadata = metadata.resolve(strict=True)
    helper = helper.resolve(strict=True)
    xex = xex.resolve(strict=True)
    if metadata.suffix != ".json":
        raise ValueError("Expected the capture JSON metadata")
    meta = json.loads(metadata.read_text(encoding="utf-8"))
    raw_path = metadata.with_suffix(".base.bin")
    raw = raw_path.read_bytes()
    validate_metadata(meta, raw)
    if output.exists():
        raise ValueError("Use a new output directory to preserve previous evidence")
    output.mkdir(parents=True)
    dds = output / "original.dds"
    cmd = [str(helper), str(raw_path), str(meta["width"]), str(meta["height"]),
           str(meta["base_row_pitch_bytes"]), str(meta["format"]), str(meta["endian"]),
           str(int(meta["tiled"])), str(dds)]
    subprocess.run(cmd, check=True)
    with Image.open(dds) as image:
        rgba = image.convert("RGBA")
        if rgba.size != (meta["width"], meta["height"]):
            raise ValueError("DDS dimensions mismatch")
        pixels = rgba.tobytes()
        rgba.save(output / "original.png")
    # Canonical original pixel identity excludes guest pages, tiling and padding.
    identity = hashlib.sha256(b"aster-texture-rgba8-v1\0" +
                              struct.pack("<II", *rgba.size) + pixels).hexdigest()
    with xex.open("rb") as stream:
        xex_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {
        "schema": 1, "status": "original-inspection-only",
        "classification": "unknown-review-required", "immutability_proven": False,
        "color_space": "unknown", "alpha_semantics": "unknown",
        "canonical_rgba8_sha256": identity,
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "dds_sha256": hashlib.sha256(dds.read_bytes()).hexdigest(),
        "game_xex_sha256": xex_hash, "capture_metadata": meta,
        "provenance_limit": "XEX hash records the operator-selected source; material identity is not proven.",
        "enhancement": None, "runtime_replacement": False,
    }
    manifest = output / "inspection.json"
    manifest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--helper", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--xex", required=True, type=Path,
                        help="Operator-selected original XEX, hashed for local provenance")
    args = parser.parse_args()
    print(convert_capture(args.metadata, args.helper, args.output, args.xex))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
