# Entrega de slots no menu —30/10/2026 (backend24 /0.1.4-rc.5)

New Game e Continue agora abrem seis slots DENTRO da janela do jogo, via
runtime_save_slots.cpp. Continue relê o container original antes de aplicar o
estado; Slot1 conserva o caminho legado. Seleção ocupada cria backup após
confirmação. Retornar da seleção de jogadores cancela a troca de slot.
Veja [SAVE_SLOTS.md](SAVE_SLOTS.md), incluindo a limitação do aviso original
redundante em destino vazio e os limites da validação Windows.

Receita comum Linux/Windows inclui os dois CPPs novos eSDK0035/0037; integração
mínima24. Fontes empacotadas nos dois launchersrc.5 e verificadas byte a byte.
Artefatos locais emdist/native-slots-rc5: AppImage, EXE eSHA256SUMS. Ambos tiveram
abertura gráfica; oWindows foi verificado emWine, sem certificaçãoD3D12 real.
Não houvepush nemrelease. OworkflowWindows foi atualizado, mas .github/ está
IGNORADO por.git/info/exclude: a publicação precisa adicionar oarquivo
explicitamente após revisão. O prompt local está em
.aster/reports/features-2026-10-30/PROMPT_OPENCODE_GITHUB_SLOTS.md.

Evidências privadas em.aster/reports/features-2026-10-30; sessões207–209.
Campanha novaSlot2 chegou à fase1; ContinueSlot1, comSlot2 anteriormente emRAM,
carregou a fase de voo. Backup e rollback do menu de jogadores conferidos na
build pública em60FPS. XEX e três arquivos do perfil humano permaneceram
intactos. Não repetir a falha de reconstruir bibliotecas de uma sessão ativa:
a sessão207 terminou comSIGBUS por erro da automação, não por falha funcional
identificada no jogo; a208 terminou comexit0. Cada teste novo usa pasta imutável.

PSglyphs originais dentro do jogo continuam pendentes: a abaControles e o
remapeamento não devem ser anunciados como troca completa desses assets.

--- Checkpoints anteriores preservados abaixo ---

# Prioridade atual —30/10/2026

O usuário pediu SOMENTE slots no menu New Game/Continue, ícones PlayStation no
jogo+remapeamento na abaControles, e escolha de voz/legendas com português.
Back/Select foi confirmado como funcionamento normal; usuário concluiu fase1 e
considerou shaders jogáveis/resolvidos. Não voltar às prioridades gráficas antigas.

Há fontes novas parcialmente implementadas, AINDA NÃO integradas/validadas dentro
do jogo ou empacotadas. Não publicar como atualização pronta. Estado preciso,
arquivos, testes e próximos passos estão em
`.aster/reports/features-2026-10-30/CONTINUE.md`. Auditoria não encontrou os três
recursos nas refs locais deOpenCode/rc4. Sem push/release nesta rodada.

## Histórico anterior

# Retomada e entrega v0.1.4-rc.4 — 29/10/2026

O usuário autorizou retomar o jogo após o launcher e pediu estabilidade urgente,
otimização do custo gráfico, interface/legendas em resolução própria, 60 FPS e
ilimitado, e redução das travadas restantes. Saves humanos e a instalação do
usuário devem ser preservados; testes usam perfis `ASTER_DATA_HOME` isolados.
Não declarar stable, campanha completa ou Windows nativo sem evidência.

Estado desta entrega: fonte `0.1.4-rc.4`, `pyproject.toml` `0.1.4rc4`,
integração 23, 31 patches até `0034-bounded-hd-source-cache.patch`. O build do
workspace é `native/6c9bdb...`; o SDK Linux é `spatial-sdk/af09e...`. A
instalação humana permanece no backend 22 (`4813943...`) e não foi alterada.

O patch 0034 mantém até 128 MiB de DDS/mips validados em cache LRU; evita
releitura/hash quando a fonte ainda cabe no cache, sem ampliar VRAM, eliminar o
primeiro carregamento, o upload GPU ou a pausa de pipelines inéditos. A suíte
completa passou com 474 testes e 3 skips opcionais. Controles 197/198/201
mediram, entre 100–170 s, medianas de 16,830/16,833/16,833 ms, máximos abaixo de 18 ms e zero
intervalos acima de 25 ms; são timestamps de apresentação, não prova de GPU ou
campanha. O experimento 202 não foi integrado (travou em “Press START”). A UI em
resolução própria continua protótipo privado, sem instalação pública.

Evidência: `.aster/reports/graphics-2026-10-29/STATUS.md` e
`docs/GRAPHICS_PROGRESS_2026-10-29.md`. Backup do código:
`/run/media/victor/games/aster-backups/2026-10-29-pre-rc4`; arquivo de
evidências: `/run/media/victor/games/aster-archive/2026-10-29`.

