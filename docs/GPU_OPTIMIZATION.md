# GPU — investigação de 22/10/2026

## Mudança

O SDK escolhe `VK_PRESENT_MODE_IMMEDIATE_KHR` antes de mailbox/FIFO, mesmo com
`vsync=true`: o controle de vblank do guest e a apresentação no monitor são
independentes. Fonte: `src/ui/vulkan/vulkan_presenter.cpp`, seleção da swapchain,
no SDK local v0.10.0. As tentativas registram o modo realmente selecionado.

O launcher agora pede FIFO quando VSync está ligado. O pedido de mailbox nos
experimentos também selecionou FIFO nesta máquina (modo 2 nos logs). Mailbox
efetivo não foi testado. Isso usa os controles existentes do SDK e
mantém o vblank do guest, FSI, escala interna 1x, filtro de textura, MSAA, sombras,
cache e compilação assíncrona. Nenhum limite de FPS do jogo foi removido.
A escolha original pode ser restaurada com:

```sh
python3 scripts/play_green_lantern.py --vsync on --present-mode auto
```

Com `--vsync off`, a escolha original de apresentação continua sendo o padrão;
essa opção também altera o temporizador de vblank e permanece experimental.

## Evidências

- 034/035, checkpoint parado: agrupamento de submissions reduziu 83,00% para
  82,25% e 70,12 W para 69,68 W. Diferença insuficiente para adotar esse ajuste.
- 040, timestamps opt-in: cerca de 10 ms por swap no checkpoint, com utilização
  global aproximadamente 83,5%/69,57 W. As marcações cobrem os command buffers do
  processador gráfico do guest; não medem todo o trabalho do presenter/compositor
  e podem incluir esperas. Não equivalem à ocupação dos shaders nem a FPS únicos.
- 041/042/046 reduziram consumo no título, mas não entraram em gameplay: teclas X11
  eram enviadas sem foco real no Niri. Não comparar esses resultados com gameplay.
- 043, pedido de mailbox com FIFO efetivo e plugin instrumentado: checkpoint Lv.2, movimento/pulo enviados,
  sem fatal/destino não registrado. Amostras entre 120 e 140 s: 35,33% e 43,88 W.
- 044, FIFO efetivo e plugin normal: combate com inimigos, movimento/ação enviados e
  retorno 0; 60–100 s: 41,14% e 48,28 W. O save de teste havia avançado, portanto
  esse trecho confirma funcionamento, mas não é o par controlado de 034/040.

Todas as porcentagens e potências são da placa inteira, com outros aplicativos
ativos. Os números não atribuem uso exclusivamente ao processo do jogo. As limitações da comparação aparecem abaixo. Outras cenas/GPUs ainda precisam
de validação.

## Resultado integrado

**152 testes passaram, zero falhas/skips**, em cerca de 4 s, na rodada atual com
Xvfb 1440×900. A validação do launcher com o plugin principal passou nos três
alvos. Não houve recompilação/substituição do executável CPU ou do plugin
principal nesta etapa; a mudança integrada são os argumentos Vulkan de
apresentação, os presets e os builds experimentais isolados. O plugin
instrumentado fica somente no build de teste.

| Trecho observado | Modo efetivo | GPU global média | Potência média |
| --- | --- | ---: | ---: |
| 034, checkpoint parado, 80–100 s | imediato (0) | 83,00% | 70,31 W |
| 045, combate, 80–100 s | imediato (0) | 84,25% | 70,12 W |
| 047, checkpoint parado, 108–128 s | FIFO (2) | 34,75% | 42,92 W |
| 044, combate, 60–100 s | FIFO (2) | 41,14% | 48,28 W |

A cadência de chamadas de apresentação nesses intervalos ficou em aproximadamente
30/s. Isso não prova quantos quadros únicos chegaram ao monitor. Não houve
redução intencional de resolução, texturas ou sombras para obter esses números.
XEX e saves humanos continuam iguais aos hashes/backup anteriores.

## Alvo 60 opt-in

Na validação pareada 055/056, com o mesmo build e perfil, a telemetria global
entre 60 e 200 s foi de aproximadamente 31,67%/39,33 W no alvo 30 e
57,41%/56,98 W no alvo 60. O alvo 60 dobra as chamadas de renderização e os
subpassos. Ele está disponível como **alvo opt-in na aba Gráficos** do launcher,
com perfil isolado e aviso; não é o padrão nem FPS livre. Na sessão humana 058, a
mediana global foi 67,5%/58,72 W (82 amostras; 69,0%/59,03 W após 60 s), mas a
cena/atividade não foi pareada com 30 fps. Veja
[FPS_PROGRESS.md](FPS_PROGRESS.md).

## Presets gráficos e alvo ilimitado

