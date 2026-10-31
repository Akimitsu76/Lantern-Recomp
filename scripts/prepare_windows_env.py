"""Export the launcher's real Windows compiler environment to GitHub Actions."""
from pathlib import Path
import argparse
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from native_port.native_build import toolchain
from native_port.workspace import Workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--github-env', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('This helper requires Windows.')
    _, _, _, environment = toolchain(ROOT, Workspace(ROOT / '.aster', ROOT))
    allowed = {'PATH', 'INCLUDE', 'LIB', 'LIBPATH', 'VCTOOLSINSTALLDIR', 'VCINSTALLDIR',
               'VSINSTALLDIR', 'WINDOWSSDKDIR', 'WINDOWSSDKVERSION', 'WINDOWSSDKBINPATH',
               'WINDOWSSDKVERBINPATH', 'UCRTVERSION', 'UNIVERSALCRTSDKDIR',
               'VSCMD_ARG_TGT_ARCH', 'VSCMD_ARG_HOST_ARCH', 'VSCMD_VER', 'VCTOOLSVERSION',
               'VSCMD_SKIP_SENDTELEMETRY'}
    exported = []
    with args.github_env.open('a', encoding='utf8', newline='\n') as output:
        for name in sorted(allowed):
            if name in environment:
                value = environment[name]
                if '\r' in value or '\n' in value:
                    raise ValueError('Unexpected multiline compiler environment')
                output.write(name + '=' + value + '\n')
                exported.append(name)
    print('Compiler environment prepared: ' + ', '.join(exported))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
