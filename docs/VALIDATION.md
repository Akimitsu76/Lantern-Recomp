# Validação executada — atualização em 24/10/2026

## Revisão de FPS e portabilidade

Ver [RELEASE_READINESS.md](RELEASE_READINESS.md) para os testes atuais de 60 FPS,
ilimitado, reutilização do cache, correções Windows e critérios pendentes.
A candidata continua experimental; registros históricos abaixo não a certificam.

## Biblioteca da campanha — 24/10/2026

- 253 materiais difusos opacos revisados, com usos registrados nas dez missões,
  preparados em2x e4x. Alta criou238 masters novos e reutilizou15; Ultra reutilizou
  todos, sem nova inferência. A primeira preparação local Alta levou2097,9s nesta
  máquina; o tempo não deve ser tratado como previsão para outros PCs.
- O carregador C++ real aceitou todos253 DDS em cada escala, com mipmaps completos
  e liberação das referências fracas. Payload DDS total:272.764.600 bytes emAlta
  e1.091.047.096 emUltra. Isso não significa que253materiais apareceram na tela.
- Revisão visual de oito folhas comparou todos253 atlas originais/resultados2x;
  não houve perda grosseira de layout/cor observada. Não certifica cada texel,
  costuraUV ou amostragem do jogo. Ultra usa os mesmos masters4x.
- Probes com biblioteca: Alta/Ultra180s em1080p chegaram ao combate inicial;
  respectivamente5800/5762 apresentações, saída0, semfatal/destino não registrado.
  Renderer registrou quatro/cinco recursosHD. Não são benchmarks deFPS nem
  certificação da campanha completa. XEX e seis saves originais mantiveramSHA256.
- 307 testes Linux aprovados (1skip) e149 Windows/Wine (2skips). Incluem cache,
  retomada após interrupção, bibliotecas, Unicode, hashes, presets e controles.
- A revisão final0014 aponta o LZX às fontes regulares canônicas de libmspack,
  idênticas aos antigos alvos symlink. SDK recompilado; essa mudança de caminho
  não altera lógica de gráficos. Windows nativo/D3D12, outrasGPUs, campanha
  completa e60FPS com esta revisão continuam pendentes.


## Presets e texturas locais — 24/10/2026

- 265 testes Linux em Xvfb aprovados, um skip de fixture privada; 107 testes
  de presets, interface, cache e pipeline Windows em Wine aprovados, um skip.
- 47 contratos C++ reais do carregador aprovados: 19 de escala/limites,
  oito de pacote legado e 20 de lote. Incluem 2x/4x BC1/BC3, dimensões 8192,
  eixos incompatíveis, escalas inválidas, orçamento e caminhos inseguros.
- Pipeline executado no dump suportado: 15 difusos opacos extraídos por hashes
  exatos e preparados em Alta2x/Ultra4x. Ultra reutilizou os masters de IA;
  os dois lotes têm cadeia completa de mipmaps e validação de integridade.
- Linux, 30FPS e saída 1920x1080: probe Alta150s (4.880 apresentações) e
  Ultra180s (5.774 apresentações) alcançaram o início da fase de Oa. Ambos
  terminaram com código0, sem fatal ou destino não registrado. Essas contagens
  não são benchmark de FPS, pois incluem menus, carregamento e captura.
- O renderer registrou quatro materiais HD distintos em cada sessão; tamanhos
  host eram exatamente2x em Alta e4x em Ultra. Isso não prova que todos os15
  materiais passaram pelos caminhos de amostragem elegíveis ou apareceram na tela.
- Capturas inspecionadas mostram personagem, cenário e efeitos sem as grandes
  áreas pretas anteriores. Não certificam todos os materiais, sombras ou emendas.
  XEX e seis arquivos de saves originais permaneceram com os mesmos SHA256.
- AppImage e EXE foram empacotados a partir das mesmas fontes. Smokes de
  interface usam dados e telas virtuais isolados; Windows real/D3D12, IA Vulkan
  em Windows real, outras GPUs, 60FPS e campanha completa continuam pendentes.
- Evidências privadas: hd-presets-{high,ultra}-gameplay-validation.json,
  hd-scales-contract-validation.json e testes/empacotamento em .aster/reports.
  Não publicar esses logs ou capturas junto das fontes.

Os registros abaixo são históricos e não substituem esta validação limitada.


## Arquivos únicos — 23/10/2026