## Histórico — launcher com atualizador, 28/10/2026

Último pedido: acrescentar Atualizações ao lado de Diagnóstico e preparar prompt
para o OpenCode publicar. Concluído em Linux e Windows/Wine. Jogo segue PAUSADO
até nova confirmação explícita; não abrir gameplay, compilar backend ou alterar saves.

Versão0.1.4-rc.3; pyproject0.1.4rc3. Pacotes finais desta função:
`dist/launcher-updater-2026-10-28-r2` com AppImage, EXE, SHA256SUMS, README e auditoria.
Candidatos anteriores permanecem históricos, não publicar no lugar destes.
Prompt de publicação mantido no relatório privado.
Notas: `docs/RELEASE_v0.1.4-rc.3.md`; funcionamento: `docs/LAUNCHER_UPDATES.md`.
Repositório atual Akimitsu76/Lantern-Recomp, ID1431033413; endereço antigo redireciona.
Publicação desta revisão: pré-release `v0.1.4-rc.3` pelo OpenCode, commit `2920c91`.

51 testes UI/Tk9Linux;20 atualizadorLinux;20Windows/Wine;3payload. Smoke dos dois
binários finalizados; troca/restart e recuperação reais em cópias isoladas passaram
nos dois sistemas, com dados fictícios preservados. Sem validação Windows nativa.
Evidências: `.aster/reports/launcher-updater-2026-10-28/VALIDACAO_FINAL.json` e
`OBSERVACOES.md`. Saves e instalação humana intactos; bugDisparo do Anel pendente.

## Histórico da entrega anterior

# Prioridade e autorização — launcher, 28/10/2026

O usuário determinou: terminar as melhorias do launcher, avisá-lo e só voltar
a mexer no jogo após confirmação explícita. Não iniciar gameplay, recompilar
backend, investigar progressão nem alterar saves enquanto essa confirmação
não chegar. O tutorial do Ring Blaster continua pendente; não declarar corrigido.

Melhorias de interface e progresso concluídas. Pacotes entregáveis em
`dist/launcher-2026-10-28-final`: AppImage Linux e EXE Windows, SHA256SUMS,
LEIA-ME e auditoria. Fontes DejaVu privadas nos dois sistemas. Tk9 Linux foi
recompilado com Xft e o módulo Pillow dinâmico foi incluído; candidatos anteriores
em `dist/launcher-2026-10-28` e `dist/launcher-2026-10-28-r2` permanecem históricos,
não usar seus AppImages. Não substituir estes caminhos pelo candidato antigo.

Os executáveis finais passaram no smoke de fontes/imagem e abriram/fecharam
normalmente com perfis isolados (Linux e Windows via Wine). 47 testes da interface
passaram no Tk9 Linux corrigido, incluindo o tamanho mínimo 1088×720. A auditoria
conferiu as 134 entradas públicas em cada pacote e seus inventários; sem conteúdo
do jogo. Isso não valida gameplay/compilação nativos Windows. Instalação humana e
saves preservados. Evidências em `.aster/reports/launcher-redesign-2026-10-28/final`.

Aguardar confirmação explícita do usuário para retomar o jogo. O problema do
tutorial do Disparo do Anel permanece sem causa/correção confirmada.

## Estado anterior do jogo — pausado

# Estado atual — 28/10/2026

Prioridade atual: bloqueio humano no tutorial de atribuição do Ring Blaster.
A gravação mostra slots preenchidos e tutorial aberto, com teclado e controle
relatados pelo usuário. A sessão foi encerrada com autorização e os saves
originais foram preservados. Reprodução e comparação30/60 em cópias ainda
não concluídas; não declarar causa nem corrigir progressão por flags forçadas.

No código do launcher, recibos externos de validação HD evitam reler/decodificar
os253 originais e toda biblioteca inalterada em cada abertura. A primeira
execução após a atualização continua integral. A mudança é comum a Linux/Windows,
com invalidação por metadados e opção de validação integral. Inventário real
medido em cerca de25ms aquecido; isso não mede a abertura completa do jogo.
Suíte Linux em Xvfb:419 testes,3skips, sem falhas. Instalação humana preservada
no backend32/integração21; estes novos arquivos ainda não estão no AppImage.

Workspace nativo: backend33/integração22. O patch0033 corrige a espera de
apresentação na retirada da swapchain, fora do caminho de cada quadro.
Preparação opcional agora reconstrói quatro shaders e dois pipelines revisados
do dump local, além do cache aprendido. Cobertura: filtro da abertura e uma
partícula do primeiro combate, não a campanha inteira. Teste pareado190/191,
mesmas entradas/cachebase, sem PNG durante comandos e cacheglobal do driver
desativado: máximo100–170s caiu de517,45ms para34,45ms; medianas16,819/16,819ms.
O pipeline de480ms passou para a preparação inicial. Sem fatal/destino não
registrado nos dois testes. Não comprova zero stutter ou aumento do FPS médio.

