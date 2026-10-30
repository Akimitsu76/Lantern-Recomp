# Aster Native

Framework experimental de portabilidade e launcher desktop original, com módulo
inicial para **Green Lantern: Rise of the Manhunters (Xbox 360)**.

**Port experimental, ainda sem validação completa de jogabilidade.** O host
Linux com ReXGlue/Vulkan alcança título, menus, abertura e a primeira fase com
HUD, cenário/personagens visíveis, combate inicial e passagem dos primeiros
destroços até o tutorial de defesa. Há sinal de áudio medido no stream do jogo. O modo
Vulkan FSI corrigiu a geometria preta nas cenas testadas; o padrão FBO falhou. A revisão
das mudanças do OpenCode corrigiu o analisador e isolou 21 limites de função
não comprovados. Veja [a revisão](docs/OPENCODE_REVIEW.md) e o
[estado de jogabilidade](docs/PLAYABILITY.md).

## Slots no menu — integração 24, v0.1.4-rc.5

**New Game** e **Continue** abrem um seletor de seis campanhas dentro do jogo.
O Slot 1 preserva o save existente; os demais têm armazenamento separado por
usuário, compartilhado entre as configurações gráficas e de FPS. Iniciar sobre
um slot ocupado exige confirmação e backup. Após atualizar o launcher, use
**Gerar port/Atualizar port** uma vez para instalar o backend 24.

As fontes são comuns ao AppImage e ao .exe. A troca de campanhas foi testada no
Linux; o launcher Windows abriu em Wine, mas gameplay D3D12 nativo ainda precisa
de validação. O aviso original de sobrescrita pode aparecer também em slot
vazio. Veja [funcionamento e limites dos slots](docs/SAVE_SLOTS.md).

## Integração 23 e cache de texturas — v0.1.4-rc.4, 29/10/2026

Esta pré-release experimental reúne o launcher da rc.3 e o backend de integração
23, com o patch 0034. O patch mantém até 128 MiB de DDS e metadados de mip já
validados em um cache LRU em RAM. Ele evita repetir leitura e hash quando uma
textura perde todos os donos na GPU e sua fonte ainda cabe no cache. Não amplia
VRAM, não carrega a biblioteca inteira, não elimina o primeiro carregamento nem
o upload para a GPU, e a criação de um pipeline inédito ainda pode pausar a
apresentação. Veja as [notas da rc.4](docs/RELEASE_v0.1.4-rc.4.md) e o
[progresso gráfico](docs/GRAPHICS_PROGRESS_2026-10-29.md).

Os controles 197/198/201, entre 100–170 s, tiveram medianas de apresentação de
16,830/16,833/16,833 ms, máximos abaixo de 18 ms e nenhum intervalo acima de
25 ms. São timestamps de apresentação, não tempo de GPU nem prova de campanha.
O experimento 202 eliminou o teto do título, mas ficou preso em “Press START”;
não foi integrado. A interface/legendas em resolução própria continua um
protótipo privado, sem instalação no backend público.

Quem vem da rc.3 precisa trocar o launcher e usar **Gerar port/Atualizar port**
para receber a integração 23; saves, cache e preferências são preservados. A
suíte completa passou com 474 testes e 3 skips opcionais. Windows nativo/D3D12, campanha
completa e o tutorial do Disparo do Anel continuam sem validação; não é stable.

## Histórico de FPS e portabilidade — 24/10/2026

Naquela revisão experimental, 60 FPS voltou a alcançar a fase no Linux, mas havia
engasgos; a navegação do ilimitado não foi validada. Corrigidos progresso/cancelamento
da compilação no Windows e leitura UTF-8. Gameplay Windows nativo continua pendente.
Veja os [resultados e critérios para stable](docs/RELEASE_READINESS.md).

## Gráficos e texturas por preset — 24/10/2026

O menu **Gráficos** reúne Baixa, Média, Alta e Ultra, resolução até 4K
(incluindo 1920×1080), tela cheia, FPS, VSync, FXAA, FSR 1 com nitidez e
filtragem anisotrópica. Alta prepara materiais revisados em 2×; Ultra em 4×.
A preparação parte do dump do usuário antes da partida, com cache verificado
e inferência compartilhada entre presets. Baixa/Média usam os originais.

