import os
import signal
import subprocess
import threading
import time
from .errors import PortError


class Cancellation:
    def __init__(self):
        self.event = threading.Event()

    def cancel(self):
        self.event.set()

    def check(self):
        if self.event.is_set():
            raise PortError('CANCELLED', 'Operação cancelada.')


def run_process(argv, cwd, cancel, timeout=120, env=None, on_output=None, output_log=None):
    """Internal trusted calls only; never accepts argv from a game manifest or UI.

    No shell, own process group; cancellation kills descendants and reaps parent.
    Output is spooled to temporary files, with a bounded diagnostic tail.
    """
    import tempfile
    start = time.monotonic()
    cancel.check()
    try:
        with tempfile.TemporaryDirectory(prefix='aster-task-') as spool, \
                open(os.path.join(spool, 'stdout'), 'w+b') as out, \
                open(os.path.join(spool, 'stderr'), 'w+b') as err, \
                open(os.path.join(spool, 'stdout'), 'rb') as live:
            pending = b''
            def stream():
                nonlocal pending
                if on_output is None:
                    return
                # Windows CRT readers can retain EOF after the initial empty
                # spool read. Reposition before each bounded read so later
                # compiler output becomes visible while the process runs.
                live.seek(live.tell())
                chunk = live.read(65536)
                if chunk:
                    parts = (pending + chunk).replace(b'\r', b'\n').split(b'\n')
                    pending = parts.pop()[-16384:]
                    for line in parts[-128:]:
                        if line:
                            on_output(line.decode('utf8', errors='replace'))
            with subprocess.Popen(argv, cwd=cwd, stdout=out, stderr=err,
                                  start_new_session=True, env=env) as proc:
                try:
                    while proc.poll() is None:
                        stream()
                        cancel.check()
                        if time.monotonic() - start > timeout:
                            raise PortError('TIMEOUT', 'Tempo limite da tarefa excedido.')
                        cancel.event.wait(0.025)
                except BaseException:
                    try:
                        if os.name == 'nt':
                            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            if proc.poll() is None:
                                proc.kill()
                        else:
                            os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    raise
                stream()
                if on_output and pending:
                    on_output(pending.decode('utf8', errors='replace'))
                # A quick tool can exit before its final output is delivered.
                # Its output callback may request cancellation even then.
                cancel.check()
                # Keep full compiler diagnostics on disk when requested. A
                # bounded tail and a sampled progress callback can both miss
                # an early error followed by warnings from parallel jobs.
                if output_log is not None:
                    import shutil
                    with open(output_log, 'wb') as diagnostic:
                        for captured in (out, err):
                            captured.seek(0)
                            shutil.copyfileobj(captured, diagnostic)
                def tail(f):
                    f.seek(0, 2)
                    f.seek(max(0, f.tell()-65536))
                    return f.read().decode('utf8', errors='replace')
                result = dict(argv=list(map(str, argv)), returncode=proc.returncode,
                              stdout=tail(out), stderr=tail(err), seconds=time.monotonic()-start)
    except OSError as e:
        raise PortError('PROCESS_START', str(e), argv=list(map(str, argv))) from e
    if result['returncode']:
        raise PortError('PROCESS_FAILED', 'Falha na ferramenta externa.', **result)
    return result