Correção de evidência: o contador antigo não interceptava pipelines obtidos via
vkGetInstanceProcAddr. Resultados antigos com zero criações não excluem
compilação naquele caminho. O novo contador intercepta ambos os resolvedores.
Windows/Wine validou os testes focados, mas GPU/compilação nativos Windows
continuam pendentes. Candidata r4 abaixo permanece histórica, sem estas mudanças.

## Histórico da revisão anterior

# Estado atual — 27/10/2026

SDK local com patches até 0032, integração 21. A frente de qualidade de fontes
identificou o FXAA simplificado do Vulkan como causa de erosão dos traços.
0031 substitui esse filtro pelo FXAA Quality 3.11; o bytecode Quality já existente
no D3D12 é preservado. Os testes 163–167 isolaram apresentação sem AA, FSR sem AA,
bilinear com AA antigo e FSR/AA corrigido; o texto do menu ficou mais contínuo
sem trocar sua fonte original. Capturas brutas e comparação privada estão em
`.aster/reports/quality-2026-10-27`. Não é validação de todas as fontes/partículas.

0029 registra opcionalmente os bits da constante pixel c255 junto ao diagnóstico
limitado de transparência. 0030 acrescenta o canal ASTERUI2 RGBA8 sem recompressão
BC3 do alpha; mantém ASTERUI1 e as métricas/UVs. É uma experiência CLI explícita,
sem ativação automática nos presets. Os dois formatos passaram pelo carregador
C++ real com dados sintéticos; os caminhos de imagem/view foram ajustados em
Vulkan e D3D12. Compilação/GPU nativos Windows continuam para o workflow/OpenCode.

168/169 repetiram combate a 60 FPS com SDK 0031. Entre 100–170 s, mediana de
16,74/16,76 ms; o máximo caiu de 516,25 para 50,55 ms ao reutilizar o cache.
Não houve fatal/destino não registrado/falha de renderização detectada.
As capturas 167–169 têm barras laterais de aproximadamente 44 pixels no ambiente
Niri/Xwayland. O patch 0032 corrige a conexão da superfície que ainda guardava o
tamanho anterior ao mapeamento, mesmo após o Window saber do tamanho final.
Uma notificação nativa de tamanho repetido agora atualiza o presenter sem reenviar
listeners de resize. O teste C++ reproduz 1920x1030 em cache versus 1920x1080
real; a sessão 174 voltou a preencher 1920x1080. A comparação recortada antiga
continua ilustrativa, não uma métrica pixel a pixel.

A criação inédita de pipeline ainda espera o driver mesmo em worker de fundo,
retendo o quadro completo até ficar pronta. O experimento de desativar otimização
do driver não eliminou a pausa (604,82/497,51 ms na criação). O ensaio privado de
SPIR-V otimizado também foi rejeitado: 476,89 ms versus 489,88 ms na criação
com código original, sem eliminar o engasgo e com custo adicional de preparação. Nenhuma promessa de zero stutter.

Artefatos desta revisão: AppImage, EXE, SHA256SUMS e instruções, publicados como
assets da pré-release `v0.1.4-rc.2`. As GUIs abriram com dados isolados; 126
entradas públicas por plataforma foram comparadas com as fontes/payloads. A
publicação é feita pelo OpenCode. O prompt atualizado e o estado detalhado estão
em `.aster/reports/quality-2026-10-27/PROMPT_OPENCODE_GITHUB_QUALIDADE_2026-10-27.md`
e `continuation.json`/`STATUS.md` no mesmo diretório. A instalação ativa é a do
manifesto `.aster/config/native-install.json`; caminhos/builds antigos abaixo
são históricos.

Na revisão r4, launcher e comando de execução compartilham a verificação de
versão/correções do backend em Linux/Windows. O log mostra a integração
efetivamente instalada. r4 passou 398 testes Linux/2 skips e 372 Windows/Wine/32
skips; os próprios AppImage/EXE rejeitaram um manifesto sintético de backend 20
antes de abrir o jogo. O AppImage do usuário foi atualizado de 20 para 21 com 8
arquivos verificados, saves preservados e o build anterior mantido; as novas
legendas foram avaliadas com o renderer 21, sem apagar cache/save.

## Histórico — revisão até 0028