**Cobertura HD: 253 materiais difusos opacos revisados, com usos nas dez
missões e em recursos compartilhados.** Outros materiais mantêm os originais. Não é um remaster completo. A implementação é comum a
Linux/Windows; Wine valida o launcher, não certifica gameplay D3D12.
Veja [texturas e limites](docs/HD_TEXTURES.md).

## Launcher e atualização integrada — 28/10/2026

A interface do launcher foi renovada com navegação Início/Gráficos/Preparar/Jogo/
Diagnóstico/Atualizações, ajustes rápidos e ações de Salvar/Jogar no rodapé. A
preparação mostra o avanço geral separado da etapa atual. As fontes DejaVu
acompanham os executáveis; no Linux, o AppImage usa Tk 9.0.4 recompilado com Xft.

A nova aba **Atualizações** consulta os releases públicos, avisa quando há versão
maior, permite incluir pré-releases, baixa o AppImage/EXE da plataforma e confere
tamanho, formato x64 e SHA-256 antes de instalar. O launcher guarda a versão
anterior, reinicia e restaura o backup se a nova interface não iniciar. O backend
do jogo não é atualizado automaticamente, e saves, cache, preferências e dump são
preservados. Veja [launcher](docs/LAUNCHER.md),
[atualizações](docs/LAUNCHER_UPDATES.md) e as
[notas da v0.1.4-rc.3](docs/RELEASE_v0.1.4-rc.3.md).

Esta é uma pré-release experimental do launcher, não stable. Ela não certifica a
campanha, não corrige o tutorial do Disparo do Anel e não valida Windows nativo:
o EXE foi exercitado sob Wine. O jogo segue pausado até confirmação do usuário.

## Revisão local de fontes e apresentação — 27/10/2026

O FXAA Vulkan foi corrigido para preservar melhor os contornos das letras,
com FSR ainda ligado. O caminho D3D12 mantém seu FXAA Quality já existente.
A conexão de apresentação também passou a atualizar tamanhos nativos repetidos,
resolvendo no teste local as barras laterais indevidas após entrar em tela cheia.
O backend atualizado usa os patches até 0032, integração 21; instalações anteriores
precisam de **Gerar port/Atualizar port** para receber a correção, além de trocar
o executável do launcher. A revisão r4 verifica a versão/correções tanto
na interface quanto no comando de execução em Linux/Windows, e informa no log
o backend efetivamente instalado.

A fonte original ganhou um formato RGBA8 opcional que preserva o alpha sem nova
compressão BC3; continua uma experiência CLI. Todos os efeitos e legendas da
campanha ainda precisam de revisão. Pipelines inéditos continuam podendo pausar
no primeiro uso; as experiências de compilação que não trouxeram ganho útil foram
mantidas fora da produção. Veja [estado e limitações](docs/RESUME_CHECKPOINT.md)
e as [notas da candidata v0.1.4-rc.2](docs/RELEASE_v0.1.4-rc.2.md).
Os pacotes desta revisão são os assets da pré-release experimental v0.1.4-rc.2;
ela não é stable.

## Candidata v0.1.4-rc.1 — 27/10/2026

Esta é uma **pré-release experimental**, não stable. O patch 0027 remove uma
espera indevida por workers no fim da submissão Vulkan em modo assíncrono,
preservando o caminho bloqueante, os flushes de cache e a sincronização de
shaders com efeitos na memória. O patch 0028 repete uma única vez o pedido de
tela cheia no primeiro foco quando ele foi descartado na abertura. Duas sessões
de dez minutos em 60 FPS alcançaram tutorial/combate inicial sem falha fatal ou
de renderização detectada; cache aquecido reduziu pausas, sem eliminá-las.
A sessão 156, repetindo a 153 com o cache aprendido, caiu de 517,57 ms para
33,90 ms de pausa máxima entre 100–170 s e de 1 para 0 criações de pipeline,
sem intervalo acima de 50 ms nessa repetição. São cenas curtas, não a campanha.
Veja os [testes e limites atuais](docs/RELEASE_READINESS.md) e as
[notas da candidata](docs/RELEASE_v0.1.4-rc.1.md).

