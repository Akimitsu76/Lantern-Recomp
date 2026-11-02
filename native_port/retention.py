"""Modo leve: remove caches de atualização e mantém só o necessário para jogar.

A geração/atualização do port baixa ferramentas e cria texturas intermediárias.
Depois que o build e o pack HD estão prontos, esses arquivos não são mais
necessários para abrir o jogo. Este módulo apaga apenas caches conhecidos,
sempre depois de conferir o build ativo e sem tocar em saves, preferências,
shaders decodificados, recibos de validação, originais ou no pack HD em uso.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil

INTERMEDIATE_TEXTURES = ('inference', 'decoded', 'prepared')
BUILD_NAME = re.compile(r'[0-9a-f]{20}')
PACK_NAME = re.compile(r'[0-9a-f]{64}')


def human_size(value):
    amount = float(value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if amount < 1024 or unit == 'TB':
            return f'{int(amount)} B' if unit == 'B' else f'{amount:.1f} {unit}'
        amount /= 1024
    return f'{amount:.1f} TB'


def _size(path, seen):
    """Conta blocos uma única vez; btrfs pode compartilhar inodes entre caches."""
    if not path.exists() and not path.is_symlink():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            info = path.lstat()
        except OSError:
            return 0
        key = (info.st_dev, info.st_ino)
        if key in seen:
            return 0
        seen.add(key)
        return info.st_size
    total = 0
    for root, _directories, files in os.walk(path):
        for name in files:
            try:
                info = os.lstat(os.path.join(root, name))
            except OSError:
                continue
            key = (info.st_dev, info.st_ino)
            if key not in seen:
                seen.add(key)
                total += info.st_size
    return total


def _configured_pack(project):
    path = Path(project) / '.aster/config/settings.json'
    try:
        if path.stat().st_size > 65536:
            return None
        value = json.loads(path.read_text(encoding='utf8')).get('hd_texture_pack')
        return Path(value).expanduser().resolve() if isinstance(value, str) and value else None
    except (OSError, ValueError, AttributeError):
        return None


def _build_running(project):
    lock = Path(project) / '.aster/native/build.lock'
    if not lock.is_file():
        return False
    try:
        from .locking import lock_session
        descriptor = lock_session(lock)
    except BlockingIOError:
        return True
    except OSError:
        # Sem certeza de que o workspace está livre, não apague nada.
        return True
    else:
        os.close(descriptor)
        return False


def _active_build(project, install):
    binary = (Path(project) / install['binary']).resolve()
    native = (Path(project) / '.aster/native').resolve()
    if not binary.is_file():
        raise ValueError('o executável do build ativo não existe')
    active = binary.parents[1].resolve()
    if active.parent != native or not BUILD_NAME.fullmatch(active.name):
        raise ValueError('o build ativo está fora do diretório esperado')
    return active


def _prune_pack_home(home, keep_packs, removable, skipped):
    """Remove packs antigos, preservando o diretório que contém o pack em uso."""
    if not home.is_dir() or home.is_symlink():
        return
    home = home.resolve()
    kept_children = set()
    for pack in keep_packs:
        try:
            relative = pack.resolve().relative_to(home)
        except (OSError, ValueError):
            continue
        if relative.parts:
            kept_children.add((home / relative.parts[0]).resolve())
    if not kept_children:
        # Sem um pack de referência não há como saber o que é descartável.
        skipped.append(f'{home} preservado: nenhum pack de referência')
        return
    for child in sorted(home.iterdir()):
        if (child.is_dir() and not child.is_symlink() and PACK_NAME.fullmatch(child.name)
                and child.resolve() not in kept_children):
            removable.append(('pack HD antigo', child))


def trim_workspace(project, workspace_root, *, keep_packs=(), keep_tools=False):
    """Aplica o modo leve e devolve um relatório sem levantar erro de limpeza.

    ``project`` é a raiz instalada (onde ficam ``.aster/config`` e o build) e
    ``workspace_root`` é o diretório de trabalho usado pelas texturas. O build
    ativo é conferido por hash antes de qualquer remoção. Em caso de dúvida a
    função não apaga nada e devolve ``state='skipped'``.
    """
    project = Path(project).resolve()
    workspace = Path(workspace_root).expanduser().resolve()
    report = {'state': 'clean', 'removed': [], 'freed': 0, 'warnings': [], 'kept_build': None,
              'message': 'Nada para remover. O workspace já está no modo leve.'}

    if _build_running(project):
        report.update(state='skipped', message='Geração em andamento; limpeza adiada.')
        return report

    keeps = []
    for value in (*keep_packs, _configured_pack(project)):
        if isinstance(value, (str, os.PathLike)) and str(value):
            keeps.append(Path(value).expanduser().resolve())
    keep_set = set(keeps)

    # Monte a lista antes de conferir o build: quando o workspace já está
    # limpo, abrir o jogo não precisa recalcular o hash dos artefatos.
    def workspace_dir(relative):
        raw = workspace / relative
        if not raw.is_dir() or raw.is_symlink():
            return None
        resolved = raw.resolve()
        return resolved if resolved.is_relative_to(workspace) else None

    removable = []
    if not keep_tools:
        tools = workspace_dir('tools')
        if tools:
            removable.append(('ferramentas de compilação', tools))

    for name in INTERMEDIATE_TEXTURES:
        path = workspace_dir(f'textures/{name}')
        if path:
            removable.append((f'texturas intermediárias ({name})', path))

    _prune_pack_home(workspace / 'textures/packs', keep_set, removable, report['warnings'])
    _prune_pack_home(workspace / 'textures/libraries', keep_set, removable, report['warnings'])

    native = (project / '.aster/native').resolve()
    if native.is_dir() and not native.is_symlink():
        for child in sorted(native.iterdir()):
            if (child.is_dir() and not child.is_symlink() and BUILD_NAME.fullmatch(child.name)
                    and child.resolve().parent == native):
                removable.append(('build antigo', child))
    if not removable:
        return report

    from .errors import PortError
    from .native_build import read_install, verify_install
    try:
        install = read_install(project)
    except PortError as exc:
        report.update(state='skipped', message='Build ativo inválido; nada foi apagado.', warnings=[str(exc)])
        return report
    if not install:
        report.update(state='skipped', message='Nenhum build instalado; nada foi apagado.')
        return report
    try:
        verify_install(project, install)
        active = _active_build(project, install)
    except (PortError, ValueError, KeyError, TypeError) as exc:
        report.update(state='skipped', message='Build ativo não conferido; nada foi apagado.',
                      warnings=[str(exc)])
        return report
    report['kept_build'] = str(active)

    # Nunca remova o mesmo caminho duas vezes nem um diretório que contenha o
    # build ativo. A verificação é feita depois de resolver links simbólicos.
    final = []
    seen = set()
    for label, path in removable:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if (resolved in seen or resolved == active or active.is_relative_to(resolved)):
            continue
        seen.add(resolved)
        final.append((label, path))
    if not final:
        return report

    measured = set()
    before = shutil.disk_usage(workspace if workspace.is_dir() else project).free
    for label, path in final:
        freed = _size(path, measured)
        try:
            if path.is_symlink():
                raise OSError('link simbólico preservado')
            shutil.rmtree(path)
        except OSError as exc:
            report['warnings'].append(f'{label}: {exc}')
            continue
        report['removed'].append({'kind': label, 'path': str(path), 'bytes': freed})
        report['freed'] += freed

    if not report['removed']:
        report.update(state='skipped', message='Nada foi removido; os caches foram preservados.')
        return report
    after = shutil.disk_usage(workspace if workspace.is_dir() else project).free
    report['state'] = 'trimmed'
    report['message'] = (f'Modo leve aplicado: {len(report["removed"])} item(ns), '
                         f'{human_size(report["freed"])} de cache removidos '
                         f'(livre: {human_size(before)} → {human_size(after)}).')
    return report
