# Preparação da release

## Integração 23 e cache de texturas — v0.1.4-rc.4, 29/10/2026

**Pré-release experimental, não stable.** A versão embutida é `0.1.4-rc.4`; o
`pyproject.toml` usa a forma PEP 440 `0.1.4rc4`. A fonte exige integração 23 e
inclui os patches até `0034-bounded-hd-source-cache.patch`.

- O patch 0034 mantém até 128 MiB de DDS e metadados de mip validados em cache
  LRU. Ele evita releitura/hash quando a fonte ainda cabe no cache, mas não
  aumenta VRAM, não elimina o primeiro carregamento, o upload para a GPU ou a
  pausa de criação de um pipeline inédito.
- A suíte completa passou com 474 testes e 3 skips opcionais no Linux. Os
  contratos C++ seletivos do carregador HD e do timing portátil também foram
  executados.
- Controles 197/198/201, entre 100–170 s: medianas de apresentação de
  16,830/16,833/16,833 ms, máximos abaixo de 18 ms, zero intervalos acima de
  25 ms. São timestamps de apresentação, não tempo de GPU ou campanha.
- O experimento 202 não foi integrado: eliminou o teto do título, mas ficou
  preso em “Press START”. A UI em resolução própria permanece um protótipo
  privado, sem instalação no backend público.
- Assets: `AsterNative-linux-x86_64.AppImage` (53.152.248 bytes, SHA-256
  `a76864faa255878c6ab31db62d3d2c80a7b690339d9c3508b89bffbe6c2dd0d0`),
  `AsterNative-windows-x64.exe` (61.337.400 bytes, SHA-256
  `5296bc1f944e4a9e5375dd811107fa0196ea355dadb8291aa6da99dc70f4ffc0`),
  `SHA256SUMS` e `LEIA-ME-ATUALIZACAO.md`.
- Limites: Windows nativo/D3D12 sem validação; o EXE é exercitado sob Wine.
  Campanha completa, tutorial do Disparo do Anel e estabilidade de 60
  FPS/ilimitado continuam sem certificação. Não é stable.
- Atualização: usuários da rc.3 precisam trocar o launcher e usar **Gerar
  port/Atualizar port** para receber a integração 23; saves, cache e
  preferências são preservados.

## Histórico — launcher v0.1.4-rc.3, 28/10/2026

**Pré-release experimental, não stable.** Esta revisão publica o launcher com
interface renovada, fontes DejaVu privadas, Tk 9.0.4/Xft no Linux e atualizador
integrado. A versão embutida é `0.1.4-rc.3`; o `pyproject.toml` usa a forma
PEP 440 `0.1.4rc3`. O backend do jogo não é atualizado automaticamente por esta
entrega.

- A aba **Atualizações** consulta a API pública do repositório pelo ID
  `1431033413`, em segundo plano na abertura, a cada 30 minutos e manualmente.
  Ela ignora rascunhos, versões não maiores e releases sem o asset da plataforma
  e `SHA256SUMS`. Pré-releases são incluídas por padrão, com opção para excluí-las.
- O download aceita somente HTTPS nos hosts previstos, pode ser cancelado e
  confere tamanho, formato x64 e SHA-256. A instalação usa um helper copiado,
  substituição atômica, cópia de rollback temporária, reinicialização e handshake
  de versão/nonce; se a nova interface não abrir, a versão anterior é restaurada.
  Staging concluído é limpo e, após o sucesso, rollback e pacote baixado são
  apagados: resta apenas o launcher novo.
- Validação desta entrega: 51 testes da interface/Tk9 no Linux; 20 testes do
  atualizador no Linux e 20 no Windows/Wine; 3 testes de payload. Os dois
  executáveis passaram no smoke com perfis `ASTER_DATA_HOME` temporários e
  informaram versão `0.1.4-rc.3`, `scalable_fonts=true`,
  `hero_image_ready=true`, aba de atualizações e `game_launched=false`.
  Troca/reinicialização e recuperação reais passaram em cópias isoladas nos dois
  sistemas, com dados fictícios preservados. A consulta GitHub ao vivo passou
  em Linux e Windows/Wine.