As mudanças até 26/10 correspondem à pré-release experimental **v0.1.3**,
preservada no histórico. O build usa um único perfil de usuário para todos os
alvos de FPS, gráficos personalizados independentes e pré-compilação opcional do
cache de shaders conhecido. A geração oferece preparação de dependências pelos
gerenciadores oficiais suportados. Veja [requisitos e
limites](docs/PORTABLE_BUILD.md), [validação visual](docs/VISUAL_QUALITY.md) e
as [notas da v0.1.3](docs/RELEASE_v0.1.3.md).

O patch 0024 corrige a leitura de profundidade em 2x/3x nas duas traduções
SPIR-V/DXBC; o 0025 pré-compila shaders conhecidos antes de jogar; o 0026
reutiliza o pipeline final do presenter Vulkan em vez de recriá-lo a cada
apresentação. No controle local de abertura em 1440p interno e saída 1080p, a
mediana passou de 24,80 para 44,28 apresentações Vulkan/s, com 1.232→0 criações
de pipeline nas janelas de 5 s após 100 s. É uma medição curta da abertura, não
um benchmark universal. A campanha completa e a GPU Windows nativa permanecem
sem certificação; não há ganho acima de 60 FPS comprovado nem escala interna
1080p (1,5x).

## Launcher portátil e geração local

Na pré-release v0.1.4-rc.4, os downloads diretos são
`AsterNative-windows-x64.exe` e `AsterNative-linux-x86_64.AppImage`: cada um é um
arquivo único, sem ZIP para extrair. Recursos e dados persistentes ficam na
pasta de dados do usuário. Os formatos anteriores ZIP/TAR.GZ não são
necessários para esta entrega. `SHA256SUMS` e `LEIA-ME-ATUALIZACAO.md` acompanham
os executáveis.

O launcher gera e compila o host a partir da pasta extraída do jogo, verifica a
revisão do XEX e reutiliza builds íntegros. Incluem Python/Tk e CMake/Ninja; a
toolchain C++23 continua necessária para gerar o port. Não incluem jogo nem
código recompilado. Veja [instalação e requisitos](docs/PORTABLE_BUILD.md).

Corrigidos: VSync off acelerando o relógio guest nos alvos 30/60, falso controle
de MSAA, botão Cancelar invertido e validação ignorando destinos não registrados.
A geração e inicialização Linux foram testadas; o launcher Windows abriu no
Wine. A compilação e o jogo Windows ainda exigem validação em Windows real.

## Atualização gráfica

Cache persistente do driver Vulkan integrado e testado em duas aberturas, com
recuperação de arquivo corrompido. Pipelines novos são preparados por workers;
tradução de shaders inéditos ainda pode causar engasgos. Os conhecidos podem
ser preparados na entrada pelo controle de pré-compilação. A apresentação sincronizada FIFO
reduziu o uso observado da GPU de cerca de 83–84%/70 W para 35–41%/43–48 W em
trechos locais, mantendo a configuração gráfica. Já é o padrão com VSync ligado.
Outros trechos/GPUs, a avaliação humana subjetiva dos presets e a ocorrência
isolada de sombra continuam pendentes. A sessão humana 058 confirmou gameplay
real em 60 fps, combate, pausa, cutscene e carregamento; falta registrar a
percepção de física, animações, áudio e engasgos. Veja
[GPU_OPTIMIZATION.md](docs/GPU_OPTIMIZATION.md) e
[GRAPHICS_POLISH.md](docs/GRAPHICS_POLISH.md).

O launcher foi redesenhado com as abas **Jogar**, **Gráficos**, **Jogo e
arquivos** e **Diagnóstico**. A aba **Gráficos** oferece os presets **Baixa**,
**Média**, **Alta**, **Ultra** e **Personalizada**, além dos alvos **30 fps**,
**60 fps** e **Ilimitado**. **30 fps continua o padrão.** Os três alvos usam o
mesmo host gerado localmente e o mesmo save do usuário. Ilimitado desliga VSync
e usa apresentação imediata. Os dois alvos experimentais são opt-in e pedem
confirmação. As preferências do launcher ficam apenas em
`.aster/config/settings.json` (schema 2); nenhum preset grava no perfil do jogo.
Veja o [guia de presets](docs/GRAPHICS_PRESETS.md).