O empacotamento agora produz `dist/AsterNative-windows-x64.exe` e
`dist/AsterNative-linux-x86_64.AppImage`. Recursos públicos são instalados na
pasta de dados do usuário, com builds e preferências persistentes em `.aster`.
Não é necessário extrair ZIP nem manter diretórios ao lado do arquivo baixado.

163 testes passaram sem falhas/skips em Xvfb. Os testes novos verificam atualização
de recursos preservando dados do usuário, extração segura, permissões de ferramentas
e caminhos persistentes de workers. Os resultados dos artefatos finais ficam em
`.aster/reports/single-file-release-validation.json`. A validação Windows continua
limitada ao launcher sob Wine, sem certificar a compilação ou o jogo em Windows real.


## Atualização — gerador portátil (23/10/2026)

O estado atual está em [PORTABLE_BUILD.md](PORTABLE_BUILD.md). O fluxo real
baixa SDK fixado com hash, gera C++ local, compila e registra artefatos por hash.
Build repetido íntegro não executa codegen nem compilador. O Linux reproduz o
plugin com cache persistente; o Windows usa D3D12/ROV ainda sem validação nativa.
As quatro falhas da revisão foram corrigidas: relógio guest com VSync off,
MSAA sem efeito, Cancelar invertido e destinos não registrados ignorados.

Os resultados abaixo são históricos. Não certificam o novo host em toda a
campanha. As medições atuais e os hashes dos pacotes ficam no relatório local
`.aster/reports/portable-release-validation.json`.


## Estado atual — launcher, presets e alvos

**152 testes passaram, zero falhas/skips**, em cerca de 4 s, com Xvfb em
1440×900. A suíte cobre launcher Tk, presets/CVars, schema 2 e migração do
schema 1, comandos dos três alvos, validação de referências FSI, isolamento dos
perfis e segurança de workers. Os testes unitários não certificam jogabilidade,
sincronização ou FPS de toda a campanha.

- `python3 scripts/play_green_lantern.py --validar --fps-target 30` passou.
- `--validar --fps-target 60` passou com o build v9 e a referência 057.
- `--validar --fps-target unlimited` passou com o build v10 e a referência
  `unlimited-gameplay-003`: 90,16 s, 38.627 apresentações (428,4/s), FSI, XEX
  carregado, entradas de teclado enviadas e nenhum fatal. O probe mantém
  `gameplay_verified=false`; não houve captura visual de gameplay no Xwayland.
- Um probe curto do build principal de 30 fps com `--graphics-preset default`
  (`preset30-default-001`, 12,52 s) carregou o XEX, aceitou as CVars do preset e
  fez 461 apresentações sem fatal, em FSI/FIFO e perfil isolado. `ready=false`
  porque o prazo curto não completa a inicialização; isso confirma aceitação das
  flags, não jogabilidade.
- A configuração real foi restaurada para 30 fps + preset Média, preservando o
  caminho do dump. As preferências ficam em `.aster/config/settings.json`
  (schema 2); nenhum preset/alvo cria ou altera saves/perfil do jogo.
- O snapshot do teste é `.aster/reports/launcher.png`, capturado em Xvfb
  1440×900. Também foram gerados `.aster/reports/launcher-real.png` (aba Jogar)
  e `.aster/reports/launcher-graphics.png` (aba Gráficos) com a configuração
  real restaurada. O layout padrão é 1160×720; o mínimo é 1088×696.
- O build duplicado `rex-rex-fps-unlimited-v10` foi auditado e removido. As
  arenas `xenia_memory_*` não foram limpas nesta rodada.

## Histórico da investigação de FPS

**129 testes passaram, zero falhas/skips**, em 2,148 s com Xvfb. Inclui extração
segura do comando de link experimental sem executar staging e detecção de
violações de memória em logs, mesmo com encerramento de retorno 0.
Hosts experimentais reutilizam os objetos CPU sem alterar o binário principal.
Veja [FPS_PROGRESS.md](FPS_PROGRESS.md); os testes unitários não certificam
jogabilidade, sincronização ou FPS de toda a campanha.

A validação pareada 30/60 (055/056) usou o mesmo build v9, perfis idênticos e a
mesma sequência de entrada. O alvo 30 mediu 30,000 chamadas de render/s,
delta1,02038 e passo de simulação0,99993; o alvo60 mediu59,997 chamadas/s,
delta1,02032 e passo0,99996. O alvo60 alcançou o checkpointLv.2, sem fatal e com
XEX intacto. O desvio de~2% do delta é comum aos dois alvos; o passo de
simulação acompanha o tempo de parede. Isso não valida golpes, física, animações,
áudio ou campanha completa. Evidência em
`.aster/reports/fps-validation-results.json`.

