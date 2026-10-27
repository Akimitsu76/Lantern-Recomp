# Qualidade de imagem: estado da validação

Atualizado em 26 de outubro de 2026. Esta revisão corresponde à pré-release
experimental v0.1.3; os limites abaixo continuam valendo.

A resolução de saída e a resolução interna têm funções diferentes. A saída
1920×1080 está disponível em todos os presets. Baixa/Média usam 1280×720
interno; Alta usa 2560×1440 e Ultra usa 3840×2160. Em saída Full HD, Alta/Ultra
reduzem a cena maior, ajudando a suavizar bordas; isso custa mais GPU. O backend
aceita escalas inteiras de 720p, sem uma escala interna exata de 1920×1080.
Renderizar mais pixels não inventa detalhes nas texturas, fontes ou partículas.

No modo Personalizada, saída, escala interna, texturas, filtragem, AA e FPS
são independentes e persistem ao salvar/reabrir. Full HD com texturas Ultra não
obriga usar 4K interno. A implementação de 1,5× precisa adaptar endereçamento,
resolves e amostragem; trocar apenas o tipo do seletor produziria resultado
incorreto.

Controle local 141: 720p interno, saída 1080p, ilimitado, cache quente, sem
AA/AF, 150 s, movimento na plataforma inicial e cerca de 60 apresentações
Vulkan/s. Controles anteriores 2× na mesma abertura ficaram perto de 22–25/s.
Isso não certifica 60 FPS na campanha nem ganho acima de 60. FBO e desativar
submissão por buffer primário não resolveram o desempenho; FBO também corrompeu
a imagem.

Correção posterior, patch 0026: o presenter Vulkan não guardava o formato do
pipeline final criado com sucesso. Isso provocava espera pela GPU e recriação
em cada apresentação. O formato agora é guardado; mudanças reais de formato
mantêm a espera necessária, e falhas de criação continuam sendo tentadas depois.
O teste C++ executa o ramo original e o corrigido, incluindo troca de formato,
resize compatível, dois efeitos e falha seguida de nova tentativa.

Comparativo local 142/143, saída Full HD, renderização 1440p, ilimitado,
sem AA/AF, cache copiado e mesma sequência de entradas: nas janelas de cinco
segundos após 100 s, a mediana passou de 24,80 para 44,28 apresentações Vulkan/s.
O contador de criações de pipeline nessas janelas passou de 1.232 para 0.
No teste 144, modo 60 com FSR 1/FXAA/8×, a mediana foi 43,70/s. Todos terminaram
após 150 s, código 0, sem fatal/destino não registrado e com XEX intacto.
As imagens revistas do 143 mostram cenário e movimento íntegros. O 144 valida
aceitação/execução das opções, sem certificação visual completa dos efeitos ou
uso de texturas HD: nenhum pack foi anexado nesse controle. Ainda faltam 60 FPS
estáveis em 2×, campanha e Windows nativo. D3D12 já cria os pipelines finais
durante a preparação e não apresenta esse mesmo defeito de formato no código.

## Preparação dos shaders

O patch 0025 acrescenta **Pré-compilar shaders conhecidos antes de jogar**
(padrão ligado), compartilhado entre Linux e Windows. Dois controles Linux de
35 s, 139/140, confirmaram término sem fatal, XEX intacto e preservação integral
dos bytes originais dos caches com a opção ligada e desligada. O modo desligado
acrescentou receitas sob demanda sem truncar os arquivos. Isso não comprova
ausência de engasgos: a tradução de variantes inéditas ainda é síncrona, mesmo
quando pipelines são preparados por workers. A pré-compilação abrange o cache
conhecido; não cobre automaticamente toda a campanha ou um driver diferente.

Esses valores exigem o SDK com o patch 0024. Builds anteriores recebem uma
mensagem para atualizar o port quando 2×/3× é solicitado; a escolha não é mais
silenciosamente reduzida para 1×. O seletor de escala interna também está no
launcher, junto às opções de imagem, e é compartilhado entre Linux e Windows.

## Nitidez

