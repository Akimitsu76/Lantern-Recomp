"""Inspect and prepare known prerequisites through the OS package manager.

Inspection never installs anything. Installation is explicitly enabled by the
launcher's generation consent. Package names and installer IDs are fixed here;
dump metadata and downloaded text can never become an elevated command.
"""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from .errors import PortError
from .paths import external_env
from .tasks import Cancellation, run_process

LINUX_PACKAGES = {
    'arch': {'compiler': ('clang', 'gcc'), 'cmake': ('cmake',), 'ninja': ('ninja',),
             'git': ('git',), 'pkgconfig': ('pkgconf',), 'x11': ('libx11', 'libxext'),
             'wayland': ('wayland', 'wayland-protocols'), 'xkbcommon': ('libxkbcommon',),
             'alsa': ('alsa-lib',), 'pulse': ('libpulse',), 'pipewire': ('pipewire',),
             'udev': ('systemd-libs',), 'vulkan': ('vulkan-headers', 'vulkan-icd-loader')},
    'apt': {'compiler': ('clang-18', 'build-essential'), 'cmake': ('cmake',), 'ninja': ('ninja-build',),
            'git': ('git',), 'pkgconfig': ('pkg-config',), 'x11': ('libx11-dev', 'libxext-dev'),
            'wayland': ('libwayland-dev', 'wayland-protocols'), 'xkbcommon': ('libxkbcommon-dev',),
            'alsa': ('libasound2-dev',), 'pulse': ('libpulse-dev',), 'pipewire': ('libpipewire-0.3-dev',),
            'udev': ('libudev-dev',), 'vulkan': ('libvulkan-dev',)},
    'fedora': {'compiler': ('clang', 'gcc-c++'), 'cmake': ('cmake',), 'ninja': ('ninja-build',),
               'git': ('git',), 'pkgconfig': ('pkgconf-pkg-config',), 'x11': ('libX11-devel', 'libXext-devel'),
               'wayland': ('wayland-devel', 'wayland-protocols-devel'), 'xkbcommon': ('libxkbcommon-devel',),
               'alsa': ('alsa-lib-devel',), 'pulse': ('pulseaudio-libs-devel',), 'pipewire': ('pipewire-devel',),
               'udev': ('systemd-devel',), 'vulkan': ('vulkan-headers', 'vulkan-loader-devel')},
}
MODULES = {'x11': ('x11', 'xext'), 'wayland': ('wayland-client', 'wayland-protocols'),
           'xkbcommon': ('xkbcommon',), 'alsa': ('alsa',), 'pulse': ('libpulse',),
           'pipewire': ('libpipewire-0.3',), 'udev': ('libudev',), 'vulkan': ('vulkan',)}
VS_COMPONENTS = ('Microsoft.VisualStudio.Workload.VCTools',
                 'Microsoft.VisualStudio.Component.VC.Llvm.Clang',
                 'Microsoft.VisualStudio.Component.VC.Llvm.ClangToolset')


def distro_family(release):
    identifiers = {release.get('ID', ''), *release.get('ID_LIKE', '').split()}
    if identifiers & {'arch', 'cachyos', 'manjaro'}:
        return 'arch'
    if identifiers & {'fedora'}:
        return 'fedora'
    if identifiers & {'ubuntu'}:
        # Older Ubuntu repositories do not provide the compiler baseline.
        version = release.get('UBUNTU_CODENAME') or release.get('VERSION_ID', '')
        if version in ('jammy', 'focal', '22.04', '20.04'):
            raise PortError('DEPENDENCIES_OS', 'A preparação automática exige Ubuntu 24.04 ou mais recente.')
        return 'apt'
    if identifiers & {'debian'}:
        # Debian 13 provides clang-19; its package is selected separately.
        if release.get('VERSION_ID', '').split('.')[0] not in ('13', '14'):
            raise PortError('DEPENDENCIES_OS', 'A preparação automática exige Debian 13 ou mais recente.')
        return 'apt'
    raise PortError('DEPENDENCIES_OS', 'Distribuição sem plano de instalação validado. Nenhum pacote foi alterado.')


