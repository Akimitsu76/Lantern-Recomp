# v0.1.4-rc.4 — Integração 23 e cache limitado de texturas

Esta pré-release experimental reúne o launcher da v0.1.4-rc.3 e o backend de
integração 23. Ela não é stable e não certifica a campanha completa.

## O que mudou

O patch 0034 mantém até 128 MiB de dados DDS e metadados de mip já validados em
um cache LRU em RAM. Quando uma textura perde todos os donos na GPU e sua fonte
ainda cabe no cache, o carregador evita repetir a leitura e o hash. O cache é
compartilhado pelos caminhos Vulkan/Linux e D3D12/Windows, mas não aumenta a
VRAM, não carrega a biblioteca inteira, não elimina o primeiro carregamento nem
o upload para a GPU. A criação de um pipeline inédito ainda pode pausar a
apresentação; isso não está declarado resolvido.

A integração 23 também inclui as correções anteriores até 0033. Por acrescentar
armazenamento a um tipo público, o patch 0034 exige um novo host CPU. Quem vem
da rc.3 precisa trocar o launcher e usar **Gerar port/Atualizar port**; saves,
cache e preferências são preservados. O launcher e o comando de execução
rejeitam um backend 22 em vez de usar silenciosamente o renderizador anterior.

## Evidência desta revisão

- A suíte completa passou com 474 testes e 3 skips opcionais no Linux.
- Os controles 197/198/201, entre 100–170 s, tiveram medianas de apresentação de
  16,830/16,833/16,833 ms, máximos abaixo de 18 ms e nenhum intervalo acima de
  25 ms. São timestamps de apresentação, não tempo de GPU nem prova de campanha.
- O experimento privado 202 eliminou o teto do título, mas ficou preso em
  “Press START”; não foi integrado.
- A interface e as legendas em resolução própria continuam um protótipo privado,
  sem instalação no backend público.
- O smoke dos dois executáveis usou perfis `ASTER_DATA_HOME` temporários e
  informou versão `0.1.4-rc.4`, `scalable_fonts=true`,
  `hero_image_ready=true`, aba de atualizações e `game_launched=false`.

## Limites

Windows nativo/D3D12 continua sem validação; o EXE é exercitado sob Wine, que
não certifica GPU ou gameplay nativos. O tutorial do Disparo do Anel continua
pendente, a campanha completa não está certificada e 60 FPS/ilimitado seguem
experimentais. Não há arquivos do jogo nestes pacotes; é necessário seu próprio
dump compatível.

## Downloads

- `AsterNative-linux-x86_64.AppImage`
- `AsterNative-windows-x64.exe`
- `SHA256SUMS`
- `LEIA-ME-ATUALIZACAO.md`

No Linux, marque o AppImage como executável; se FUSE não estiver disponível,
use `--appimage-extract-and-run`.
