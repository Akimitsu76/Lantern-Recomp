# v0.1.4-rc.1 — pré-release experimental (27/10/2026)

Esta é uma **pré-release experimental** do Aster Native para *Green Lantern:
Rise of the Manhunters* (Xbox 360). Ela **não é stable** e não deve ser anunciada
como tal. A campanha completa, o jogo nativo em Windows/GPU, a ausência de
engasgos e ganhos acima de 60 FPS continuam sem certificação. **30 FPS segue
como padrão**; 60 FPS e ilimitado permanecem experimentais.

Os downloads são apenas o launcher. O jogo, o dump/XEX/ISO, os saves, as
texturas extraídas ou ampliadas e o código recompilado do jogo **não** estão
incluídos.

## Mudanças desta candidata

- **Patch 0027 — submissão Vulkan assíncrona.** O fim de `EndSubmission` ainda
  drenava/esperava os workers mesmo com `async_shader_compilation` ligado. Agora,
  nesse modo, o trabalho permanece nos workers; o caminho bloqueante continua
  ajudando/esperando e os flushes de cache são preservados. Shaders com efeitos
  na memória guest (memexport) continuam no caminho sincronizado. O agendador
  D3D12 não foi alterado por este patch. Tradução de shaders inéditos e a
  primeira leitura de DDS ainda podem provocar pausas.
- **Patch 0028 — tela cheia no primeiro foco.** Se o gerenciador de janelas
  descartar o pedido de tela cheia durante o mapeamento, o pedido é repetido uma
  única vez quando a janela recebe foco. O diagnóstico isolado recuperou
  1920×1080 reais no Niri/Xwayland. A mudança não força tela cheia quando a
  opção está desligada, não altera o modo do monitor e não muda o layout público
  da classe de janela.
- **Classificação explícita de falhas de renderização.** O resumo dos logs passa
  a separar erros de tradução de shader, criação de pipeline e dispositivo
  perdido de uma saída limpa. Apresentações e `Execution complete` não aprovam
  mais um renderer que falhou; avisos recuperáveis de cache e APIs opcionais não
  são tratados como falha fatal.
- **Mudanças anteriores preservadas.** Os patches 0024 (profundidade em 2x/3x),
  0025 (pré-compilação de shaders conhecidos) e 0026 (cache de formato do
  pipeline do presenter Vulkan) continuam presentes, assim como a poda de AVIF e
  de `libstdc++`/`libgcc_s` do empacotador Linux. Não houve cópia seletiva apenas
  do 0027 sobre uma árvore antiga.

## Evidência resumida

- Suítes completas sem falhas: **386 testes Linux (2 ignorados)** e **360 testes
  Windows sob Wine (28 ignorados)**. Wine valida o launcher/contratos; não
  substitui compilação SDK/D3D12 nem gameplay em Windows real.
- Duas sessões Linux de 600,41 s em modo 60, escala interna 1x, FSR 1/FXAA e
  saída Full HD solicitada alcançaram Oa, tutorial, combate inicial e
  morte/recarregamento, com código 0 e sem fatal, destino não registrado ou falha
  de renderização detectada nos logs retidos. Não certificam a primeira missão
  inteira nem a campanha.
- Com cache da aplicação vazio, após os primeiros 100 s houve 16 intervalos de
  apresentação acima de 50 ms (máximo 599,88 ms); com cache aquecido, 3 (máximo
  234,32 ms). As medianas ficaram em 16,82 ms nos dois casos. São timestamps de
  retorno de `vkQueuePresentKHR`, incluindo menus/transições/capturas, não FPS de
  GPU ou de conteúdo único; o gameplay não é determinístico. O resultado mostra
  reutilização útil, sem prometer ausência de stutter.
- Sessões 154/155: combate inicial em 60/janela (1920×1030) e 30/Full HD Ultra
  (1920×1080), ambas com código 0 e sem erro detectado. São cenas curtas da
  abertura, não uma campanha certificada.
- Sessão 156, repetindo as entradas da 153 com o cache recém-aprendido: entre
  100–170 s, o intervalo máximo caiu de 517,57 ms para 33,90 ms e as criações de
  pipeline de 1 para 0; nenhum intervalo passou de 50 ms nessa repetição. A
  chamada Vulkan anterior consumira 493,96 ms de CPU. Isso verifica reutilização
  nessa cena; não elimina compilação/pausas de variantes inéditas.
- Linux: GLIBC máxima auditada **2.27**. O EXE foi exercitado somente sob Wine,
  sem certificar GPU Windows nativa.

## O que ainda falta

- Compilação e execução nativas em Windows real, incluindo D3D12, GPU, IA e os
  três alvos de FPS. O workflow público `native-graphics-windows.yml` cobre
  compilação/contratos, mas só produz evidência se for publicado e executado.
  Se o token de publicação não tiver escopo `workflow`, o arquivo precisa ser
  incluído manualmente; nenhum resultado de CI deve ser anunciado nesse caso.
- Campanha prolongada, primeira missão inteira, transições, mortes/
  recarregamentos, áudio/sincronia, física, sombras e efeitos.
- Ausência de stutter, 60 FPS estáveis em 2x e ganho acima de 60 FPS.
- Instalação limpa de dependências em Windows/Linux e validação dos executáveis
  publicados em máquinas diferentes.
- Assinatura digital dos executáveis; eles não são assinados.

## Como usar

### Linux

1. Baixe `AsterNative-linux-x86_64.AppImage` e `SHA256SUMS`.
2. Dê permissão de execução: `chmod +x AsterNative-linux-x86_64.AppImage`.
3. Abra o AppImage. Sem FUSE, use
   `./AsterNative-linux-x86_64.AppImage --appimage-extract-and-run`.
4. Selecione a pasta extraída que contém `default.xex` e os demais arquivos.
5. Use **Atualizar port** (ou **Gerar port**) para obter o backend novo.

### Windows

1. Baixe `AsterNative-windows-x64.exe` e `SHA256SUMS`.
2. Abra o `.exe`; não é necessário instalar Python.
3. Selecione a pasta extraída do jogo.
4. Use **Atualizar port** (ou **Gerar port**) para obter o backend novo.

O primeiro uso instala recursos públicos em
`%LOCALAPPDATA%/AsterNative/app` no Windows ou
`${XDG_DATA_HOME:-~/.local/share}/aster-native/app` no Linux. O jogo não é
baixado. É necessário fornecer um dump próprio da revisão suportada. Confira
`SHA256SUMS` antes de abrir os executáveis.

## Assets desta release

- `AsterNative-linux-x86_64.AppImage`
- `AsterNative-windows-x64.exe`
- `SHA256SUMS`
- `LEIA-ME-CANDIDATA.txt`

Pastas de build, dumps, saves, capturas, logs privados, texturas e código
recompilado do jogo não fazem parte dos assets.

Evidências privadas de sessões e relatórios não são enviadas ao repositório nem
aos assets. Consulte `RELEASE_READINESS.md`, `KNOWN_LIMITATIONS.md` e
`PORTABLE_BUILD.md` para os critérios e limites completos.
