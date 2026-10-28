# Arquivos únicos para Releases

Os assets da pré-release experimental v0.1.4-rc.3 são:

- `AsterNative-windows-x64.exe` — executável Windows com recursos embutidos.
- `AsterNative-linux-x86_64.AppImage` — AppImage Linux com recursos embutidos.
- `SHA256SUMS` — checksums somente desses dois executáveis.
- `LEIA-ME-ATUALIZACAO.md` — instruções curtas do launcher e limites conhecidos.

Launchers anteriores não têm a aba **Atualizações**: baixe e abra esta versão
manualmente uma vez. Depois disso, os próximos releases compatíveis podem ser
instalados pela própria interface, que preserva dump, saves e preferências.

Esses quatro arquivos são os assets obrigatórios da prerelease. ZIP e TAR.GZ são
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
`docs/`, README, CMake/pyproject e, quando incluídos, workflows de CI. `.aster`,
dumps, saves, texturas extraídas/HD, código gerado do jogo e executáveis de build
nunca entram no repositório.

A pré-release v0.1.4-rc.3 preserva os patches 0024 (profundidade em 2x/3x),
0025 (pré-compilação de shaders conhecidos), 0026 (cache de formato do pipeline
do presenter Vulkan), 0027 (submissão Vulkan assíncrona sem drenar workers),
0028 (uma repetição do pedido de tela cheia no primeiro foco), 0031 (FXAA Quality
3.11 no Vulkan), 0032 (atualização da conexão de apresentação em tamanho nativo
repetido), 0030 (ASTERUI2 RGBA8 opcional para cobertura de UI) e 0029
(diagnóstico opcional de c255), e acrescenta 0033 (espera da fila de apresentação
na retirada da swapchain). A integração do backend é 22. O módulo de requisitos e
as opções independentes de gráficos continuam incluídos. Não altere o requisito
de toolchain: Clang/C++23 e, no Windows, Build Tools/Windows SDK continuam
necessários para GERAR o jogo, embora Python não seja necessário para ABRIR o
launcher.

Os hashes dos assets desta revisão são:

- `AsterNative-linux-x86_64.AppImage` (53.148.152 bytes):
  `d51e9a062d45f5ff9249f8d282fc27440142ed013268e51dd3138f21c819dda8`
- `AsterNative-windows-x64.exe` (61.333.642 bytes):
  `17c38e24517fdcde515b7e924f27a72e89163ddf25fdf0d7a0480fbe8a680f83`

Trocar apenas o executável não atualiza o backend compilado. Use **Gerar
port/Atualizar port** e preserve saves/cache; o build anterior permanece em
outra pasta. Atualize também atalhos/Steam que ainda apontem para o arquivo
anterior.

A validação local de empacotamento fica em `.aster/` (privado) e não é enviada.
Windows foi testado via Wine; o jogo em Windows real continua sem validação.
O workflow público `native-graphics-windows.yml` só produz evidência se for
publicado e executado; sem escopo `workflow` no token, ele precisa ser incluído
manualmente e nenhum resultado de CI deve ser anunciado.