Novas configurações usam nitidez FSR 30. A opção **Equilibrada**, ao lado do
controle, aplica esse valor às preferências existentes. Valores escolhidos pelo
usuário são preservados. Aumentar a nitidez pode acentuar contornos serrilhados,
compressão e granulação dos efeitos; não aumenta sua resolução de origem.

## Fontes e transparência

Há um caminho experimental separado para um atlas monocromático de fontes.
Ele extrai os dados do próprio dump, verifica suas identidades, preserva as
métricas e processa cada célula de glifo separadamente. A preparação mantém
transparência e não usa a reconstrução por IA aplicada aos materiais opacos.

O backend Linux já selecionou o atlas 2× durante uma sessão de gameplay.
Isso confirma o uso do recurso preparado; ainda não comprova melhora visual
sobre a filtragem original. O menu contém outros recursos de texto que esse
atlas não abrange. Por isso a preparação de fontes permanece experimental e
não é ativada automaticamente pelos presets.

Com o código-fonte, o diagnóstico pode preparar o recurso localmente:

```sh
python3 -m native_port texture-ui-prepare /caminho/Green_Lantern --scale 2
```

O comando informa o diretório do pack. A opção experimental
`--ui-texture-pack /caminho/do/pack` do script de execução valida esse diretório
antes de passá-lo ao backend. Os arquivos preparados pertencem ao usuário e não
devem ser incluídos no repositório ou nos releases.

## Rastros e partículas

Foi identificado um atlas de efeitos com transparência e sem cadeia de mips.
Sua imagem contém muitas células pequenas de animação. Ampliar esse recurso
como uma textura opaca pode danificar transparência, bordas e encaixe das
células. A resolução do atlas, a filtragem e o estado de composição de cada
desenho precisam ser distinguidos antes de instalar uma substituição.

Uma sessão isolada em 1× identificou um atlas BC3 de 1568×1568 usado em
gameplay. No desenho registrado, o backend selecionou filtragem linear em
minificação e magnificação, com teste de alfa do renderizador e alfa para
cobertura desligados. O shader desse desenho contém uma instrução de descarte
própria (`kill_gt`); desligar o teste de alfa do renderizador não elimina esse
descarte. Seu limiar efetivo ainda não foi medido. Esse resultado não cobre
todos os efeitos nem mede a resolução do alvo de composição na GPU.

## Escala interna

Antes do patch 0024, as áreas pretas em 2× foram reproduzidas em sessões isoladas com:

- filtragem anisotrópica desligada;
- FSR e FXAA desligados, com saída de 2560×1440;
- leitura de volta dos resolves ligada;
- caminho alternativo FBO;
- cache de shaders inicialmente vazio e compilação síncrona;
- ajustes de coordenadas de texturas escaladas desligados;
- resolução de saída e modo do convidado mantidos em 720p.

Esses controles não corrigiram o defeito. Limpar o cache não deve ser
apresentado como solução.

O replay da captura 120 localizou a mudança incorreta na profundidade no passe
9530. O código de parâmetros de pixel dividia o endereço inteiro do pixel do
host pela escala, mas preservava o deslocamento de meio pixel inteiro esperado
pelo shader do jogo. Em 2× isso fazia a cópia ler o pixel vizinho. O patch 0024
aplica a fase `0.5 / escala - 0.5` após a divisão, nos emissores SPIR-V e DXBC.
O caminho 1×, o teste de profundidade e a ordem dos desenhos são preservados.

No controle da mesma captura, corrigir somente X ou somente Y deixou defeitos;
corrigir ambos recuperou piso e cenário. Em cinco pontos pares/ímpares medidos,
a profundidade restaurada passou a coincidir com a pré-passagem. As sessões
Linux 133 (2×, modo 60, saída 1080p, bilinear) e 134 (3×, modo 60, saída 1080p,
FSR 1/FXAA) alcançaram a plataforma inicial e movimentação com o cenário
recuperado, sem falha fatal ou destino não registrado. Ambas saíram normalmente
pelo prazo do teste, com XEX intacto. São testes visuais limitados; não provam
60 FPS constantes, toda a campanha, todos os efeitos ou desempenho superior.

