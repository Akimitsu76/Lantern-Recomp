# Preparação da release

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