Histórico das correções anteriores: a correção 0027 evita que o fim da
submissão Vulkan drene/espere a fila de pipelines no modo assíncrono; o caminho
bloqueante e shaders com efeitos na memória guest mantêm a sincronização.
Tradução de shaders inéditos e primeira leitura de DDS ainda podem pausar.
Não foi alterado o agendador D3D12 por esta correção.
0028 repete o pedido de tela cheia uma vez no primeiro foco caso tenha sido
descartado na abertura. O diagnóstico isolado conseguiu 1920x1080 reais no
Niri/Xwayland, sem alterar modo do monitor. Não muda classe/layout público.

Dois probes Linux de dez minutos em 60 FPS, 720p interno e saída Full HD
solicitada alcançaram a abertura, tutorial, combate e morte/recarregamento.
Sem fatal, destino não registrado ou falha de renderização detectada nos logs.
Entre 100–600 s, intervalos de apresentação acima de 50 ms caíram de 16 com
cache da aplicação vazio para 3 com cache aquecido; máximos de 599,88/234,32 ms.
Mesmas entradas agendadas, sem determinismo de gameplay garantido; menus e
transições incluídos. Não é prova de ausência de engasgos nem da campanha.

A sessão 153, no SDK final, completou 300,40 s em ilimitado/Ultra com saída
1920x1080 real; 154/155 repetiram a abertura em 60/janela (1920x1030) e
30/FullHD Ultra (1920x1080), com exit 0 e sem erro detectado. A 156 repetiu as
entradas da 153 com o cache aprendido: entre 100–170 s, máximo de 517,57 para
33,90 ms, criações de pipeline de 1 para 0 e nenhum intervalo >50 ms. São cenas
curtas; não certificam campanha, ausência de stutter ou ganho acima de 60 FPS.

Suítes desta revisão: 395 testes Linux (2 ignorados), 369 Windows/Wine (32
ignorados), sem falhas. Wine não valida GPU/compilação nativa Windows. Os
probes usam cópias de perfil e preservaram XEX/saves humanos. Evidências
privadas em `.aster/reports/stability-2026-10-27` e sessões 145/146/153–156.
O workflow Windows só produz evidência se for publicado e executado; sem escopo
`workflow`, a inclusão é manual e nenhum resultado de CI deve ser anunciado.

Não aprovar stable antes dos critérios de RELEASE_READINESS.md. Os estados
abaixo são históricos e não substituem esta seção.

# Histórico — revisão de FPS de 24/10/2026

Candidata não aprovada como stable: ver RELEASE_READINESS.md. Hook portátil agora
preserva callback/contador no ilimitado, mas navegação não foi validada. Linux
60 FPS alcançou Oa; ainda há engasgos. Corrigidos streaming/cancelamento Windows
e UTF-8 explícito. Não confundir Wine com gameplay Windows real.

# Ponto de retomada — 22–23/10/2026

## Estado atual — biblioteca da campanha (24/10/2026)

- Integração 12, patches até 0014. Perfil de 253 difusos opacos revisados com
  usos nas dez missões. Baixa/Média originais, Alta2x/Ultra4x; cache comum.
- Descomprimidos 84 cenários/personagens e dois contêineres globais. Scanner
  TFO conservador confrontado com145 registros GPU; revisão visual dos originais
  e de253 pares com resultados IA. Alpha, normais, especulares e efeitos excluídos.
- Os253 produtos2x e4x foram preparados. Alta gerou238 novos masters e reutilizou
  15; Ultra reutilizou todos. Não distribuir esses arquivos, apenas metadados.
- Bibliotecas ASTERHDLIB1 carregam só índice; DDS sob correspondência com
  fingerprint original. Leituras no primeiro uso podem causar pausa. Legacy
  batches mantêm limites antigos; cache usa referências fracas em RAM.
- Retomada usa locks liberados pelo SO após queda do processo; saída sem recibo
  fica preservada e não é aceita como resultado pronto.
- 307 testes Linux e149 Windows/Wine sem falhas (1/2 skips). Wine não valida
  D3D12 nativo. Gameplay de toda campanha e60FPS continuam não certificados.
- Evidências privadas em .aster/reports/offline-textures/campaign. Abaixo há
  registros históricos; não usar contagens/perfis antigos como estado atual.

## Histórico — presets e preparação automática (24/10/2026)

- Integração 10, patches comuns até 0011. Menu Gráficos único: Baixa/Média
  originais, Alta 2x e Ultra 4x, FSR/FXAA/AF e saída 1080p configuráveis.
- Pipeline extrai 15 difusos opacos revisados do dump suportado, antes de jogar,
  com hashes de contêiner/blocos/DDS/pixels e caches persistentes. Não usa seleção
  manual de catálogo no fluxo normal. Cobertura parcial da primeira fase.
- Master IA 4x compartilhado por preset: Ultra reutilizou inferência preparada
  por Alta. Mapas especulares, normais, UI e materiais desconhecidos excluídos.