O alvo 60 opt-in foi medido em par com o alvo 30: o passo de simulação acompanha
o tempo de parede nos dois e o delta de ~2% é comum aos dois alvos. O alvo 60
alcançou o checkpoint Lv.2 sem fatal. Na sessão humana 058, as capturas mostram
combate, menu de pausa, cutscene e carregamento; a mediana foi 59,995
apresentações/s, com seis janelas de 5 s abaixo de 59. O modo ainda não é FPS
livre nem certificação de física, animações ou áudio.

Os números antigos de apresentação do v10 são históricos e não demonstram
gameplay acima de60FPS. A validação atual conta chamadas reais do presenter
Vulkan e captura apenas a janela do processo de teste. Veja
[limites atuais](docs/VISUAL_QUALITY.md); [FPS_PROGRESS.md](docs/FPS_PROGRESS.md)
preserva a investigação anterior.

## Estado em 23/10/2026

- Núcleo Python sem dependências pip: inspeção estrutural XEX2/XDVDFS, SHA-256,
  relatórios, diretórios limitados ao projeto, API de módulo v1 e cancelamento.
- Launcher Tk: seleção de pasta extraída, ISO ou XEX, inventário de assets,
  diagnóstico, tarefas reais, logs exportáveis e cancelamento. Preferências de
  diretório de trabalho, presets e alvo persistentes; limpeza confirmada do
  cache. Compilar/iniciar completos continuam desabilitados. **Jogar agora** abre
  o build local após validar dump, build, plugin e referência FSI. O alvo e o
  preset ficam na aba **Gráficos**; 30 fps é o padrão, e 60/ilimitado são opt-in
  com confirmação e perfis isolados.
- Utilitário C++ próprio compilado e executado para verificar o compilador local.
- ISO inicial sem assinatura XDVDFS. Nova pasta extraída fornecida pelo usuário:
  XEX identificado como Green Lantern, 135 arquivos / 3,60 GB. O XEX declara
  criptografia e compressão basic; decodificação local concluída após autorização.
- XenonRecomp compilado localmente; Ghidra identificou 12.534 funções, com
  limitações documentadas. Imports resolvidos: 451 registros / 232 APIs distintas.
- ReXGlue v0.10.0: análise passou com hints próprios, sem `--force`; executável
  Linux compilado. Menus respondem ao teclado; perfil local foi criado e lido
  novamente. Combate, destruição de obstáculos, tutorial de defesa e retomada após derrota
  foram observados com FSI. Há saída de áudio não nula atribuída ao jogo; qualidade
  e sincronia, campanha completa e outras GPUs continuam sem validação.

## Uso direto, sem instalação

Na raiz deste projeto:

```sh
python3 -m native_port doctor
python3 -m native_port gui
python3 -m native_port inspect '/caminho/jogo.iso'
python3 -m native_port prepare '/caminho/pasta-do-jogo'
python3 scripts/survey_image.py '/caminho/jogo.iso'
python3 scripts/host_probe.py
python3 -m unittest discover -s tests -v
xvfb-run -a -s '-screen 0 1440x900x24' python3 -m unittest discover -s tests -v
```

Também pode executar `./apps/launcher/aster-native` a partir da raiz.

Para abrir a **compilação experimental local já testada**, com teclado e Vulkan FSI:

```sh
python3 scripts/play_green_lantern.py
```

O comando usa a pasta do último probe e verifica os hashes do XEX, do executável e
do plugin. Também aceita a pasta como argumento. Enter = Start, Espaço = A,
Backspace = B, WASD = stick esquerdo, L = X. Feche a janela para encerrar.
Logs/cache/saves ficam em `.aster/`. Presets e alvos também podem ser escolhidos
na linha de comando:

```sh
python3 scripts/play_green_lantern.py --graphics-preset high --validar
python3 scripts/play_green_lantern.py --graphics-preset high

python3 scripts/play_green_lantern.py --fps-target 60 --validar
python3 scripts/play_green_lantern.py --fps-target 60

python3 scripts/play_green_lantern.py --fps-target unlimited --validar
python3 scripts/play_green_lantern.py --fps-target unlimited
```

