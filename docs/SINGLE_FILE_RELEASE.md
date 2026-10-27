# Arquivos únicos para Releases

Os assets da pré-release experimental v0.1.3 são:

- `AsterNative-windows-x64.exe` — executável Windows com recursos embutidos.
- `AsterNative-linux-x86_64.AppImage` — AppImage Linux com recursos embutidos.
- `SHA256SUMS` — checksums somente desses dois executáveis.

Esses três arquivos são os assets obrigatórios da prerelease. ZIP e TAR.GZ são
formatos anteriores opcionais e não substituem os executáveis acima. O `.exe`
único não depende de `app` ou `_internal` ao lado. Os arquivos não são assinados
digitalmente. O jogo não está incluído.

O primeiro uso instala recursos públicos em `%LOCALAPPDATA%/AsterNative/app`
(Windows) ou `${XDG_DATA_HOME:-~/.local/share}/aster-native/app` (Linux). Os dados
persistentes ficam em `.aster` dentro dessa pasta. Atualizações preservam essa
pasta. `ASTER_DATA_HOME` permite escolher uma pasta de dados distinta.

## Reproduzir

Acrescente `--single-file` aos argumentos de `scripts/package_launcher.py`,
executado pelo Python da plataforma de destino com PyInstaller disponível.
Forneça `--cmake-data` e `--ninja` como no empacotamento anterior.

No Linux, use o Python portátil de empacotamento já preparado (Python 3.13 com
PyInstaller, Pillow, xxhash e capstone) e forneça também `--appimagetool` e
`--appimage-runtime`. O runtime Python standalone foi verificado com glibc 2.17
como referência máxima, evitando impor a glibc da máquina de desenvolvimento aos
usuários. O arquivo `appimage-runtime-LICENSE` deve estar ao lado do runtime. Os binários oficiais
usados nesta execução foram verificados pelos digests publicados no GitHub:

- AppImage/appimagetool, continuous, x86_64: SHA-256
  `95cbe7cce9717fce90c484e34052ee7c7f1d7635b33c12525b4776826a7d29b6`.
- AppImage/type2-runtime, continuous, runtime-x86_64: SHA-256
  `617aa77314d57c8b8e4fae9c3f0b35af7b30d5529cb69e98f64f92510ed98a46`.

Não confie que a tag continuous conservará os mesmos arquivos: confira o hash.
O runtime é incorporado; o appimagetool serve apenas para empacotar.

O AppImage pode ser aberto com FUSE ou com
`APPIMAGE_EXTRACT_AND_RUN=1 ./AsterNative-linux-x86_64.AppImage`.
Workers usam extração automática para evitar depender de uma montagem antiga.

## Publicação do código

As mudanças deste empacotamento estão na árvore original do projeto. Antes de
publicar, compare os arquivos públicos com o checkout da branch remota. A
auditoria inclui `native_port/`, `apps/`, `scripts/`, `integrations/rexglue/`,
`games/` (somente metadados/hints revisados), `tests/` e fixtures públicas,
`docs/`, README, CMake/pyproject e workflows. `.aster`, dumps, saves, texturas
extraídas/HD, código gerado do jogo e executáveis de build nunca entram no
repositório.

A pré-release v0.1.3 inclui os patches 0024 (profundidade em 2x/3x), 0025
(pré-compilação de shaders conhecidos) e 0026 (cache de formato do pipeline do
presenter Vulkan), o módulo de requisitos e as opções independentes de gráficos.
Não altere o requisito de toolchain: Clang/C++23 e, no Windows, Build
Tools/Windows SDK continuam necessários para GERAR o jogo, embora Python não seja
necessário para ABRIR o launcher.

A validação local de empacotamento fica em `.aster/` (privado) e não é enviada.
Windows foi testado via Wine; o jogo em Windows real continua sem validação.
