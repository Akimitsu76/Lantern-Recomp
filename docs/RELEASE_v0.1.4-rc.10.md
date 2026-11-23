# v0.1.4-rc.10 — Suporte ao RecompLauncher (níveis 1, 2 e 3)

Esta pré-release experimental publica o launcher `0.1.4-rc.10`. Ela não é
stable, não certifica a campanha completa e não distribui arquivos do jogo.

## O que mudou

Fecha o pedido de `recomplauncher.json` da issue #2 com os três níveis do SDK:

- **Nível 1 — Play:** a entrada `game` aceita uma imagem `.iso` XDVDFS ou uma
  pasta extraída com `default.xex`. O launcher confere o Title ID `575207E9` e
  inicia o recomp com `--play {input:game}`.
- **Nível 2 — Configurações:** sete opções (qualidade gráfica, resolução
  interna, tamanho da janela, tela cheia, upscaler, antisserrilhado e limite de
  FPS) aparecem na página do jogo e no Big Picture. Cada escolha foi validada
  como argumento aceito por `scripts/play_green_lantern.py`.
- **Nível 3 — Setup:** `prepare` executa `--prepare-game {input:game}` sem abrir
  janela. O extrator XDVDFS limitado e somente leitura
  (`native_port/xdvdfs_extract.py`) grava em
  `<dados>/app/.aster/game-files/green-lantern`, imprime linhas
  `progress <0..1> <texto>` e valida o SHA-256 do `default.xex`. `prepare.done`
  aponta para esse arquivo, e `dumps` cadastra os discos da Redump Europe
  (61842) e USA (90097) para o selo de dump verificado.

A correção de link do Windows da rc.9 (`add_compile_options(-msse4.1)`,
`roundevenf`) continua incluída.

Para o jogador, basta arrastar a ISO para o setup do RecompLauncher; a
extração acontece uma vez e os arquivos nunca entram no release, então uma
atualização não apaga a cópia preparada.

## Evidência desta revisão

- 19 testes de contrato do RecompLauncher passam, incluindo uma ISO XDVDFS
  sintética, extração de subdiretórios, limites de tamanho/profundidade,
  recusa de `..`, dispatch `--play`/`--prepare-game` e o ZIP com o manifesto na
  raiz.
- Suíte completa: 536 testes, 9 skipped; os dois únicos problemas restantes
  são do sandbox sem servidor X (captura de tela `ImageGrab` e um assert de
  rolagem da UI), sem relação com esta mudança.
- Smoke dos binários finais: o AppImage Linux e o EXE Windows (sob Wine)
  receberam `--prepare-game` e chegaram ao código de preparação, reportando a
  ausência da cópia de teste como esperado.
- Os dois ZIPs de release contêm exatamente o executável da plataforma e
  `recomplauncher.json`; nenhum conteúdo do jogo é incluído.

## Limites

- Windows nativo/D3D12, campanha completa e modos acima de 60 FPS seguem sem
  certificação; o EXE foi exercitado sob Wine.
- É necessário ter gerado o port no launcher do projeto ao menos uma vez.
  Presets Alta/Ultra, FSR 1 e texturas HD dependem do backend atualizado.
- Cópias que não batem com os CRC32 cadastrados funcionam, mas não recebem o
  selo de dump verificado.
- O manifesto no `main` sozinho não basta: o RecompLauncher lê o
  `recomplauncher.json` anexado ao release.

## Downloads

- `AsterNative-linux-x86_64.AppImage` (59.294.912 bytes) — SHA-256
  `8f1820a774590be75db6aa3e48c6dc2feeb9db09fb53e0cf202490ad6fd501b7`
- `LanternRecomp-v0.1.4-rc.10-Linux-x64.zip` (58.888.051 bytes) — SHA-256
  `3229526dc53c49def4cb0547fe060843f7d3d92dcd696ddbdcdcaf48bbebbae4`
- `AsterNative-windows-x64.exe` (25.935.672 bytes) — SHA-256
  `f12bd92c5fd779d755d6b03703fad2842511bcf17200863fb7088c638e482204`
- `LanternRecomp-v0.1.4-rc.10-Windows-x64.zip` (25.551.660 bytes) — SHA-256
  `973c0d23929885cfdc1a8d2d18bdca6770acbbcdd6aca243c95975b1ef9e962c`
- `SHA256SUMS`

Use o ZIP da sua plataforma para instalar pelo RecompLauncher (o manifesto
está na raiz). Os executáveis avulsos continuam disponíveis para o atualizador
embutido. No Linux, marque o AppImage como executável; sem FUSE, use
`--appimage-extract-and-run`.
