# Cadência da engine — investigação local em 22/10/2026

A versão jogável principal continua com CPU e plugin GPU preservados. O ajuste
FIFO anterior reduz trabalho de apresentação; não desbloqueia a cadência da engine.
Os experimentos abaixo usam executáveis e perfil separados em `.aster/`.

A validação pareada 30/60 de 055/056 confirmou que o alvo 60 preserva o passo de
simulação medido e que o desvio de ~2% do relógio de delta já existe no alvo 30.
Isso valida o passo, não o combate, a física, as animações ou o áudio.

## Evidência

- 048/049: chamadas de renderização estabilizam em cerca de 30/s após os vídeos.
  A apresentação `825AEB90` leva menos de 1 ms **somado em cinco segundos**;
  o frame `82141C18` leva aproximadamente 156–202 ms somados no mesmo intervalo.
  A espera ocorre fora dessas funções. Isso mede chamadas, não frames únicos exibidos.
- 051: wrappers de espera localizam o produtor no relógio da engine `82403998`.
- 052: `82402E38`, chamado por esse relógio, espera aproximadamente 33 ms por
  quadro quando o alvo global em `82836A24` vale 30. A função compara o alvo com
  31 e espera dois ou um incrementos do contador do callback `8247CE30`.
- O seletor original `82375A28` contém valores 25/50 e 30/60 conforme modo de
  vídeo. O contador e os relógios originais devem ser preservados.
- 055/056: com o hook v9, o alvo 30 e o alvo 60 mostram o mesmo delta de
  aproximadamente 1,0203 s/s e passo de simulação de aproximadamente 1,000.
  O alvo 60 dobra os subpassos e as chamadas de renderização. Veja a seção
  pareada abaixo.

## Ferramentas

`scripts/build_rex_experiment.py` compila um único hook e relinka os 114 objetos
CPU existentes em uma pasta nova. Confere os hashes dos objetos e dos artefatos
principais, copia as bibliotecas RD atuais e não executa geração de código ou
staging do build principal. O manifest registra comandos, hashes e fonte do hook.

`integrations/rexglue/experiments/frame_pacing.cpp` envolve funções originais e
imports, mede taxas/tempos e captura callers conhecidos sem sondar a pilha.
`--frame-diagnostics` habilita a observação no probe e no host experimental.
A opção `--fps-target 60` (ou o atalho antigo `--experimental-60fps`) é opt-in no
probe e no launcher: seleciona 60 quando a engine pede 30, mantendo a rotina
original de espera. `--fps-target unlimited` usa outro hook, que remove a espera
e força apresentação imediata. Nenhum dos dois é o padrão.
`ASTER_DELTA` mede o retorno do relógio de delta original por tempo de parede;
mesmo uma razão próxima de 1 não certifica física, combate ou animação completos.

## Tentativas rejeitadas e limites

- v1 teve RPATH incorreto e não abriu o jogo; builder corrigido.
- 050/v4 leu uma região não mapeada ao tentar percorrer a pilha e entrou em
  violações repetidas. Não é uma sessão bem-sucedida apesar do retorno 0 no
  encerramento. `reassessment.json` registra a falha, preservando relatório/logs.
  Essa leitura foi removida em v5. A análise dos logs agora reconhece violações
  de memória sem depender da marca literal `[FATAL]` e tem teste de regressão.
- Decompilação Ghidra dessas funções tem limites truncados por inferência
  incorreta de noreturn. O caminho foi confirmado no código privado recompilado
  e nas medições; não tratar o pseudo-C truncado como função completa.
- Há ações baseadas em frames no jogo. Ainda é necessário comparar deslocamento,
  duração de ataques, física, cutscenes e áudio antes de oferecer 60 como padrão.
- Saves humanos e XEX original não são usados como destino de escrita dos probes.
  Fontes derivadas, capturas e logs permanecem locais e privados.

## Primeiro experimento com alvo 60

O host v7 conserva os relógios e a espera originais e muda o alvo30 para60 somente
quando `aster_experimental_60fps` está habilitado (defaultfalse). 053 ficou no
Press START por entrada não aceita: evidencia menu a60, não gameplay.
054 repetiu Start e atingiu o checkpoint Lv.2. Capturas `window-24.png` e
`window-33.png` mostram fase e deslocamento; `live-104.png` mostra um ataque com
rastro verde. Movimento e oito pedidos de ataque foram registrados pelo probe.
Duração/correção dos golpes, combate completo e sincronização de áudio continuam
sem comparação controlada. Esse host não substitui a versão principal.