Validação de código em 26/10/2026: 379 testes Linux (1 ignorado) com Xvfb e
353 contratos Windows sob Wine (25 ignorados). O teste C++ do presenter executa
os blocos reais de ambos os backends, incluindo escalas 1/2/3 e assimétricas. A
compilação e a GPU nativas de Windows precisam ser verificadas em máquina
Windows; não houve CI nesta revisão. Wine não substitui uma partida nativa.

O código comum contempla Vulkan e D3D12. Testes do launcher e dos contratos
Windows sob Wine não substituem uma partida nativa em Windows. A validação
atual também não certifica a campanha inteira nem a ausência de engasgos.

## Preparação de shaders e engasgos

O patch 0021 corrige duas condições do pré-carregamento D3D12: a criação de
trabalhadores temporários e a espera pelo último trabalho em andamento quando a
inicialização pede modo bloqueante. O teste C++ reproduz o retorno antecipado
anterior e verifica a espera corrigida. A alteração já faz parte da receita
comum; ainda falta validar sua compilação e execução gráfica em Windows nativo.

No Vulkan, os pipelines conhecidos já são preparados antes de liberar a thread
principal do jogo. Durante a partida, criar pipelines novos é assíncrono, mas
traduzir variantes inéditas de shaders ainda pode ocupar a thread de comandos.
Além disso, quadros que contêm desenhos ainda pendentes não são apresentados:
o último quadro completo permanece visível. Desligar essa proteção não constitui
correção, pois pode apresentar objetos ausentes e flashes.

Os arquivos persistentes de microcódigo, receitas e cache do driver têm papéis
distintos. Eles não equivalem a um cache persistente de todas as traduções
SPIR-V nem eliminam a preparação de conteúdo nunca encontrado. Não há validação
atual de gameplay sem engasgos.

## Apresentação e notificações ociosas

O patch 0022 impede que a notificação vazia de conquistas peça redesenhos
continuamente. Menus e notificações ativos preservam a animação; uma conquista
recebida por outra thread acorda a janela pela fila de eventos SDL. Contextos
que não usam essa implementação mantêm o comportamento anterior. A alteração
exige reconstruir SDK e host juntos, pois muda interfaces e layouts da UI.

Em dois testes Linux sequenciais de 45 segundos, com o mesmo perfil copiado e
as mesmas configurações, um contador das chamadas reais `vkQueuePresentKHR`
mediu cerca de 4.744 apresentações/s na build anterior e 30/s na nova, no trecho
final da tela inicial. O jogo atualizava esse trecho a aproximadamente 30 Hz.
O modo usado foi **IMMEDIATE**; o launcher em FIFO já limita a apresentação à
sincronização da tela. Esses números medem apresentações redundantes e não uma
porcentagem de redução do uso de GPU. Não foi adicionado um limite de FPS.

O novo conjunto de SDK e host também executou cinco minutos de um teste Linux
em modo 60 FPS, alcançando a plataforma inicial com movimento e ataques, sem
erro fatal registrado. As imagens revisadas ficaram íntegras em 1×. Isso não
certifica a campanha, o ritmo da simulação, todas as animações ou Windows nativo.

## Evidência de renderização

Uma captura Vulkan isolada em 2× reproduziu a corrupção no início do jogo e
reteve os comandos produtores, além da apresentação final. Ela contém 4.127
ações e 183 texturas. A inspeção desses recursos está em andamento; a quantidade
de ações não mede FPS nem valida a correção visual. O diagnóstico usou RenderDoc
e desativou memória compartilhada esparsa por compatibilidade com a ferramenta,
portanto não é um benchmark de desempenho.

## Referências e diagnósticos opcionais

O diagnóstico opcional de efeitos verifica a identidade do atlas antes de
registrar amostragem e composição. Um índice local permite revisar fontes de
uma sessão sem ampliar a coleta a texturas desconhecidas. O patch 0020 acrescenta
até 16 registros de decisões por processo para distinguir recusas de geometria,
layout, estado, snapshot de CPU e identidade; mantém o teto de 32 snapshots e
todos os critérios de aceitação. Ele fica desligado na execução normal e não
altera filtros, shaders ou o estado de composição.

