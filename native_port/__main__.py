import argparse
import json
from pathlib import Path
import sys
from games.green_lantern import GreenLantern
from .diagnostics import diagnostics
from .errors import PortError
from .native_build import build_native
from .paths import project_root
from .pipeline import prepare
from .sources import inspect_source
from .workspace import Workspace

PROJECT = project_root(__file__)


def main():
    parser = argparse.ArgumentParser(description='Aster Native — framework experimental de portabilidade')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('gui')
    for name in ('inspect', 'prepare'):
        p = sub.add_parser(name)
        p.add_argument('source')
        if name == 'prepare':
            p.add_argument('--workspace', type=Path, default=PROJECT / '.aster')
    builder = sub.add_parser('build', help='Gerar e compilar o port a partir do dump local')
    builder.add_argument('source')
    builder.add_argument('--jobs', type=int, default=2)
    builder.add_argument('--download-sdk', action='store_true')
    builder.add_argument('--install-dependencies', action='store_true', help='Autoriza instalar requisitos ausentes pelo gerenciador oficial do sistema.')
    hd = sub.add_parser('texture-prepare', help='Preparar uma textura de cor revisada com Real-ESRGAN local')
    hd.add_argument('inspection', type=Path)
    hd.add_argument('--reviewed-color-opaque', action='store_true', help='Confirma revisão de cor opaca; exclui normais, sombras, UI e fontes')
    hd.add_argument('--download-model', action='store_true')
    pack = sub.add_parser('texture-pack-prepare', help='Preparar materiais de um catálogo local revisado com IA')
    pack.add_argument('catalog', type=Path)
    pack.add_argument('--download-model', action='store_true')
    auto_hd = sub.add_parser('texture-preset-prepare', help='Preparar automaticamente as texturas do preset a partir do dump')
    auto_hd.add_argument('source', type=Path)
    auto_hd.add_argument('--preset', choices=('high', 'ultra'), required=True)
    auto_hd.add_argument('--download-tools', action='store_true')
    ui = sub.add_parser('texture-ui-prepare', help='Preparar atlas de fonte original com alpha e métricas preservados; experimental')
    ui.add_argument('source', type=Path)
    ui.add_argument('--scale', type=int, choices=(2, 4), default=2)
    ui.add_argument('--download-tools', action='store_true')
    ui.add_argument('--coverage-format', choices=('bc3', 'rgba8'), default='bc3', help='RGBA8 preserva cobertura alpha sem recompressão; requer backend 0030.')
    helpers = sub.add_parser('texture-tools', help='Compilar helpers públicos sem assets do jogo')
    helpers.add_argument('--download-sdk', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'gui':
            from .launcher import main as launch
            launch()
            return 0
        if args.command == 'doctor':
            result = diagnostics()
        elif args.command == 'build':
            result = build_native(args.source, Workspace(PROJECT / '.aster', PROJECT),
                                  jobs=args.jobs, allow_download=args.download_sdk, install_dependencies=args.install_dependencies,
                                  emit=lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr))
        elif args.command == 'texture-tools':
            from .texture_tools import ensure_texture_tools
            result = {k: str(v) for k, v in ensure_texture_tools(PROJECT, Workspace(PROJECT / '.aster', PROJECT),
                allow_download=args.download_sdk, emit=lambda event: print(json.dumps(event), file=sys.stderr)).items()}
        elif args.command == 'texture-ui-prepare':
            from .texture_ui import prepare_game_ui
            folder = prepare_game_ui(args.source, PROJECT, Workspace(PROJECT / '.aster', PROJECT),
                scale=args.scale, allow_download=args.download_tools, coverage_format=args.coverage_format,
                emit=lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr))
            result = {'state': 'prepared', 'ui_pack': str(folder), 'scale': args.scale, 'runtime_rendered': False}
        elif args.command == 'texture-preset-prepare':
            from .texture_pipeline import ensure_graphics_textures
            result = ensure_graphics_textures(args.source, {'texture_quality': args.preset}, PROJECT,
                Workspace(PROJECT / '.aster', PROJECT), allow_download=args.download_tools,
                emit=lambda event: print(json.dumps(event), file=sys.stderr))
        elif args.command == 'texture-pack-prepare':
            from .texture_pack import prepare_texture_pack
            output = prepare_texture_pack(args.catalog, PROJECT, Workspace(PROJECT / '.aster', PROJECT),
                                          allow_download=args.download_model,
                                          emit=lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr))
            result = {'pack': str(output), 'state': 'prepared', 'runtime_rendered': False}
        elif args.command == 'texture-prepare':
            from .texture_enhance import prepare_texture
            output = prepare_texture(args.inspection, PROJECT, Workspace(PROJECT / '.aster', PROJECT),
                                     reviewed_color_opaque=args.reviewed_color_opaque,
                                     allow_download=args.download_model,
                                     emit=lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr))
            result = {'pack': str(output), 'state': 'prepared', 'runtime_rendered': False}
        elif args.command == 'inspect':
            result = inspect_source(args.source)
        else:
            result = prepare(args.source, Workspace(args.workspace, PROJECT), GreenLantern(),
                             emit=lambda event: print(json.dumps(event, ensure_ascii=False), file=sys.stderr))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 3 if result.get('state') == 'blocked' else 0
    except PortError as e:
        print(json.dumps({'error': e.as_dict(), 'ready': False}, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
