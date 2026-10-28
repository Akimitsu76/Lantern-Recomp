#!/usr/bin/env python3
"""Build the launcher's Linux Tk9/Xft overlay without installing on the host.

Pinned official Tcl/Tk archives and Ubuntu 18.04 packages form a private glibc
2.27 sysroot. Only Tk and its non-glibc runtime closure enter the output. This
is a launcher build dependency, never a dependency downloaded by players.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request

GLIBC = {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2',
         'librt.so.1', 'libresolv.so.2', 'ld-linux-x86-64.so.2'}
TK_NAME = 'libtcl9tk9.0.so'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(item, path, offline):
    if path.is_file() and digest(path) == item['sha256']:
        return
    if offline:
        raise ValueError('Missing or invalid cached input: ' + str(path))
    with urllib.request.urlopen(item['url'], timeout=60) as response:
        raw = response.read(32 * 1024 * 1024 + 1)
    if len(raw) > 32 * 1024 * 1024 or hashlib.sha256(raw).hexdigest() != item['sha256']:
        raise ValueError('Input failed SHA256: ' + item['url'])
    if 'bytes' in item and len(raw) != item['bytes']:
        raise ValueError('Input failed size: ' + item['url'])
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(raw)
    temporary.replace(path)


def unpack(raw, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as archive:
        for member in archive:
            # Ubuntu's absolute symlinks must remain inside our private sysroot.
            if member.issym() and member.linkname.startswith('/'):
                member.linkname = os.path.relpath(destination / member.linkname.lstrip('/'),
                                                   (destination / member.name).parent)
            archive.extract(member, destination, filter='data')


def elf(path, flag):
    return subprocess.check_output(['readelf', flag, str(path)], text=True)


def audit_elf(path):
    versions = [tuple(map(int, v.split('.'))) for v in re.findall(r'GLIBC_([0-9.]+)', elf(path, '-V'))]
    if versions and max(versions) > (2, 27):
        raise ValueError('Library exceeds glibc2.27: ' + str(path))
    dynamic = elf(path, '-d')
    if re.search(r'\((?:RPATH|RUNPATH)\)', dynamic):
        raise ValueError('Runtime library embeds search path: ' + str(path))
    return re.findall(r'\(NEEDED\).*\[([^]]+)\]', dynamic)


def stage(work, output, inputs):
    sysroot = work / 'sysroot'
    if output.exists():
        # Only remove a previous output produced by this helper.
        if not (output / 'TK_RUNTIME.json').is_file():
            raise ValueError('Output already exists without TK_RUNTIME.json')
        shutil.rmtree(output)
    (output / 'lib').mkdir(parents=True)
    candidates = {}
    for folder in ('usr/lib/x86_64-linux-gnu', 'lib/x86_64-linux-gnu'):
        for path in (sysroot / folder).glob('*.so*'):
            if path.is_file():
                candidates[path.name] = path
    pending = [(TK_NAME, work / 'build/tk' / TK_NAME)]
    done = set()
    while pending:
        name, source = pending.pop()
        if name in done or name in GLIBC:
            continue
        if not source.resolve().is_relative_to(work.resolve()):
            raise ValueError('Dependency escapes private build: ' + str(source))
        needed = audit_elf(source)
        target = output / 'lib' / name
        shutil.copyfile(source, target)
        done.add(name)
        for dependency in needed:
            if dependency not in GLIBC and dependency not in done:
                if dependency not in candidates:
                    raise ValueError('Dependency absent from sysroot: ' + dependency)
                pending.append((dependency, candidates[dependency]))
    if not {'libXft.so.2', 'libfontconfig.so.1'} <= done:
        raise ValueError('Tk was built without Xft')
    shutil.copytree(work / 'source/tk-core-9-0-4/library', output / 'tk_data')
    shutil.copyfile(Path(__file__).with_name('launcher_fontconfig.conf'), output / 'launcher_fontconfig.conf')
    licenses = output / 'LICENSES'
    licenses.mkdir()
    for name in ('tcl', 'tk'):
        shutil.copyfile(work / f'source/{name}-core-9-0-4/license.terms', licenses / f'{name}-license.terms')
    for path in (sysroot / 'usr/share/doc').glob('*/copyright'):
        if path.is_file() and path.resolve().is_relative_to(sysroot):
            shutil.copyfile(path, licenses / (path.parent.name + '-copyright'))
    manifest = {'schema': 1, 'tk': '9.0.4', 'abi': 'Tcl9', 'xft': True,
                'glibc_ceiling': '2.27', 'inputs': inputs,
                'files': {p.relative_to(output).as_posix(): digest(p)
                          for p in sorted(output.rglob('*')) if p.is_file()}}
    (output / 'TK_RUNTIME.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return manifest


def build(work, output, inputs, jobs, offline):
    downloads = work / 'downloads'
    downloads.mkdir(parents=True, exist_ok=True)
    source = work / 'source'
    source.mkdir(exist_ok=True)
    for name, item in inputs['sources'].items():
        archive = downloads / f'{name}9.0.4.tar.gz'
        fetch(item, archive, offline)
        if not (source / f'{name}-core-9-0-4').is_dir():
            unpack(archive.read_bytes(), source)
    sysroot = work / 'sysroot'
    for item in inputs['packages'].values():
        archive = downloads / item['url'].rsplit('/', 1)[-1]
        fetch(item, archive, offline)
        members = subprocess.check_output(['ar', 't', str(archive)], text=True).splitlines()
        data = next(m for m in members if m.startswith('data.tar'))
        unpack(subprocess.check_output(['ar', 'p', str(archive), data]), sysroot)
    env = os.environ.copy()
    env.update(CC='clang', CPP='clang -E', CFLAGS=f'--sysroot={sysroot} -O2 -fPIC',
               LDFLAGS=f'--sysroot={sysroot} -fuse-ld=lld -static-libgcc -L{sysroot}/usr/lib/x86_64-linux-gnu -L{sysroot}/lib/x86_64-linux-gnu',
               PKG_CONFIG_SYSROOT_DIR=str(sysroot), PKG_CONFIG_PATH='',
               PKG_CONFIG_LIBDIR=f'{sysroot}/usr/lib/x86_64-linux-gnu/pkgconfig:{sysroot}/usr/share/pkgconfig')
    def run(name, command, directory):
        with (work / 'build' / (name + '.log')).open('w') as log:
            subprocess.run(command, cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    for name in ('tcl', 'tk'):
        directory = work / 'build' / name
        directory.mkdir(parents=True, exist_ok=True)
        command = [str(source / f'{name}-core-9-0-4/unix/configure'), '--prefix=' + str(output), '--disable-rpath']
        if name == 'tcl':
            command += ['--disable-shared', '--disable-load']
            target = 'libtclstub.a'
        else:
            command += ['--with-tcl=' + str(work / 'build/tcl'), '--enable-xft', '--disable-xss', '--disable-zipfs']
            target = TK_NAME
        run(name + '-configure', command, directory)
        # Relink even after configuration changes; preserve existing object cache.
        (directory / target).unlink(missing_ok=True)
        make = ['make', '-j' + str(jobs), target]
        if name == 'tk':
            make += ['TK_SHLIB_LD_EXTRAS=-Wl,-soname,' + TK_NAME]
        run(name + '-make', make, directory)
    return stage(work, output, inputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=Path('.aster/tools/launcher-tk-xft'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    if os.name != 'posix' or not 1 <= args.jobs <= 16:
        parser.error('Linux build with 1..16 jobs required')
    work = args.work.resolve()
    output = (args.output or work / 'runtime').resolve()
    if output == work or work.is_relative_to(output):
        parser.error('Output cannot contain the build directory')
    inputs = json.loads(Path(__file__).with_name('launcher_tk_inputs.json').read_text())
    manifest = build(work, output, inputs, args.jobs, args.offline)
    print(json.dumps({'runtime': str(output), 'libraries': len(list((output / 'lib').iterdir())),
                      'tk': manifest['tk'], 'xft': True, 'glibc_ceiling': '2.27'}))


if __name__ == '__main__':
    main()
