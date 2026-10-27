import os
from pathlib import Path
import platform
import shutil
import sys
from .tasks import run_process, Cancellation
from .errors import PortError
from .paths import project_root

TOOLS = {'cc': '--version', 'c++': '--version', 'clang': '--version', 'cmake': '--version',
         'ninja': '--version', 'java': '-version', 'git': '--version',
         'rexglue': '--version', 'XenonRecomp': '--help'}


def local_tool(name):
    project = project_root(__file__)
    paths = {'cmake': project/'.aster/tools/cmake-runtime/cmake/data/bin/cmake',
             'XenonRecomp': project/'.aster/build/xenon/upstream/XenonRecomp/XenonRecomp'}
    path = paths.get(name)
    return str(path) if path and path.is_file() and os.access(path,os.X_OK) else None


def diagnostics(cancel=None):
    cancel = cancel or Cancellation()
    result = {'python': sys.version.split()[0], 'system': platform.platform(), 'tools': {}}
    for name, flag in TOOLS.items():
        cancel.check()
        path = shutil.which(name) or local_tool(name)
        item = {'available': bool(path), 'path': path, 'version': None}
        if path:
            try:
                r = run_process([path, flag], '.', cancel, timeout=5)
                item['version'] = (r['stdout'] or r['stderr']).splitlines()[0]
                if name == 'XenonRecomp':
                    item['probe_output'] = item['version']
                    item['version'] = 'build local; CLI sem opção de versão'
            except (PortError, IndexError) as e:
                if isinstance(e, PortError) and e.code == 'CANCELLED':
                    raise
                item['probe_error'] = e.as_dict() if isinstance(e, PortError) else str(e)
        result['tools'][name] = item
    try:
        import tkinter
        result['tk'] = tkinter.TkVersion
    except ImportError:
        result['tk'] = None
    ghidra_root = Path(os.environ.get('GHIDRA_INSTALL_DIR',
                      str(Path.home() / '.local/opt/ghidra_12.1.4_PUBLIC'))).expanduser()
    props = ghidra_root / 'Ghidra/application.properties'
    result['ghidra'] = {'available': False, 'path': str(ghidra_root), 'version': None,
                        'rea_status': 'not-probed-by-launcher'}
    try:
        if props.is_file() and props.stat().st_size < 65536:
            values = dict(line.split('=', 1) for line in props.read_text(encoding='utf8').splitlines()
                          if '=' in line and not line.lstrip().startswith('#'))
            result['ghidra'].update(available=(ghidra_root / 'support/analyzeHeadless').is_file(),
                                    version=values.get('application.version'))
    except OSError as e:
        result['ghidra']['error'] = str(e)
    return result
