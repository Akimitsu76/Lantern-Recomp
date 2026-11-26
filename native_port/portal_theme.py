"""Tema reutilizável do Portal dos Recomps.

Cada jogo recebe o mesmo ``shell`` do launcher, mas uma identidade própria.
Um tema é um arquivo JSON pequeno, validado aqui, que controla paleta,
tipografia, glyph e o motivo desenhado no hero. Nenhum asset externo é
necessário: o hero é gerado com primitivas do Canvas na inicialização.

Para criar o launcher de outro recomp:
    cp native_port/themes/green_lantern.json native_port/themes/meu_jogo.json
    # edite os campos; o launcher escolhe o tema por ASTER_PORTAL_THEME ou
    # pelo arquivo portal-theme.json ao lado de settings.json.

Este módulo não depende de Tk nem de Pillow, para poder ser usado por
ferramentas de empacotamento e por testes sem abrir janela.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
import json
import os
import re

from .errors import PortError


THEMES_DIR = Path(__file__).resolve().parent / 'themes'
DEFAULT_THEME = 'green_lantern'
_HEX = re.compile(r'^#[0-9a-fA-F]{6}$')


def mix(first: str, second: str, amount: float) -> str:
    """Interpola duas cores ``#RRGGBB`` (``amount=0`` devolve ``first``)."""
    amount = max(0.0, min(1.0, float(amount)))
    a = [int(first[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(second[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


def shade(color: str, amount: float) -> str:
    """Clareia (positivo) ou escurece (negativo) uma cor do tema."""
    return mix(color, '#ffffff' if amount >= 0 else '#000000', abs(amount))


@dataclass(frozen=True)
class PortalTheme:
    """Identidade visual de um launcher de recomp.

    Cores são ``#RRGGBB``. ``glyph`` é um curto rótulo simbólico usado no
    selo do portal (por exemplo ``GL``). ``hero_motif`` seleciona o desenho
    procedural do banner: ``ring``, ``rift`` ou ``grid``.
    """

    key: str = DEFAULT_THEME
    game: str = 'Green Lantern'
    subtitle: str = 'Rise of the Manhunters'
    edition: str = 'Recomp · PC'
    tagline: str = 'A luz do anel no seu PC'
    glyph: str = 'GL'
    hero_motif: str = 'ring'
    font: str = 'DejaVu Sans'
    bg: str = '#05080c'
    bg_deep: str = '#03060a'
    surface: str = '#0d1720'
    surface_2: str = '#142431'
    line: str = '#1e3444'
    accent: str = '#34e0a1'
    accent_2: str = '#9ff7d6'
    ink: str = '#eaf7f2'
    muted: str = '#809b95'
    warn: str = '#ffb454'
    danger: str = '#ff6b6b'
    ok: str = '#34e0a1'

    def palette(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in (
            'bg', 'bg_deep', 'surface', 'surface_2', 'line', 'accent',
            'accent_2', 'ink', 'muted', 'warn', 'danger', 'ok')}

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def with_overrides(self, **changes) -> 'PortalTheme':
        theme = replace(self, **changes)
        theme.validate()
        return theme

    def validate(self) -> 'PortalTheme':
        if not self.key or not re.fullmatch(r'[a-z0-9_-]+', self.key):
            raise PortError('THEME_VALUE', 'Chave do tema deve usar letras minúsculas, números, - ou _.')
        if not self.game or not self.subtitle:
            raise PortError('THEME_VALUE', 'Tema precisa de jogo e subtítulo.')
        if len(self.glyph) > 4:
            raise PortError('THEME_VALUE', 'O selo do portal deve ter até 4 caracteres.')
        if self.hero_motif not in ('ring', 'rift', 'grid'):
            raise PortError('THEME_VALUE', 'Motivo do hero deve ser ring, rift ou grid.')
        for field, value in self.palette().items():
            if not isinstance(value, str) or not _HEX.match(value):
                raise PortError('THEME_VALUE', f'Cor inválida no tema: {field}={value!r}.')
        if self.bg == self.ink:
            raise PortError('THEME_VALUE', 'Fundo e texto do tema não podem ser iguais.')
        return self


def from_dict(data: dict, *, default: PortalTheme | None = None) -> PortalTheme:
    base = default or PortalTheme()
    if not isinstance(data, dict):
        raise PortError('THEME_VALUE', 'Arquivo de tema deve conter um objeto JSON.')
    allowed = set(base.to_dict())
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise PortError('THEME_VALUE', 'Campos desconhecidos no tema: ' + ', '.join(unknown))
    return replace(base, **{k: v for k, v in data.items() if k in allowed}).validate()


def load_file(path: Path | str) -> PortalTheme:
    path = Path(path).expanduser()
    try:
        if path.stat().st_size > 65536:
            raise PortError('THEME_VALUE', 'Arquivo de tema excede 64 KiB.')
        data = json.loads(path.read_text(encoding='utf8'))
    except (OSError, ValueError) as exc:
        raise PortError('THEME_VALUE', f'Não foi possível ler o tema {path}: {exc}') from exc
    return from_dict(data)


def builtin(name: str = DEFAULT_THEME) -> PortalTheme:
    """Load ``native_port/themes/<name>.json`` with a safe built-in fallback."""
    if not re.fullmatch(r'[a-z0-9_-]+', name or ''):
        raise PortError('THEME_VALUE', 'Nome de tema inválido.')
    path = THEMES_DIR / f'{name}.json'
    if path.is_file():
        return load_file(path).with_overrides(key=name)
    if name == DEFAULT_THEME:
        return PortalTheme().validate()
    raise PortError('THEME_VALUE', f'Tema {name!r} não encontrado em {THEMES_DIR}.')


def discover(project_root: Path | str, *, override: str | None = None) -> PortalTheme:
    """Choose the theme for a project.

    Precedence: explicit override, ``ASTER_PORTAL_THEME``, a ``portal-theme.json``
    next to the settings file, then the built-in Green Lantern theme. A bad
    theme never prevents the launcher from opening: the caller may fall back.
    """
    root = Path(project_root).expanduser()
    candidate = override or os.environ.get('ASTER_PORTAL_THEME')
    if candidate:
        path = Path(candidate).expanduser()
        return load_file(path) if path.is_file() else builtin(candidate)
    local = root / '.aster' / 'config' / 'portal-theme.json'
    if local.is_file():
        return load_file(local)
    return builtin()