def read_release(path=Path('/etc/os-release')):
    values = {}
    for line in path.read_text(encoding='utf8').splitlines():
        key, separator, value = line.partition('=')
        if separator and key in ('ID', 'ID_LIKE', 'VERSION_ID', 'UBUNTU_CODENAME'):
            values[key] = value.strip().strip('"\'')
    return values


def package_plan(missing, family, release=None):
    """Return only fixed package names, rejecting unknown requirements."""
    if family not in LINUX_PACKAGES or any(key not in LINUX_PACKAGES[family] for key in missing):
        raise PortError('DEPENDENCIES_PLAN', 'Requisito sem instalador aprovado.')
    packages = sorted({p for key in missing for p in LINUX_PACKAGES[family][key]})
    if family == 'apt' and (release or {}).get('ID') == 'debian' and 'clang-18' in packages:
        packages[packages.index('clang-18')] = 'clang-19'
    return packages


def linux_install_command(packages, family, which=shutil.which, elevated=False):
    # Revalidate names against the fixed catalog even when called directly.
    if family not in LINUX_PACKAGES:
        raise PortError('DEPENDENCIES_PLAN', 'Gerenciador sem plano aprovado.')
    allowed = {p for values in LINUX_PACKAGES[family].values() for p in values} | {'clang-19'}
    if not packages or any(p not in allowed for p in packages):
        raise PortError('DEPENDENCIES_PLAN', 'Pacote não permitido no plano de instalação.')
    executable, arguments = {'arch': ('pacman', ['-S', '--needed', '--noconfirm']),
                             'apt': ('apt-get', ['install', '--yes', '--no-remove']),
                             'fedora': ('dnf', ['install', '--assumeyes'])}[family]
    manager = which(executable)
    if not manager:
        raise PortError('DEPENDENCIES_MANAGER', 'Gerenciador de pacotes do sistema indisponível.')
    command = [manager, *arguments, *packages]
    if not elevated:
        pkexec = which('pkexec')
        if not pkexec:
            raise PortError('DEPENDENCIES_ELEVATION', 'O sistema não oferece a autorização gráfica PolicyKit necessária para instalar dependências.')
        command.insert(0, pkexec)
    return command


def windows_install_commands(missing, which=shutil.which):
    ids = {'compiler': 'Microsoft.VisualStudio.2022.BuildTools', 'git': 'Git.Git',
           'cmake': 'Kitware.CMake', 'ninja': 'Ninja-build.Ninja',
           'runtime': 'Microsoft.VCRedist.2015+.x64'}
    if any(item not in ids for item in missing):
        raise PortError('DEPENDENCIES_PLAN', 'Requisito Windows sem instalador aprovado.')
    winget = which('winget')
    if not winget:
        raise PortError('DEPENDENCIES_MANAGER', 'O Instalador de Aplicativo/WinGet do Windows está indisponível. A preparação foi interrompida sem alterar o port.')
    commands = []
    for item in sorted(set(missing)):
        command = [winget, 'install', '--id', ids[item], '--exact', '--source', 'winget',
                   '--accept-source-agreements', '--accept-package-agreements', '--disable-interactivity']
        if item == 'compiler':
            options = '--passive --wait --norestart --includeRecommended ' + ' '.join('--add '+c for c in VS_COMPONENTS)
            command.extend(['--override', options])
        commands.append(command)
    return commands