- 265 testes Linux em Xvfb e 107 Windows em Wine aprovados (um skip em cada).
  47 contratos C++ do carregador aprovados, incluindo dimensões 8192 e limites.
- Probe Alta de 150s alcançou tutorial/combate inicial; quatro materiais HD
  efetivamente criados pelo renderer, sem fatal/destino não registrado.
  Validação Ultra e evidências finais em docs/VALIDATION.md.
- Executáveis em dist/graphics-presets-hd no workspace privado. Não publicar
  .aster, imagens/texturas, dump, saves, código gerado nem modelos de IA.
- D3D12 e IA em Windows real, campanha completa e 60FPS com estas mudanças
  continuam pendentes. Registros abaixo são históricos.

## Histórico — FSR/FXAA e protótipo HD (23/10/2026)

- SDK espacial comum por padrão em Linux e Windows, integração 8. EASU/RCAS
  e FXAA são reais; escala interna permanece 1x para evitar áreas pretas.
- Preparação Real-ESRGAN local com modelo/ferramenta fixados por hash, master 4x,
  derivada 2x BC1/BC3 e mipmaps em luz linear; cache verificado evita repetir IA.
- Substituição experimental de um material revisado nos dois backends. Não é
  pacote completo de texturas; veja HD_TEXTURES.md. O launcher seleciona um
  pacote local para Alta/Ultra e mantém o save compartilhado por usuário.
- Linux: testes completos 203/203. Dois probes de gameplay de 150 s com pacote
  ativo alcançaram combate sem fatal/destino não registrado; correção posterior
  do cache de seleção preserva as texturas originais sem refazer a seleção a
  cada bind. As capturas inspecionadas não mostram as grandes áreas pretas.
- Testes adicionais em 60 FPS permaneceram no título; a entrada automatizada
  não avançou mesmo após Start posterior. Não revalidaram gameplay 60 FPS.
- Windows em Wine: 61 testes de interface/processamento/cache e smoke do EXE.
  Compilação D3D12 e gameplay no Windows real permanecem pendentes. O workflow
  native-graphics-windows.yml, não publicado nesta revisão, compila apenas SDK
  público quando habilitado.
- AppImage e EXE novos estão em `dist/experimental-hd` no workspace privado,
  com SHA256SUMS. Nenhum modelo, textura de jogo ou save entra nos pacotes.
- Abaixo há registros históricos; não usar seus perfis isolados, flags antigas
  ou contagens de testes como instruções do launcher atual.


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

- Launcher redesenhado em abas **Jogar**, **Gráficos**, **Jogo e arquivos** e
  **Diagnóstico**, com tema escuro, cards, status de build e validação antes de
  abrir. Tamanho padrão 1160×720; mínimo 1088×696.
- Presets gráficos **Baixa**, **Média**, **Alta**, **Ultra** e
  **Personalizada** na aba **Gráficos**. Eles traduzem valores para CVars reais
  de resolução interna, MSAA, anisotrópico, cache de texturas e dithering.
- Alvos **30 fps** (padrão), **60 fps** (build v9) e **Ilimitado** (build v10,
  VSync off, apresentação imediata). 60 e ilimitado são opt-in, pedem confirmação
  e compartilham o perfil/save do usuário; não há save separado por alvo.
- Preferências do launcher em `.aster/config/settings.json`, schema 2; schema 1
  é migrado em memória e salvo como 2. Nenhum preset/alvo escreve no perfil ou
  nos saves do jogo.
- Build v10: `.aster/build/rex-fps-unlimited-v10/aster_green_lantern`, SHA-256
  `2e9069aa99ac8bce65f70c01149ec696d253922b92a4cba2cb29b09bcb9955f1`.
  Plugin `2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249`.
- Probe ilimitado final `unlimited-gameplay-003`: 90,16 s, 38.627 apresentações
  (428,4/s), FSI, entradas de teclado enviadas, sem fatal. `ASTER_SIM` manteve
  alvo 60 e simulação em tempo real; GPU global 95–96% / ~91–107 W nas amostras
  finais. `gameplay_verified=false` e sem captura X11 de gameplay.
- Probe curto do build principal de 30 fps com preset Média
  (`preset30-default-001`, 12,52 s): XEX carregado, CVars aceitas, 461
  apresentações, FSI/FIFO, perfil isolado e nenhum fatal. `ready=false` pelo
  prazo curto; confirma aceitação das flags, não gameplay.
- Referências: 30 fps `.aster/reports/rexglue-runtime-probe.json` (047); 60 fps
  `.aster/reports/rexglue-runtime-probe-60fps.json` (057); ilimitado
  `.aster/reports/rexglue-runtime-probe-unlimited.json` (003).