O probe rejeita esses experimentos com executável principal ou perfil humano,
e exige as duas pastas isoladas. A suíte atual tem 152 testes aprovados.

No trecho após105s de054,17 janelas somaram59,87 chamadas de frame/s
(intervalos59,21–60,01). O relógio de delta original somou1,02035s por segundo
de parede; a comparação com a mesma instrumentação em30 foi feita em055/056
(veja abaixo). Telemetria global:59,13% e58,93W (média de16 amostras), sem
comparação determinística entre cenas.
A sessão terminou em190,86s por prazo, retorno0, sem fatal/destino não registrado,
XEX intacto. Evidência privada: `.aster/reports/frame-pacing-results.json`.
CPU/plugin principais e saves humanos conferidos por hash; referência047
restaurada e `play_green_lantern.py --validar` aprovado. Nenhum probe permanece
ativo. Acompanhamento027 permanece pausado. Sombras ainda pendentes.

## Validação pareada 30/60 — 055/056

O host v9 acrescentou `ASTER_SIM` (passo de simulação) e `ASTER_STEP` ao hook
v7, sem alterar o delta. 055 rodou o alvo 30 e 056 o alvo 60 com o mesmo build,
o mesmo conteúdo e perfis byte a byte iguais (`fps-validation-profile-seed.json`).

| Medida | 055, alvo 30 | 056, alvo 60 | 054, 60 (v7) |
| --- | ---: | ---: | ---: |
| Janelas de 5 s | 40 | 46 | 37 |
| Chamadas de render/s (mediana) | 30,000 | 59,997 | 59,994 |
| Delta original (mediana) | 1,02038 | 1,02032 | 1,02036 |
| Passo de simulação (mediana) | 0,99993 | 0,99996 | não medido |
| Subpassos por janela (mediana) | 151 | 300 | não medido |
| GPU global 60–200 s | 31,67% / 39,33 W | 57,41% / 56,98 W | 57,12% / 56,94 W |
| Duração | 208,9 s (janela fechou) | 240,22 s (prazo) | 190,86 s (prazo) |

O delta de ~1,0203 é comum aos dois alvos: o desvio de ~2% do relógio original
não foi introduzido pelo alvo 60. O passo de simulação acompanha o tempo de
parede nos dois casos; o alvo 60 gera 300 subpassos por janela de 5 s, o dobro
dos 150 do alvo 30. 056 alcançou o checkpoint Lv.2 (`window-40.png`,
`window-50.png`), com 51 capturas, retorno 0, sem fatal/destino não registrado
e XEX intacto. A GPU global subiu de ~31,7%/39,3 W para ~57,4%/57,0 W na mesma
janela; é telemetria da placa inteira, não uma medição exclusiva do jogo.

Limites: as chamadas contadas não são quadros únicos exibidos; a duração dos
golpes, física, animações, cutscenes, áudio e campanha completa não foram
comparados de forma pareada por um humano. A sessão 058 posterior confirmou
gameplay e combate visual, mas não substitui essa comparação controlada. A
checagem de áudio em 120 s retornou sinal zero em 055 e 056; isso não valida
qualidade/sincronia. O desvio de ~2% contra um console físico continua sem
explicação. Evidência privada:
`.aster/reports/fps-validation-results.json`; capturas e logs em
`.aster/reports/rex-history/055-validation-30fps/` e `056-validation-60fps/`.

## Sessão humana 058 — 60 fps

A sessão humana **058-human-60fps** usou o build v9, FSI, o perfil isolado
`.aster/runtime/green-lantern-60fps/` e o mesmo caminho do launcher 60 fps. O
jogador abriu o checkpoint Lv.2, lutou, pausou, assistiu a uma cutscene e chegou
a um carregamento. A janela foi fechada pelo usuário após **412,04 s**; retorno
0, sem fatal/destino não registrado e XEX intacto. O perfil humano de 30 fps
permaneceu idêntico ao backup.