- Assets: `AsterNative-linux-x86_64.AppImage` (53.148.152 bytes, SHA-256
  `d51e9a062d45f5ff9249f8d282fc27440142ed013268e51dd3138f21c819dda8`) e
  `AsterNative-windows-x64.exe` (61.333.642 bytes, SHA-256
  `17c38e24517fdcde515b7e924f27a72e89163ddf25fdf0d7a0480fbe8a680f83`).
- Limites: não houve novo teste de gameplay nem validação Windows nativa; Wine
  não certifica D3D12/GPU nativas. O tutorial do Disparo do Anel continua
  pendente, a campanha completa não está certificada e o port não é stable.
  Usuários de launcher antigo precisam baixar esta versão manualmente uma vez.

## Revisão local de qualidade — patches 0029–0032, integração 21

**Candidata experimental, ainda sem aprovação stable.** A publicação desta
revisão é feita pelo OpenCode, conforme escolha do usuário. Os pacotes desta
revisão são os assets da pré-release `v0.1.4-rc.2`; hashes e smoke são
registrados junto aos artefatos e no relatório privado de qualidade. O histórico
de v0.1.4-rc.1 abaixo continua descrevendo a revisão anterior, até 0028.

- A revisão r4 verifica a versão/correções do backend tanto no launcher como
  no comando de execução, em Linux e Windows. Evita usar silenciosamente um
  renderizador anterior depois de substituir o AppImage/EXE; preserva saves/cache.
- 0031 substitui o FXAA simplificado Vulkan por FXAA Quality 3.11. Comparações
  separaram FSR e FXAA e mostraram contornos de texto mais contínuos com a
  fonte original e FSR ainda ligado. O bytecode D3D12 Quality permanece intacto.
- 0032 reconecta o presenter quando uma notificação nativa repete o tamanho já
  conhecido pelo Window. O contrato C++ reproduz uma superfície que ficou em
  1920x1030 e confirma sua atualização para 1920x1080 sem duplicar listeners.
  A sessão 174 confirmou o preenchimento da janela 1920x1080 sem as barras
  laterais vistas na revisão 0031. Não é validação de todos os monitores/DPI.
- 0029 acrescenta diagnóstico opcional e limitado de c255/transparência;
  não altera shaders, alpha ou memória do jogo. 0030 oferece ASTERUI2 RGBA8
  opcional, sem recompressão BC3 do alpha nem mudança de métricas/UVs. Os
  formatos antigo e novo passaram pelo carregador C++ real com dados sintéticos.
- Abertura/combate da revisão 0031 em 60 FPS: medianas 16,74/16,76 ms entre
  100–170 s, máximos 516,25/50,55 ms antes/depois de reutilizar cache. O primeiro
  pipeline novo continua podendo reter o quadro. Não confundir timestamps de
  apresentação com tempo de GPU, conteúdo único ou certificação de campanha.
- A sessão 175, mais recente, mediu 190,38 s em combate a 60 FPS; entre 100–170 s,
  mediana 16,75 ms, máximo 35,18 ms e zero intervalos acima de 50 ms com cache
  aprendido. A sessão 178 teve uma pausa de 334,67 ms entre 175–225 s, sem
  destruição de imagens Vulkan observada nesse intervalo. Não atribuir todo
  stutter à falta de VRAM nem prometer eliminação nesta release.
- As experiências privadas de desativar otimização do driver e pré-otimizar
  SPIR-V não eliminaram a pausa de cerca de 0,5 s e não fazem parte desta receita.
- Suíte Linux r4: 398 testes, 2 ignorados, sem falhas, incluindo o carregador
  nativo. Windows/Wine r4: 372 testes, 32 ignorados, sem falhas. Wine não valida
  SDK/D3D12 nem gameplay Windows nativo. O workflow Windows inclui os novos
  contratos; só produz evidência se for publicado/executado. Sem escopo
  `workflow`, o arquivo permanece local para inclusão manual e não há CI aprovado.