- `play_green_lantern.py --validar` passou nos três alvos. Suíte completa:
  **152 testes aprovados**, sem falhas/skips, em Xvfb 1440×900.
- Config real restaurada para **30 fps + preset Média**, preservando o caminho
  do dump. O build duplicado `rex-rex-fps-unlimited-v10` foi auditado e
  removido; as arenas SHM não foram limpas nesta rodada.
- Pendente do usuário: avaliar visualmente Baixa/Alta/Ultra, confirmar a sensação
  de 60/ilimitado, áudio, campanha e outras GPUs. Não executar testes que exijam
  controle humano até o retorno.

## Investigação atual: cadência da engine

- Binário e plugin principais permanecem preservados; referência estável047.
- 048/049/051 isolam a espera fora da apresentação/renderização; 052 confirma
  `82402E38` esperando cerca de33ms com alvo30 em `82836A24`. Seletor original
  `82375A28` suporta30/60 (25/50 em outro modo). Veja FPS_PROGRESS.md.
- Builder `scripts/build_rex_experiment.py` relinka114 objetos em pasta separada,
  sem codegen ou staging. Hook fica em integrations/rexglue/experiments/.
- 050/v4 falhou por leitura diagnóstica da pilha não mapeada. Reassessment registra
  a falha; leitura removida em v5. Parser agora detecta access violations.
- 054/v7 alcançou checkpointLv.2, deslocamento e ataque visual;59,87 chamadas de
  frame/s após105s, retorno0 em190,86s, semfatal/XEXintacto. Seletor60 opt-in
  desligado por padrão; o v7 não foi integrado ao launcher. 053 ficou no título.
- 055/v9 rodou o baseline de30fps no mesmo build experimental, com perfil
  idêntico ao de60: mediana de30,000 chamadas de render/s, delta1,02038s/s,
  passo de simulação0,99993 e150 subpassos por janela de5s. Terminou em208,9s
  quando a janela fechou, retorno0, sem fatal/XEXintacto.
- 056/v9 rodou o alvo60 com o mesmo build e perfil: mediana de59,997 chamadas
  de render/s, delta1,02032s/s, passo de simulação0,99996 e300 subpassos por
  janela de5s. Alcançou o checkpointLv.2, retorno0 em240,22s por prazo, sem
  fatal/XEXintacto. O delta de~2% é comum aos dois alvos; o alvo60 não o criou.
- 057 validou o caminho do launcher 60fps: buildv9, FSI, perfil isolado
  `green-lantern-60fps`, 45,18s, sem fatal, XEXintacto; referência estável em
  `.aster/reports/rexglue-runtime-probe-60fps.json`. O launcher ganhou o alvo
  opt-in de 60 fps na aba **Gráficos**, com confirmação e perfil próprio;
  30 fps continua o padrão.
- 058/sessão humana 60fps: 412,04s, retorno0, sem fatal, XEXintacto, perfil
  humano igual ao backup. 81 janelas de simulação, todas com alvo60; mediana de
  300 chamadas/subpassos, delta0,999949. Apresentação mediana59,995/s, com6
  janelas abaixo de59 e3 abaixo de55. Capturas mostram combate, pausa, cutscene
  e carregamento. A percepção de golpes/física/animações/áudio e dos engasgos
  ainda precisa do relato humano; não é certificação automática.
- GPU global na janela60–200s:30fps~31,67%/39,33W;60fps~57,41%/56,98W. Na
  sessão humana058, mediana global de67,5%/58,72W, sem pareamento de cena. É
  telemetria da placa inteira, não benchmark determinístico.
- Evidência `.aster/reports/fps-validation-results.json` e
  `.aster/reports/rex-history/055-validation-30fps/`, `056-validation-60fps/`,
  `057-60fps-launcher-validation/` e `058-human-60fps/`. Fonte do hookv9 em
  `.aster/build/rex-fps-validation-v9/hook.cpp`. Referência principal047
  restaurada, launcher `--validar` passou. Todos os probes encerrados;
  acompanhamento027 pausado.
- Na rodada 055/056, 129 testes passaram em 2,148 s, zero falhas/skips. Saves
  humanos iguais ao backup.

## Estado atual: apresentação e GPU

- Launcher com VSync on agora pede apresentação FIFO; rollback somente dessa
  escolha: `python3 scripts/play_green_lantern.py --vsync on --present-mode auto`.
- GPU local observada: imediato ~83–84%/70 W; FIFO ~35–41%/43–48 W em checkpoint
  e combate, mantendo recursos gráficos e vblank. Não é benchmark determinístico
  nem garantia para toda a campanha. Na rodada de apresentação, 121 testes
  passaram (1,950 s), zero skips.
