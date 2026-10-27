#!/usr/bin/env python3
"""Build public SDK graphics only, without requiring any game dump or XEX."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_port.native_build import toolchain
from native_port.spatial_sdk import build_spatial_sdk
from native_port.tasks import Cancellation
from native_port.workspace import Workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--allow-download', action='store_true')
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--resume-base', type=Path, help='Resume a verified isolated SDK build without moving its CMake tree')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    work = Workspace(args.workspace / ".aster", args.workspace)
    prefix = build_spatial_sdk(root, work, toolchain(root, work), Cancellation(),
                               lambda event: print(json.dumps(event, ensure_ascii=False), flush=True),
                               args.allow_download, args.jobs, args.resume_base)
    print('SPATIAL_SDK_PREFIX=' + str(prefix), flush=True)


if __name__ == '__main__':
    main()