| Medida da sessão 058 | Resultado |
| --- | ---: |
| Janelas `ASTER_SIM` de 5 s | 81 |
| Alvo declarado | 60 em todas |
| Chamadas/subpassos por janela (mediana) | 300 / 300 |
| Delta `elapsed/wall` (mediana) | 0,999949 |
| Janelas `present` | 81 |
| Apresentações/s (mediana) | 59,995 |
| Apresentações/s (faixa) | 47,599–60,011 |
| Janelas abaixo de 59/s | 6 |
| Janelas abaixo de 55/s | 3 |
| Chamadas de present observadas | 24.340 |
| GPU global, mediana de 82 amostras | 67,5% / 58,72 W |
| GPU após 60 s, mediana de 70 amostras | 69,0% / 59,03 W |
| Capturas de janela | 28 |

As capturas mostram fase com HUD, combate com contador de golpes, menu de pausa,
cutscene e transição de carregamento. As quedas de 56–57/s ocorreram em uma
janela de combate com muitos efeitos; as de 50–51/s coincidem com uma transição
de cutscene e a de 47,6/s com carregamento/encerramento. A inspeção automática
não decide se esses engasgos foram perceptíveis; isso precisa do relato humano.
Também não há medição de qualidade/sincronia de áudio nesta sessão.

O alvo 60 continua opt-in, agora na aba **Gráficos** do launcher, com
confirmação e perfil isolado `.aster/runtime/green-lantern-60fps/`; 30 fps segue
como padrão. Ele não é FPS livre nem certificação de velocidade. A validação de
referência do launcher é o probe 057, preservado em
`.aster/reports/rexglue-runtime-probe-60fps.json`. A sessão humana 058 já foi
executada; resta registrar a percepção de golpes, física, animações, áudio e
engasgos antes de qualquer integração como padrão. Evidência:
`.aster/reports/rex-history/058-human-60fps/` e
`.aster/reports/rex-history/058-human-60fps/summary.json`.

## Alvo ilimitado — build v10

O build v10 fica em `.aster/build/rex-fps-unlimited-v10/aster_green_lantern`
(SHA-256 `2e9069aa99ac8bce65f70c01149ec696d253922b92a4cba2cb29b09bcb9955f1`)
e usa o hook `aster_experimental_unlimited_fps`. O modo força alvo 60 no relógio
da engine, ignora a espera de pacing em `sub_82402E38`, desliga VSync e solicita
apresentação imediata. O plugin gráfico continua
`2760fb7b285370737f78569e261b6ddc5e46afb0040a5fc44d29b50af15d4249`.

O probe final `unlimited-gameplay-003` rodou 90,16 s em FSI, com 38.627
apresentações observadas (média de 428,4/s), XEX carregado, eventos de teclado
enviados e nenhum erro fatal. `ASTER_SIM` mostrou `elapsed_s` aproximadamente
igual a `scaled_s` com alvo 60, ou seja, a simulação não acelerou no trecho
observado. A GPU global ficou em 95–96% e cerca de 91–107 W nas amostras finais.
Isso é telemetria da placa inteira, não um benchmark de gameplay.

Limites: o probe registra `gameplay_verified=false`; a captura X11 no Xwayland
não funciona nesta máquina e não há confirmação visual humana do trecho. O modo
pode causar tearing, esquentar/consumir mais GPU e não garante velocidade
correta em combate, física, animações ou áudio. A referência é
`.aster/reports/rexglue-runtime-probe-unlimited.json`; o perfil isolado é
`.aster/runtime/green-lantern-unlimited/`. O comando
`play_green_lantern.py --validar --fps-target unlimited` passou, exigindo as
flags experimentais, VSync off, apresentação imediata e média acima de 60/s. O
build duplicado criado por engano
(`rex-rex-fps-unlimited-v10`) foi auditado e removido; as arenas SHM não foram
tocadas.

## Launcher e presets

O launcher agora expõe presets **Baixa/Média/Alta/Ultra/Personalizada** e os
alvos **30/60/ilimitado** na aba **Gráficos**. As preferências usam schema 2 em
`.aster/config/settings.json`; schema 1 é migrado em memória e salvo como 2.
Nenhum preset ou alvo grava no save/perfil do jogo. O padrão restaurado nesta
máquina é 30 fps com preset Média. A suíte completa tem **152 testes aprovados**
em Xvfb 1440×900; `--validar` passou nos três alvos. Um probe curto do build
principal com preset Média (`preset30-default-001`, 12,52 s) carregou o XEX,
aceitou as CVars, fez 461 apresentações em FSI/FIFO e não teve fatal; `ready=false`
pelo prazo curto, então isso não é validação de gameplay. A avaliação visual dos
presets e a sensação de 60/ilimitado continuam dependendo do usuário.