O alvo 60 usa o build v9; o alvo ilimitado usa o build v10, com VSync desligado
e apresentação imediata. Os dois compartilham o mesmo perfil/save do usuário em
`.aster/runtime/green-lantern/`; não existe save separado por alvo.
`--experimental-60fps` continua aceito como atalho antigo. O modo FSI exige
suporte a fragment shader interlock;
foi testado na RTX 5060 local. Isso não habilita o backend completo no launcher
Tk.

No launcher, clique em **Selecionar pasta do jogo…** e indique a pasta com
`default.xex` e os demais arquivos extraídos. Não mova somente o XEX para uma
pasta vazia: o jogo dependerá também dos seus assets. O botão **Jogar agora** só
habilita quando o build e a referência do alvo escolhido estão presentes; a aba
**Jogo e arquivos** mostra o que falta.

Python >=3.11; Tkinter/Tk para GUI; compilador C++17 para o utilitário opcional.
Use um terminal da sessão gráfica para abrir o launcher. Os testes da GUI usam
Xvfb; para capturar a janela inteira, use uma tela de pelo menos 1440×900.

`inspect` retorna 0 para estrutura reconhecida e 2 para erro. `prepare` retorna 3
quando salva preparação mas para no backend ausente; isso não significa jogo pronto.
Os resultados ficam em `.aster/`, ignorado pelo Git. `survey_image` lê a imagem
inteira para calcular hash e localizar assinaturas; pode levar tempo e aceita Ctrl+C.
Não faz descriptografia nem extração.

O CMakeLists da raiz cria somente `aster-host-probe` e foi configurado/compilado.
CMake 3.31.10 fica em `.aster/tools/cmake-runtime`; não altera o PATH global.
A integração de análise fica em `integrations/xenonrecomp`. Veja NATIVE_PROGRESS
e BUILD_PIPELINE para reproduzir o experimento.

## Documentação

- [Notas da v0.1.4-rc.4](docs/RELEASE_v0.1.4-rc.4.md)
- [Notas históricas da v0.1.4-rc.3](docs/RELEASE_v0.1.4-rc.3.md)
- [Launcher](docs/LAUNCHER.md)
- [Atualização integrada](docs/LAUNCHER_UPDATES.md)
- [Notas históricas da candidata v0.1.4-rc.2](docs/RELEASE_v0.1.4-rc.2.md)
- [Notas históricas da candidata v0.1.4-rc.1](docs/RELEASE_v0.1.4-rc.1.md)
- [Notas históricas da v0.1.3](docs/RELEASE_v0.1.3.md)
- [Arquivos únicos para Releases](docs/SINGLE_FILE_RELEASE.md)
- [Progresso nativo e evidências atuais](docs/NATIVE_PROGRESS.md)
- [Estudo dos ports indicados pelo usuário](docs/PORT_REFERENCES.md)
- [Licenças das ferramentas](docs/TOOLING_LICENSES.md)
- [Ambiente inicial](docs/ENVIRONMENT.md)
- [Viabilidade e fontes técnicas](docs/FEASIBILITY.md)
- [XEX real e avaliação do XenonRecomp](docs/XENONRECOMP_EVALUATION.md)
- [Arquitetura](docs/ARCHITECTURE.md)
- [Engenharia reversa](docs/REVERSE_ENGINEERING.md)
- [Pipeline](docs/BUILD_PIPELINE.md)
- [Módulos](docs/GAME_MODULES.md)
- [Desenvolvimento e testes](docs/DEVELOPMENT.md)
- [Resultados da validação](docs/VALIDATION.md)
- [Presets gráficos e alvo de FPS](docs/GRAPHICS_PRESETS.md)
- [Abrir a compilação experimental](docs/EXPERIMENTAL_PLAY.md)
- [Limitações](docs/KNOWN_LIMITATIONS.md)

Não adicione dumps, assets, código gerado proprietário ou chaves ao repositório.
Ferramentas de terceiros ficam isoladas em `.aster/tools`, com suas licenças.

Investigação atual de cadência e experimentos isolados: [FPS_PROGRESS.md](docs/FPS_PROGRESS.md).