As técnicas e os limites encontrados nos ports indicados pelo usuário estão em
[GRAPHICS_REFERENCE_STUDY.md](GRAPHICS_REFERENCE_STUDY.md). A revisão do launcher
completo para Linux e Windows permanece como etapa posterior às correções e à
validação de jogabilidade, conforme a prioridade solicitada.

### Relógio virtual e VSync — investigação de 26/10

O teste 127 confirmou entrada na primeira plataforma, movimento/ataque e entrega de comandos em 60 FPS com VSync do SDK ligado. Ativar o hook ilimitado em runtime não elevou o ritmo observado acima de aproximadamente 60 atualizações/s nesse controle. O teste 128, com o mesmo binário e VSync desligado, recebeu Start e comandos de movimento no XamInputGetState, mas não avançou da tela inicial. Ambos encerraram pelo prazo do teste, sem erro fatal e sem alterar o XEX. Isso isola uma falha além da simples entrega de teclas sintéticas.

O SDK usava a mesma opção `vsync` para mudar os eventos de vblank do hardware virtual de aproximadamente 60 Hz para 1.000 Hz. O patch público 0023 preserva o relógio do modo de vídeo virtual ao desligar a sincronização de apresentação. O teste C++ executa os blocos originais e corrigidos com relógio controlado, incluindo mudança de VSync em execução e modos de 30/50/59,94/60/120 Hz. A validação dentro do jogo e no Windows nativo ainda precisa ser concluída; essa mudança não certifica FPS ilimitado nem desacoplamento da simulação.

Na investigação anterior de 2×, controles privados que impedem a pré-passagem de gravar profundidade faziam o piso reaparecer, mas alteravam a ocultação e não foram instalados. A correção posterior do patch 0024 trata as coordenadas da cópia; não usa esse desvio de profundidade. A instrumentação de máximos em uma região presumidamente livre do EDRAM também foi descartada como evidência conclusiva, pois essa região era reutilizada pelo jogo.

Validação local do patch 0023: SDK e host de integração 19 compilados e hashes da instalação conferidos. Suíte Linux: 362 testes, 2 ignorados; contratos de Windows sob Wine: 336 testes, 24 ignorados. O teste 129 terminou em 260 s, código 0, sem falhas fatais/destinos não registrados e com XEX intacto. Iniciou com ilimitado, mas Start continuou sem avançar. Ao desligar apenas o hook ilimitado em 77,449 s, mantendo VSync desligado, entrou na fase; salto e movimento foram observados. Reativar o hook em 177,421 s permitiu continuar a movimentação observada, porém o ritmo permaneceu perto de 60 atualizações/s. Isso valida uma melhoria do modo 60 sem VSync e mantém o ilimitado como defeito pendente. Evidências e limitações: `.aster/reports/visual-quality/vblank23-validation.json`. Nenhuma release foi publicada.

Atualização posterior — integração 20: o diagnóstico identificou o callback ativo `0x8247CE30`, um acesso ao contador em `0x82BA0348`. O hook passou a ajustar somente a comparação de pacing desse callback conhecido e a chamar a rotina original completa; callbacks desconhecidos preservam o caminho original. O host foi reconstruído por mudança no hash do hook. A sessão 131 iniciou com ilimitado e VSync desligado, avançou pelo menu e alcançou a plataforma inicial, movimento e animação de ataque, sem desligar o modo durante o teste. Em 260 s terminou com código 0, sem erro fatal/destino não registrado e com XEX intacto. Isso supera a falha de menu das sessões 129/130; não comprova ganho acima de 60 FPS, simulação correta em taxas maiores ou campanha completa. Evidência: `.aster/reports/visual-quality/pacing20-validation.json`. As suítes Linux (362/2 ignorados) e Windows sob Wine (336/24 ignorados) passaram novamente.