def inspect_build_dependencies(root, work, cancel=None):
    """Read-only inventory; tests must not depend on an installer being present."""
    cancel = cancel or Cancellation()
    from .native_build import toolchain
    missing = []
    try:
        cmake, ninja, compiler, env = toolchain(root, work)
    except PortError as error:
        if error.code != 'BUILD_TOOLS':
            raise
        cmake = ninja = compiler = None
        env = external_env()
        # Portable packages already carry CMake/Ninja; inspect those too.
        suffix = '.exe' if os.name == 'nt' else ''
        for name in ('cmake', 'ninja'):
            bundled = [Path(root)/f'tools/{name}/bin/{name}{suffix}',
                       Path(root)/f'tools/{name}/{name}{suffix}']
            if name == 'cmake':
                bundled.append(work.path(f'tools/cmake-runtime/cmake/data/bin/cmake{suffix}'))
            found = next((str(p) for p in bundled if p.is_file()), None) or shutil.which(name, path=env.get('PATH'))
            if name == 'cmake':
                cmake = found
            else:
                ninja = found
            if not found:
                missing.append(name)
        missing.append('compiler')
    if not shutil.which('git', path=env.get('PATH')):
        missing.append('git')
    if cmake:
        probe = subprocess.run([cmake, '--version'], capture_output=True, text=True, timeout=10, env=env)
        version = re.search(r'cmake version (\d+)\.(\d+)', probe.stdout)
        if probe.returncode or not version or tuple(map(int, version.groups())) < (3, 25):
            missing.append('cmake')
    if os.name == 'nt':
        system = Path(env.get('SYSTEMROOT', env.get('SystemRoot', 'C:/Windows'))) / 'System32'
        if not all((system/name).is_file() for name in ('msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')):
            missing.append('runtime')
    if compiler:
        cancel.check()
        version = subprocess.run([compiler, '--version'], capture_output=True, text=True, timeout=10, env=env)
        match = re.search(r'clang version (\d+)', version.stdout+version.stderr)
        if not match or int(match[1]) < 18:
            missing.append('compiler')
        elif os.name != 'nt':
            # Compile only; never execute a probe binary or touch a game dump.
            probe = subprocess.run([compiler, '-std=c++23', '-x', 'c++', '-fsyntax-only', '-'],
                input='#include <expected>\nstd::expected<int,int> value(1);\n',
                capture_output=True, text=True, timeout=15, env=env)
            if probe.returncode:
                missing.append('compiler')
    release, family = {}, 'windows' if os.name == 'nt' else None
    if os.name != 'nt':
        release = read_release()
        family = distro_family(release)
        pkgconfig = shutil.which('pkg-config', path=env.get('PATH'))
        if not pkgconfig:
            missing.extend(['pkgconfig', *MODULES])
        else:
            for key, modules in MODULES.items():
                cancel.check()
                result = subprocess.run([pkgconfig, '--exists', *modules], capture_output=True, timeout=10, env=env)
                if result.returncode:
                    missing.append(key)
    return {'ready': not missing, 'missing': sorted(set(missing)), 'family': family, 'release': release}


def ensure_build_dependencies(root, work, cancel, emit, *, allowed=False):
    report = inspect_build_dependencies(root, work, cancel)
    if report['ready']:
        emit({'stage': 'tools', 'state': 'running', 'message': 'Dependências de compilação disponíveis'})
        return report
    if not allowed:
        raise PortError('DEPENDENCIES_NEEDED', 'Prepare as dependências pelo launcher antes de gerar o port.', **report)
    commands = (windows_install_commands(report['missing']) if report['family'] == 'windows' else
                [linux_install_command(package_plan(report['missing'], report['family'], report['release']), report['family'],
                                       elevated=hasattr(os, 'geteuid') and os.geteuid() == 0)])
    log_root = f'reports/dependencies/{time.time_ns()}'
    for index, command in enumerate(commands):
        cancel.check()
        emit({'stage': 'tools', 'state': 'running', 'task': 'Instalar dependências',
              'message': 'O sistema pode pedir autorização. Cancelamento será aplicado após o instalador terminar.'})
        # Do not kill a privileged package manager halfway through a transaction.
        # Canceling the launcher stops the following build after this OS step.
        try:
            result = run_process(command, root, Cancellation(), env=external_env(), timeout=14400,
                on_output=lambda line: emit({'stage':'tools', 'state':'running', 'message':line[:180]}))
        except PortError as error:
            work.write_json(log_root+f'/step-{index}-failure.json', {'command':command, 'error':error.as_dict()})
            raise
        work.write_json(log_root+f'/step-{index}.json', {'command':command, **result})
        cancel.check()
    refreshed = inspect_build_dependencies(root, work, cancel)
    if not refreshed['ready']:
        raise PortError('DEPENDENCIES_RECHECK', 'O instalador terminou, mas ainda faltam requisitos. Confira o relatório; o port e os saves foram preservados.', **refreshed)
    return refreshed