- Referência atual:047-gpu-controlled-synchronized. Plugin principal permanece
  2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249; CPU intacta.
  Plugin de timestamps ccd67dfc fica isolado em rex-green-gpu-test, sem staging.
- 045/046 partem de perfis idênticos, mas046 ficou no título. Par inválido para
  comparar gameplay. 047 usa sequência adiada e alcança checkpoint; capturas de
  045 mostram combate. Não transformar isso em comparação de frames idênticos.
- 036–039 tiveram SIGBUS na arena de memória, inclusive com plugin antigo.
  Limpeza autorizada de 41 temporários órfãos liberou13.337.702.400 bytes;040
  rodou com o mesmo plugin de036. Runtime ainda usa `_Exit` e deixa arenas SHM:
  vazamento documentado, não corrigido; jamais limpar `/dev/shm` genericamente.
- Nenhum processo do jogo permanece ativo. Saves humanos iguais ao backup027.
  Acompanhamento027 continua pausado. FPS livre e sombras continuam pendentes.
- Veja GPU_OPTIMIZATION.md e .aster/reports/gpu-presentation-results.json.

## Histórico: atualização do cache

- Sessão humana 027 encerrada com autorização, retorno0, 2152,17s e XEX intacto;
  heartbeat acompanhar-sess-o-green-lantern está PAUSED. Nenhum jogo está aberto.
- Campanha avançou com personagem Lv.2; CONTINUE em cópia do perfil retomou o
  checkpoint em031. Não significa missão2 nem campanha inteira validada.
- Cache Vulkan do driver implementado no pluginRD, snapshot após prewarm e a
  cada10s quando houver pipelinesnovas. Testes030/031 gravaram/carregaram22.743.770
  bytes; 033 rejeitou corrupção e regravou semfatal. Fonte/patch preservados.
- Plugin principal .aster/build/rex-green/librexgpu-xenosrd.so atualizado, SHA256
  2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249.
  CPUbinário continua com o hash abaixo. Runtime/Tracy correspondem ao SDK RD.
- Rollback: .aster/backups/graphics-before-driver-cache/; saves humanos em
  .aster/backups/user-after-human-027/. Testes usam runtime e perfil separados.
- Opções: --shader-mode async|blocking e --vsync on|off. Defaults async/on.
  GUIConfiguração e ambiente contém os controles. --validar passou após staging.
- 119 testes passaram, zero skips/falhas. As tentativas028/029 são diagnósticos:
  028 carregou RDantigo (reassessment),029 mostrou que shutdown-only não persistia.
- GPU alta permanece: VSync off elevou GPU a97–98%/109W e ficou na tela inicial;
  não é desbloqueio de FPS validado em gameplay. Sombras: ocorrênciaúnica ainda
  não reproduzida. Não afirmar otimizaçãoGPU/sombras/FPS concluída.
- Referência do launcher:031-driver-cache-warm-gameplay (identidades CPU/GPU).
  Último teste técnico:033-driver-cache-corruption. Não retomar heartbeat027.

Veja [GRAPHICS_POLISH.md](GRAPHICS_POLISH.md). Os trechos abaixo são históricos.

O usuário retomou o trabalho e pediu revisão das alterações do OpenCode.
A pausa anterior foi encerrada. Nenhum build ou probe permanece em execução
ao concluir esta revisão.

## Atualização após polimentos e teste de jogabilidade

O ponto mais avançado observado é o grupo após destruir os primeiros destroços,
com o tutorial de defesa. Não foi concluída a missão inteira e não há bloqueio
técnico confirmado nesse ponto. Veja [PLAYABILITY.md](PLAYABILITY.md).

- Última tentativa: `026-jump-and-audio`, 645,77 s, encerrada pelo operador,
  retorno 0 e nenhum fatal/destino não registrado nos logs retidos.
- Tentativa 024: 900,44 s sem fatal; inclui períodos parado, não um benchmark.
- GAME OVER e CONTINUE foram exercitados; a continuação voltou à arena inicial.
- Áudio: stream PipeWire do PID do jogo com sinal não nulo em cerca de seis
  segundos; qualidade/sincronia e campanha completa permanecem pendentes.
- Launcher Tk agora tem as abas **Jogar**, **Gráficos**, **Jogo e arquivos** e
  **Diagnóstico**, com presets, alvos 30/60/ilimitado e validação em worker. A
  CLI tem `--validar`, controles completos e bloqueio de sessões concorrentes,
  também compartilhado pelos novos probes.
- Suíte completa atual: **152 testes aprovados, sem falhas ou skips**.
- Build nativo, SDK e 1.884 hints permaneceram iguais nesta rodada. O hash do
  XEX original continua intacto. Nenhum probe permanece em execução.