Os presets **Baixa/Média/Alta/Ultra** mudam a resolução interna (1x/2x/3x), MSAA,
filtragem anisotrópica, limites do cache de texturas e dithering por CVars reais.
**Média** conserva os valores anteriores (720p interno, MSAA 2x, aniso 4x,
cache 384/768/24 MB). **Alta** e **Ultra** renderizam em 1440p/2160p internos e
aumentam o cache de texturas; ainda não há medição pareada de GPU/VRAM nem
avaliação humana desses presets. O guia completo está em
[GRAPHICS_PRESETS.md](GRAPHICS_PRESETS.md).

O alvo ilimitado v10 usa VSync desligado e apresentação imediata. No probe
`unlimited-gameplay-003`, de 90,16 s em FSI, foram 38.627 apresentações
(428,4/s), sem fatal, com a simulação em alvo 60 e tempo real. A GPU global ficou
em 95–96% e aproximadamente 91–107 W nas amostras finais. São números da placa
inteira, coletados em menu/atratores e em um trecho não confirmado visualmente;
não são um benchmark de gameplay. O modo pode causar tearing e não garante velocidade
correta de física, animações ou áudio. A referência é
`.aster/reports/rexglue-runtime-probe-unlimited.json` e o build
`.aster/build/rex-fps-unlimited-v10/aster_green_lantern` (SHA-256
`2e9069aa99ac8bce65f70c01149ec696d253922b92a4cba2cb29b09bcb9955f1`).

O par 045/046 com cópias idênticas de perfil foi **inconclusivo**, porque 046
permaneceu no título. Em 047 a sequência de entrada foi adiada 28 s e uma espera
curta após o pedido de foco permitiu entrar no checkpoint. Embora 045/047 partam
do mesmo backup, as capturas mostram momentos diferentes (combate/checkpoint):
não são um benchmark determinístico. A tabela contém observações locais por
cena, com animação/atividade do desktop variáveis e poucas amostras por intervalo;
não é promessa de redução uniforme durante a campanha.

Relatórios locais: `gpu-presentation-results.json` guarda as amostras resumidas,
modos e limites; `gpu-controlled-comparison.json` marca o par inicial inválido;
`gpu-optimization-deployment.json` registra integração, hashes e rollback.
As referências de execução do launcher são 047 (30 fps), 057 (60 fps) e
`unlimited-gameplay-003` (ilimitado), todas com o plugin do cache
2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249.

## Instrumentação e reprodução

`scripts/probe_rex_runtime.py` acrescenta `--primary-submit`, `--gpu-timing` e
`--present-mode`, mantendo a escolha original do SDK por padrão nos probes.
O patch `integrations/rexglue/patches/0002-vulkan-submission-timing.patch` registra
submissions concluídas, swaps e tempo entre timestamps Vulkan a cada cinco
segundos. É opt-in, sem waits adicionais de fence, com suporte/validBits checados,
queries por command buffer e leitura somente após a fence já existente concluir.
O plugin instrumentado permanece em `.aster/build/rex-green-gpu-test`; ele não
substitui o plugin principal validado do cache.

O helper de entradas dos probes verifica o PID X11 antes de qualquer ação e,
no Niri, exige correspondência única de título/classe para focar a janela do teste.
O compositor pode informar o PID do Xwayland, não o PID do jogo. Foco, teclas e
capturas ficam registrados. A sessão humana 027 está encerrada e o acompanhamento
continua pausado; não houve entrada automática em sessão humana.

## Resíduos de memória compartilhada

As tentativas 036–039 encerraram com SIGBUS, inclusive com o plugin normal e
antes de inicializar o plugin. O depurador apontou a arena de memória do runtime.
A auditoria fora do sandbox encontrou 41 arenas `xenia_memory_*` órfãs, ocupando
13.337.702.400 bytes; somente arquivos do mesmo usuário, com inode conferido e
sem mapas de processos associados foram removidos com autorização.
O teste 040 voltou a funcionar com o mesmo plugin instrumentado de 036.

As execuções 055/056 deixaram novas arenas `xenia_memory_*`; a limpeza não foi
feita nesta rodada e exige auditoria de inode/mapas e autorização, como antes.
O SDK usa `std::_Exit(0)` no encerramento, sem executar a limpeza normal dessas
arenas POSIX. O vazamento de temporários não foi corrigido no runtime nesta
rodada; a instrumentação não é uma correção desse problema. Não limpar `/dev/shm`
genericamente. Auditoria, identidades e remoção ficaram nos relatórios locais
`shm-orphan-audit.json` e `shm-orphan-cleanup.json`. Saves, shaders e XEX foram
preservados. O sandbox apresenta um `/dev/shm` diferente do ambiente real.