O caminho do launcher para 60 fps foi validado pelo probe 057 e por testes que
conferem o build v9, o relatório FSI separado, o perfil isolado e a confirmação
de aviso. O alvo 60 fica na aba **Gráficos**; **Jogar agora** e as opções normais
continuam em 30 fps. A referência 60 fps fica em
`.aster/reports/rexglue-runtime-probe-60fps.json`; a referência principal
continua em `.aster/reports/rexglue-runtime-probe.json` (047). O alvo ilimitado
usa o build v10 e `.aster/reports/rexglue-runtime-probe-unlimited.json`
(`unlimited-gameplay-003`).

A sessão humana 058 rodou 412,04 s com o build v9, FSI e o perfil isolado,
terminando com retorno 0, sem fatal e com o XEX intacto. Foram 81 janelas de
simulação com alvo 60; mediana de 300 chamadas/subpassos e delta 0,999949. A
apresentação teve mediana de 59,995/s, mas 6 janelas de 5 s ficaram abaixo de 59
(3 abaixo de 55), com máximo de 822 ms; as capturas mostram combate, pausa,
cutscene e carregamento. Isso comprova gameplay real, não certifica a sensação
de golpes, física, animações ou áudio. O perfil humano de 30 fps permaneceu
idêntico ao backup. Evidência em
`.aster/reports/rex-history/058-human-60fps/` e no resumo
`.aster/reports/rex-history/058-human-60fps/summary.json`.


## Histórico após ajuste de apresentação

**121 testes passaram, zero falhas/skips**, em 1,950 s, com a suíte completa em
Xvfb. Launcher pede FIFO com VSync ligado. Probes 043/044/047 exibiram checkpoint
e combate com menor utilização/potência global que os trechos de apresentação
imediata; XEX intacto, saves humanos iguais ao backup, retornos 0 e sem fatal
ou destino não registrado. O par 045/046 é inconclusivo por 046 ficar no título;
não usar suas médias como comparação de gameplay.

A referência do launcher é 047 e o plugin principal do cache permanece o mesmo.
O helper de testes verifica PID antes de focar/enviar entrada e exige título/classe
únicos no Niri, com espera breve para SDL processar a mudança de foco.
Veja [GPU_OPTIMIZATION.md](GPU_OPTIMIZATION.md) para números e limites.

## Histórico após cache gráfico

**119 testes passaram, zero falhas/skips**, em 1,738 s, com a suíte completa em
Xvfb. Plugin GPU RD compilado isoladamente, dependências conferidas, carga/gravação
do cache e fallback por checksum inválido observados nos testes 030–033.
A sessão humana 027 terminou sem fatal e com XEX intacto. O teste 031 retomou um
checkpoint com personagem Lv.2 usando cópia do perfil em novo processo.
Veja [GRAPHICS_POLISH.md](GRAPHICS_POLISH.md) para resultados e pendências.

## Histórico após polimentos

**115 testes passaram, zero falhas/skips**, na suíte completa em Xvfb 1280×1024.
Inclui controle da sessão experimental no Tk, exclusividade dos saves e rejeição
de comandos a probes finalizados/não habilitados. As tentativas 022–026 não
registraram fatal; o tutorial de defesa após os primeiros destroços foi alcançado,
e GAME OVER/CONTINUE foram observados. Um stream PipeWire do jogo apresentou
sinal não nulo. Veja [PLAYABILITY.md](PLAYABILITY.md) para os limites.

## Histórico após revisão e retomada

**102 testes aprovados, zero falhas/skips**, com a suíte unittest completa em
Xvfb 1280×1024. Os probes 020–021 exibiram a primeira fase com Vulkan FSI e
movimento inicial pelo teclado, sem fatal registrado no período observado.
Áudio, campanha completa e desempenho continuam sem validação.
Veja [OPENCODE_REVIEW.md](OPENCODE_REVIEW.md) e
[RESUME_CHECKPOINT.md](RESUME_CHECKPOINT.md) para evidências e limites atuais.

## Histórico após autorização de decodificação