Continuam pendentes a revisão completa de rastros/partículas/legendas, a redução
do custo de pipelines realmente inéditos, campanha prolongada e GPU Windows
nativa. A revisão corrige um defeito de apresentação; não é um remaster completo.
As notas publicadas estão em `docs/RELEASE_v0.1.4-rc.2.md`.

## Candidata v0.1.4-rc.1 — 27/10/2026

**Ainda não aprovada como stable.** Esta seção descreve a candidata publicada
como pré-release; não implica aprovação stable nem substitui os critérios abaixo.

- Patch 0027 corrige a espera incondicional pela fila de pipelines no fim da
  submissão Vulkan em modo assíncrono. O caminho bloqueante mantém ajuda/espera
  e os flushes de cache são preservados. Um contrato C++ executa o ramo real
  anterior e corrigido em diferentes estados de workers. D3D12 não foi alterado
  por este patch. Tradução de shaders inéditos e leitura inicial de DDS ainda
  podem provocar pausas.
- Duas sessões Linux de 600,41 s em modo 60, escala interna 1x, FSR 1/FXAA e
  saída Full HD solicitada terminaram com código 0, sem fatal, destino não
  registrado ou falha de renderização detectada nos logs retidos. O percurso
  observado inclui abertura de Oa, tutorial, combate inicial e morte/recarregamento.
  Não certifica a primeira missão inteira nem a campanha. Nas capturas 1x
  inspecionadas não apareceram os grandes polígonos pretos anteriores.
- Após os primeiros 100 s, o cache da aplicação vazio teve 16 intervalos de
  apresentação acima de 50 ms (máximo 599,88 ms); a repetição com cache aquecido
  teve 3 (máximo 234,32 ms). Medianas de 16,82 ms em ambos. São timestamps de
  retorno de `vkQueuePresentKHR`, incluindo menus/transições/capturas, sem medir
  GPU ou quadros de conteúdo único. Mesmas entradas agendadas, gameplay não
  determinístico; cache global NVIDIA preservado. O resultado demonstra
  reutilização útil, sem atribuir todo o ganho ao patch nem prometer zero stutter.
- Patch 0028 repete uma única vez o pedido de tela cheia no primeiro foco se
  ele foi descartado durante o mapeamento da janela. O diagnóstico isolado
  passou de 1920x1030 para 1920x1080 reais no Niri/Xwayland; a mudança preserva
  modo janela, configuração do monitor e o layout público do SDK. O teste C++
  cobre sucesso/falha, foco repetido e destruição da janela.
- Suítes completas sem falhas: 386 testes Linux (2 ignorados) e 360 testes
  Windows sob Wine (28 ignorados). A análise agora distingue falhas de
  tradução/pipeline/dispositivo perdido de ausência de crash: apresentações
  e saída limpa não aprovam um renderer que falhou.
- O XEX original e os três arquivos do perfil humano permaneceram idênticos.
  Os testes usam cópias de perfil. Evidências privadas: sessões 145/146 e
  `.aster/reports/stability-2026-10-27/cold-warm27-comparison.json`.
- A instalação final com 0028 completou 300,40 s em ilimitado, Ultra4x e saída
  efetiva 1920x1080. Navegação, abertura, movimento e animações de ataque foram
  observados; sem fatal/destino não registrado/erro de renderização detectado.
  Entre 100–300 s, mediana de apresentação 16,82 ms, dois intervalos acima de
  50 ms e máximo 517,57 ms. Não há ganho acima de 60 FPS comprovado. Escala
  interna 1x e três materiais HD registrados; não certifica combate/campanha.
- AppImage e EXE finais foram empacotados com 0027/0028, abriram a GUI com
  dados isolados e tiveram os payloads extraídos comparados com as fontes.
  Nenhum conteúdo de jogo proibido entrou nos pacotes; GLIBC máxima Linux2.27.
  Os executáveis são os assets da pré-release v0.1.4-rc.1; o EXE foi exercitado
  somente sob Wine. O workflow Windows só produz evidência se for publicado e
  executado; sem escopo `workflow`, a inclusão é manual e o CI não é aprovado.