## Base técnica preservada

CPU recompilada estaticamente em host Linux x86_64 com ReXGlue v0.10.0 e backend
Xenos/Vulkan do SDK; FSI testado na RTX 5060. Fontes e binários derivados do jogo
continuam privados. Os 1.884 hints incluem a recuperação de `0x8220D2D0` como
tail branch de quatro bytes; 21 limites automáticos continuam em quarentena.
Não usar `--force` ou retornos artificiais para esconder destinos desconhecidos.

O relatório `.aster/reports/rexglue-runtime-probe.json` aponta à tentativa 047;
o modo 60 fps usa `.aster/reports/rexglue-runtime-probe-60fps.json` (057); o
ilimitado usa `.aster/reports/rexglue-runtime-probe-unlimited.json`
(`unlimited-gameplay-003`). `ready=false` e `gameplay_verified=false` permanecem
intencionais. A suíte atual:

```sh
xvfb-run -a -s '-screen 0 1440x900x24' python3 -m unittest discover -s tests -v
```

A revisão anterior está em [OPENCODE_REVIEW.md](OPENCODE_REVIEW.md). O projeto
não tinha commit base; não atribuir todas as linhas a um agente por suposição.

## Abrir a compilação experimental

```sh
python3 scripts/play_green_lantern.py --validar
python3 scripts/play_green_lantern.py
```

Para o alvo 60 opt-in:

```sh
python3 scripts/play_green_lantern.py --fps-target 60 --validar
python3 scripts/play_green_lantern.py --fps-target 60
```

Para o alvo ilimitado opt-in:

```sh
python3 scripts/play_green_lantern.py --fps-target unlimited --validar
python3 scripts/play_green_lantern.py --fps-target unlimited
```

Ou abrir o launcher Tk, selecionar a pasta do dump, escolher o preset/alvo na aba
**Gráficos** e usar **Jogar agora**. Consulte
[EXPERIMENTAL_PLAY.md](EXPERIMENTAL_PLAY.md) e
[GRAPHICS_PRESETS.md](GRAPHICS_PRESETS.md) para os controles completos.
Saves, cache e configurações ficam em `.aster/runtime/green-lantern/` para todos
os alvos. Nenhum alvo cria um save separado.

## Identidade e caminhos

- Jogo: `/caminho/do/jogo/Green_Lantern`.
- SHA-256 do `default.xex`:
  `3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1`.
- Executável principal: `.aster/build/rex-green/aster_green_lantern`.
- SHA-256 do executável principal testado:
  `7c7b81dd74f27623c1976bb0a3a3ed916575da060076cc77bf581b0632bda970`.
- Build 60 fps: `.aster/build/rex-fps-validation-v9/aster_green_lantern`,
  SHA-256 `906d300dea1284ead441efbe5853017c71f3775ee1e61864668ef46923a8cfdd`.
- Build ilimitado: `.aster/build/rex-fps-unlimited-v10/aster_green_lantern`,
  SHA-256 `2e9069aa99ac8bce65f70c01149ec696d253922b92a4cba2cb29b09bcb9955f1`.
- Plugin gráfico:
  `2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249`.
- Saves: `.aster/runtime/green-lantern/user`.
- Referências FSI: `rexglue-runtime-probe.json` (30),
  `rexglue-runtime-probe-60fps.json` (60) e
  `rexglue-runtime-probe-unlimited.json` (ilimitado).
- Histórico de execução: `.aster/reports/rex-history/`.
- Análises, imagens PE e hints em quarentena: `.aster/analysis/green-lantern/`.

## Próxima validação

Concluir manualmente o tutorial de defesa, ativar o primeiro salto contextual,
atingir um checkpoint posterior e conferir CONTINUE em uma nova sessão. Validar
qualidade/sincronia de áudio, combate prolongado, desempenho e outras GPUs.
Comparar visualmente Baixa/Média/Alta/Ultra no mesmo trecho e registrar a
sensação de 60/ilimitado (tearing, engasgos, física, animações e áudio). Para o
alvo 60, comparar duração de golpes e comportamento no mesmo trecho antes de
considerar integração; o passo de simulação já foi medido, mas isso não certifica
o comportamento visual ou de combate. Para o ilimitado, confirmar visualmente o
gameplay e a estabilidade; a evidência atual é automatizada e tem
`gameplay_verified=false`.

Os probes agora aceitam `--live-input`; comandos de `scripts/rex_probe_input.py`
são pedidos enfileirados, cuja execução e captura devem ser conferidas em
`live-results.jsonl`. O encerramento com `--stop` preserva o relatório e verifica
o XEX. Consulte a integração ReXGlue para reprodução. Nenhum processo foi deixado
aberto ao finalizar esta rodada.
