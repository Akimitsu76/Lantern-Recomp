# Shaders, desempenho e sombras — 22/10/2026

## Atualização: presets, launcher e GPU

O launcher agora expõe presets **Baixa/Média/Alta/Ultra/Personalizada** e os
alvos **30/60/ilimitado** na aba **Gráficos**. Os presets usam CVars reais de
resolução interna, MSAA, anisotrópico, cache de texturas e dithering; o guia e a
tabela estão em [GRAPHICS_PRESETS.md](GRAPHICS_PRESETS.md). O preset **Média**
preserva a configuração principal anterior. **Alta/Ultra** e o alvo ilimitado
ainda precisam de avaliação humana pareada; não são otimizações certificadas.

A apresentação FIFO foi integrada ao launcher com VSync ligado. As observações
locais passaram de aproximadamente 83–84%/70 W para 35–41%/43–48 W em checkpoint
e combate, mantendo a configuração gráfica. **152 testes passaram** na suíte
atual, sem falhas/skips. As cenas são dinâmicas e a utilização é global da placa;
não é uma certificação de campanha ou de otimização completa. Veja
[GPU_OPTIMIZATION.md](GPU_OPTIMIZATION.md).

O alvo ilimitado v10 (VSync off, apresentação imediata) mediu 428,4
apresentações/s em 90,16 s, com GPU global de 95–96% e ~91–107 W, sem fatal; a
simulação manteve alvo 60/tempo real. O probe não confirma gameplay visualmente.
Veja [FPS_PROGRESS.md](FPS_PROGRESS.md).

Os resultados de cache abaixo são da rodada anterior (030–033).

## Resultado do cache

O plugin Vulkan recebeu um cache persistente do driver, além dos arquivos de
microcode/descrições que o SDK já mantinha. As opções do launcher preparam as
pipelines conhecidas antes de entrar e compilam novas em segundo plano por padrão.
O modo com espera também está disponível. Isso reduz trabalho repetido, mas não
elimina tradução CPU para SPIR-V nem garante zero compilação ou zero travadas.

A sessão humana 027 terminou após 2.152,17 s com retorno 0, sem fatal/destino não
registrado nos logs retidos e com SHA-256 do XEX preservado. O personagem chegou
a Lv.2; isso não significa missão 2. A cópia desse perfil retomou o checkpoint de
campanha em um processo novo no teste 031. O perfil humano foi preservado e os
testes seguintes usaram uma cópia em runtime separado.

## Cache implementado e testado

- Chave por GPU/driver/UUID/API/título/FSI-FBO; envelope com tamanho e checksum.
- Fallback vazio para cache inválido, limite de 64 MiB e substituição atômica.
- Snapshot após a preparação inicial e, havendo pipelines novas, a cada dez
  segundos na thread de armazenamento, além do caminho de encerramento normal.
  Os encerramentos observados não chamam sempre o destrutor do SDK, portanto
  depender somente dele não persistia o cache (evidência do teste 029).
- Teste 030 gravou 22.743.770 bytes de payload; teste 031 carregou esse payload.
  Preparação das 379 pipelines: aproximadamente 0,99 s em 030 e 0,54 s em 031.
  São tempos locais da etapa de armazenamento, não do boot inteiro, nem contadores
  de cache-hit do driver. Os mesmos handles Vulkan ainda precisam ser recriados.
- Patch preservado em `integrations/rexglue/patches/0001-vulkan-driver-pipeline-cache.patch`.
  O build isolado usa exatamente RelWithDebInfo, runtime/Tracy correspondentes,
  glslang fixado pelo SDK e os mesmos 35 arquivos GPU. Compilação e link sem
  símbolos ausentes passaram; 119 testes Python/Tk passaram sem falhas/skips.

O teste 028 carregou o plugin RD antigo e é somente baseline; o relatório
`028-driver-cache-cold/reassessment.json` corrige a identificação inicial. Os
probes novos registram nome e hash do plugin realmente indicado pelo loader.

Teste 033: um byte do cache isolado foi alterado. O checksum rejeitou o arquivo,
o backend iniciou com cache vazio e regravou um cache válido, sem fatal.
O plugin RD validado e o cache foram integrados ao launcher; o plugin anterior
e os saves humanos estão em `.aster/backups/` para recuperação.

## Histórico até 033: diagnóstico de GPU e FPS

A medição inicial de GPU global foi 78%, 67,57 W. Não é uma atribuição exclusiva
por processo. Nos testes 031/032, o modo normal permaneceu na faixa de 77–85% e
68–71 W no fim; sem VSync, 97–98% e cerca de 109 W. A tentativa sem VSync ficou
na tela de título, portanto não constitui comparação de gameplay equivalente.
Não afirmar ganho de desempenho ou FPS livre com velocidade correta.

Desligar VSync no SDK também altera o temporizador de vblank do console emulado
para cerca de 1.000 Hz. Não é apenas uma escolha de apresentação no monitor.
O modo continua experimental e desligado por padrão. Um desbloqueio correto
precisa identificar o limite do jogo e validar simulação, animações e áudio.
A etapa posterior alterou a apresentação, com redução local documentada acima.
O custo dos shaders FSI ainda pode ser otimizado; o cache
de pipelines trata compilação/preparação, não o custo de cada frame renderizado.

## Sombras

O usuário relatou uma sombra que acompanhou o personagem uma única vez; ainda
não ficou estabelecido se era a própria sombra dinâmica ou um artefato do cenário.
As capturas atuais não permitem reproduzir ou provar uma correção. Nenhum ajuste
cego de profundidade, desativação de sombras ou redução de qualidade foi aplicado.
Se reaparecer, preservar as imagens da cena e testar a reprodução antes/depois.

## Uso

```sh
python3 scripts/play_green_lantern.py --shader-mode async --vsync on
python3 scripts/play_green_lantern.py --graphics-preset high --validar
```

A interface Tk expõe as mesmas opções para a próxima abertura, além dos presets e
alvos. A preferência padrão é a solicitada: conhecidos preparados na entrada e
novos em background. O launcher valida também o hash do plugin quando o probe
fornece essa identidade.