- Na mesma instalação, modo60 em janela e modo30/Ultra em tela cheia também
  alcançaram combate inicial e terminaram com código0, sem falha fatal ou de
  renderização detectada. O teste em janela permaneceu em 1920x1030, comprovando
  que 0028 respeita a opção desligada; tela cheia ficou em 1920x1080. Os trechos
  de 100–180 s tiveram medianas de 16,82/33,36 ms e uma pausa >50 ms em cada.
  São sessões curtas da abertura, sem certificação da missão/campanha ou FPS
  constantes.
- Repetindo as entradas da sessão 153 com seu cache recém-aprendido, a 156
  completou 173,47 s, com combate visual observado e sem erro
  fatal/renderização detectado. Entre 100–170 s, a pausa máxima passou de
  517,57 para 33,90 ms e as criações de pipeline de 1 para 0; nenhuma
  apresentação excedeu 50 ms na repetição. A chamada Vulkan anterior consumira
  493,96 ms de CPU. Mesma base de perfil e
  entradas, sem gameplay determinístico garantido. Isso verifica reutilização
  nessa cena; não elimina a compilação ou pausas de variantes inéditas.

Continuam necessários Windows nativo/D3D12, progresso prolongado na campanha,
avaliação de efeitos/sombras/áudio, instalação limpa e validação dos executáveis
publicados em máquinas diferentes. O CI Windows desta revisão não foi executado
sem o workflow publicado.
60 FPS e ilimitado permanecem experimentais; 30 FPS continua o padrão.

## Atualização — 26/10/2026 (pré-release v0.1.3)

Estado: **pré-release experimental; não aprovada como release estável**.

Esta seção substitui as contagens e o estado de empacotamento do histórico de
24/10 abaixo. O restante do documento permanece como registro daquela etapa.

- A suíte Linux completa passou com **379 testes e 1 ignorado** sob Xvfb, sem
  falhas. A suíte de contratos Windows sob Wine passou com **353 testes e 25
  ignorados**. Os dois testes C++ novos do patch 0026 executaram o ramo real no
  Linux; no Wine eles são ignorados por falta de compilador. A compilação C++
  nativa em Windows continua pendente e não foi coberta por CI nesta revisão.
- Patch 0024 corrige as coordenadas de profundidade em 2x/3x nos emissores
  SPIR-V e DXBC. Patch 0025 adiciona a pré-compilação opcional do cache conhecido
  de shaders, ligada por padrão. Patch 0026 guarda o formato do pipeline final do
  presenter Vulkan e evita a recriação por apresentação.
- No controle local 142→143, na abertura, 1440p interno, saída 1080p, ilimitado,
  sem AA/AF e mesma base de cache/entradas, a mediana após 100 s passou de 24,80
  para 44,28 apresentações Vulkan/s; as criações de pipeline caíram de 1.232 para
  0. É uma janela curta de abertura, não um benchmark universal.
- O controle 144, em modo 60 com FSR 1/FXAA/8x, teve mediana de 43,70
  apresentações/s. O controle 141, em 720p interno, teve 60,00/s. Nenhum deles
  certifica 60 FPS constantes em 2x, ganho acima de 60 ou a campanha completa.
- Presets Baixa/Média/Alta/Ultra/Personalizada, saída Full HD e opções
  independentes de escala, textura, filtragem, AA e FPS estão presentes. A escala
  interna continua 1x/2x/3x; não há 1080p interno exato em 1,5x.
- Saves/cache são do usuário e compartilhados entre configurações e alvos de FPS.
  Atualizações do launcher preservam a pasta de dados. A pré-release inclui os
  executáveis atuais Linux/Windows e `SHA256SUMS`; Windows foi exercitado apenas
  como launcher sob Wine.
- Nenhum workflow de CI foi publicado ou executado nesta revisão; o arquivo
  `native-graphics-windows.yml` permanece fora da publicação.

Critérios ainda pendentes: campanha completa, Windows nativo/D3D12, 60 FPS
estáveis em 2x, ausência de engasgos, avaliação visual dos efeitos e instalação
real de dependências em máquina limpa. Não anunciar estabilidade.

