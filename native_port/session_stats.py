"""Horas jogadas e última sessão do usuário.

O launcher grava apenas estatísticas próprias em ``.aster/config/play_stats.json``.
Nada aqui toca no save do jogo, no dump ou no perfil do emulador. A gravação é
feita pelo worker que espera o processo do jogo, portanto não bloqueia a UI.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile

from .errors import PortError

STATS_PATH = Path('.aster/config/play_stats.json')
SCHEMA = 1


def _path(root: Path | str) -> Path:
    return Path(root).expanduser() / STATS_PATH


def defaults() -> dict:
    return {'schema': SCHEMA, 'total_seconds': 0, 'sessions': 0,
            'last_played': None, 'last_duration_seconds': 0,
            'last_fps_target': None}


def load(root: Path | str) -> dict:
    """Lê o histórico; um arquivo ausente ou inválido vira o padrão."""
    result = defaults()
    path = _path(root)
    try:
        data = json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError):
        return result
    if not isinstance(data, dict):
        return result
    total = data.get('total_seconds')
    sessions = data.get('sessions')
    last_duration = data.get('last_duration_seconds')
    if type(total) is int and total >= 0:
        result['total_seconds'] = total
    if type(sessions) is int and sessions >= 0:
        result['sessions'] = sessions
    if type(last_duration) is int and last_duration >= 0:
        result['last_duration_seconds'] = last_duration
    last = data.get('last_played')
    if isinstance(last, str):
        try:
            datetime.fromisoformat(last)
        except ValueError:
            pass
        else:
            result['last_played'] = last
    fps = data.get('last_fps_target')
    if isinstance(fps, str) and fps:
        result['last_fps_target'] = fps
    return result


def _save(root: Path | str, data: dict) -> Path:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + '\n'
    fd, temporary = tempfile.mkstemp(prefix=path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return path


def finish(root: Path | str, started_epoch: float, *, ended_epoch: float | None = None,
           fps_target: str | None = None) -> dict:
    """Registra uma sessão encerrada e devolve o histórico atualizado."""
    if started_epoch <= 0:
        raise PortError('SESSION_TIME', 'Horário de início da sessão inválido.')
    ended = time_now() if ended_epoch is None else float(ended_epoch)
    duration = max(0, int(round(ended - started_epoch)))
    data = load(root)
    data['total_seconds'] += duration
    data['sessions'] += 1
    data['last_duration_seconds'] = duration
    data['last_played'] = datetime.fromtimestamp(ended, timezone.utc).isoformat(timespec='seconds')
    if fps_target:
        data['last_fps_target'] = fps_target
    _save(root, data)
    return data


def time_now() -> float:
    """Ponto único para testes; usa o relógio do sistema."""
    import time
    return time.time()


def format_total(seconds: int | float) -> str:
    seconds = max(0, int(seconds or 0))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours:
        return f'{hours}h {minutes:02d}min'
    return f'{minutes}min'


def format_last(value: str | None) -> str:
    if not value:
        return 'Nenhuma sessão registrada'
    try:
        moment = datetime.fromisoformat(value).astimezone()
    except ValueError:
        return 'Data indisponível'
    return moment.strftime('%d/%m/%Y %H:%M')


def summary(data: dict) -> str:
    last = format_last(data.get('last_played'))
    return f'{format_total(data.get("total_seconds", 0))} · última {last}'