**59 testes aprovados, zero falhas/skips** em Xvfb 1280×1024, última execução
1,094 s. Inclui decodificador real sobre fixture sintética, normalização PE,
validação de hash de análise, proteção de paths e execução do probe nativo.
**10.000 casos semânticos aprovados** para uma função real de oito bytes do dump.
Veja [NATIVE_PROGRESS.md](NATIVE_PROGRESS.md) para limites desse experimento.

Também executados: build dos quatro alvos Xenon locais, build CMake do utilitário
da raiz, análise completa Ghidra (116 s), exportação/decompilação de três alvos
confirmada com hash da entrada e linguagem corretos, resolução dos 451 registros
de importação, preparação real integrada ao launcher e conferência do original.
CTest não foi executado separadamente; a suíte unittest foi executada com Xvfb.
Os resultados anteriores abaixo são histórico e não representam o estado atual.


## Atualização após chegada do XEX real

50 testes aprovados, zero falhas/skips, em Xvfb 1280×1024 (1,086 s).
Inclui regressão de opcionais XEX inline, validação de blocos basic, metadados
de imports e bloqueio XEX_ENCRYPTED. Preparação real concluída com ready=false;
relatório em `.aster/reports/green-lantern-xex.json`. Hash do original inalterado.
Clone XenonRecomp inspecionado, não executado/compilado. Nenhum carregamento do
payload criptografado ou análise de funções realizada. Resultados anteriores abaixo.

## Resultado final

**46 testes executados e aprovados, zero falhas, zero skips**, em display virtual
Xvfb de 1280×1024. Abrange 29 testes do núcleo, 7 de pastas/configuração,
9 da interface e 1 da varredura de imagem. Tempo reportado pela suíte: 1,068 s.

```sh
python3 scripts/host_probe.py
xvfb-run -a -s '-screen 0 1440x900x24' python3 -m unittest discover -s tests -v
python3 -m compileall -q native_port games scripts tests
python3 -m native_port doctor
python3 scripts/survey_image.py '/caminho/do/jogo/Green Lantern.iso'
python3 -m native_port prepare '/caminho/do/jogo/Green Lantern.iso'
```

- Host probe: compilado com C++17, validado como ELF64 x86_64 e executado com retorno 0.
  Não contém código PowerPC nem código do jogo. Relatório `.aster/reports/host-probe.json`.
- Doctor: retornou versões reais; CMake/rexglue/XenonRecomp ausentes do PATH;
  Ghidra local 12.1.4 detectado, sem consultar MCP pelo launcher independente.
- Survey: SHA-256 da ISO e busca em 7.838.695.424 bytes concluídos em 11,717 s,
  sem escrever na fonte. Zero XDVDFS, zero CD001, duas ocorrências XEX2 com
  cabeçalhos inconsistentes. `.aster/reports/image-survey.json`.
- Prepare com ISO real: retorno 2, UNSUPPORTED_ISO, ready=false. Erro registrado
  em `.aster/reports/latest.json`; não houve extração nem importação no Ghidra.
- Fixtures de pasta/XEX: inspeção, identificação, hash, manifesto e relatórios
  executados; pipeline retorna blocked/NO_NATIVE_BACKEND, ready=false.
- Launcher: seleção de pasta com diálogo substituído por fixture, persistência
  isolada em diretório temporário, preparação, exportação, dependências ausentes,
  cancelamento visível, XEX inválido e layout mínimo 800×700 aprovados naquela
  rodada.
- Snapshot da janela inicial: `.aster/reports/launcher.png`, inspecionado visualmente.
  Nenhuma janela do usuário foi capturada; a imagem vem do display de teste.
- Compileall: concluído sem erros.

Primeiras tentativas de GUI no display da sessão e no Xvfb dentro do sandbox
não conectaram. A execução autorizada fora do sandbox permitiu validar a GUI.
Sem display, os testes gráficos são marcados como skipped, nunca aprovados.
Pillow está instalado e foi usado somente na captura opcional de teste.

## Não executado / não demonstrado

- CMake/CTest (CMake ausente).
- Extração da ISO real, importação/descompilação de XEX do jogo.
- Integração/compilação de XenonRecomp, ReXGlue ou XEXLoaderWV.
- Recompilação nativa, inicialização, renderização, áudio ou gameplay de Green Lantern.
- Integridade de assets e compatibilidade com o novo dump que o usuário está criando.

Nenhum pacote instalado; nenhuma configuração global alterada; nenhum dump,
asset ou executável privado enviado para serviços externos.