## Histórico — 24/10/2026

Estado naquela data: **candidata experimental; não aprovada como release estável**.

As mudanças são comuns aos launchers Linux e Windows. O jogo é gerado localmente
pelo usuário; o executável do launcher não contém o jogo, saves ou texturas.

## Resultado da revisão — 24/10/2026

- O ilimitado antes omitia toda a função de pacing, incluindo a chamada de
  contador e a gravação do último contador. O hook agora mantém os efeitos do
  caminho conhecido de 60 Hz e omite suas esperas; estados inesperados usam a
  função original. Um teste C++ executa o hook real com callback que altera estado.
- Essa correção **não comprovou navegação funcional no ilimitado**. Nos probes
  mais recentes, os menus não avançaram com entradas sintéticas verificadas.
  O mesmo binário entrou na fase em 60 FPS. Foco interno/entrada e timing ainda
  precisam ser distinguidos; ausência de crash não aprova o ilimitado.
- Em Linux, dois testes de 300 s com Ultra/FSR e saída 1920×1080 alcançaram o
  começo de Oa. Não houve fatal ou destino não registrado. Capturas inspecionadas
  não mostraram as grandes áreas pretas anteriores. Sombras e campanha inteira
  não estão certificadas. Um teste incluiu combate e tela normal de Game Over.
- Com cache inicialmente vazio, o trecho final teve mediana de aproximadamente
  59,4 apresentações/s e intervalo máximo de 1.050 ms. Reutilizando o cache,
  a janela de 200–270 s teve mediana de 60,0 apresentações/s e intervalo máximo
  de 333 ms. Não são benchmarks pareados: cenários, entradas e capturas diferem;
  os intervalos podem incluir gameplay, transições e menus. São timestamps de
  apresentação do guest, não FPS medido no monitor. Engasgos continuam pendentes.
- O segundo teste carregou 11.230.694 bytes de cache de driver e criou 155
  pipelines antes do jogo. Isso comprova reutilização do cache, sem garantir
  ausência de novas compilações ou pausas na campanha.
- No Windows, a leitura da saída de processos permanecia em EOF e não mostrava
  novas linhas durante a compilação. Reposicionamento antes da leitura corrige
  o progresso ao vivo; cancelamento da última linha também passa a ser respeitado.
  Teste focado em Wine passou de falha após 30 s a sucesso em aproximadamente
  0,114 s. Metadados e fontes agora especificam UTF-8 para preservar acentos e
  caminhos Unicode independentemente da página de código do Windows.
- Suíte: 310 testes Linux, uma dispensa; 301 testes Windows/Wine, 14 dispensas,
  sem falhas. Dispensas incluem ELF/POSIX, pesquisa X11/fcntl/resource e compilador
  C++ ausente no Wine. O workflow Windows tem teste C++ do hook com compilador real.
- O XEX e os saves humanos foram preservados; testes usam perfis separados.

## Critérios ainda necessários para aprovar stable

1. Navegação e gameplay do ilimitado, incluindo sair/carregar uma partida;
   relógio da simulação, física, animações e combate em velocidade correta.
2. Teste real em Windows: gerar a partir do dump, executar D3D12, preparar IA,
   controles, saves e os três alvos de FPS. Wine não substitui isso; não houve CI
   nesta revisão.
3. Repetir cenas com cache frio/quente, registrar pausas e demonstrar melhora;
   não anunciar eliminação de stutter com os dados atuais.
4. Sessões prolongadas e progressão além da abertura, incluindo transições,
   morte/recarregamento, sombras, áudio/sincronia e fechamento normal.
5. Validar os executáveis finais, integridade, atualização preservando o usuário,
   compilação Windows do SDK e teste do hook. Manter 30 FPS como padrão.

Enquanto esses critérios estiverem pendentes, usar prerelease e manter 60 FPS e
ilimitado identificados como experimentais. Não trocar ilimitado por limite
oculto nem declarar estabilidade apenas porque o processo terminou com código 0.
