# Presets gráficos e alvo de FPS

O launcher e o script de abertura usam a mesma tabela em
`native_port/graphics.py`. Os presets traduzem valores para CVars reais do
ReXGlue na próxima sessão. Eles não editam o save, o perfil do jogo nem os
arquivos do dump; as preferências do launcher ficam em
`.aster/config/settings.json` (schema 2).

## Presets

| Preset | Resolução interna | MSAA do jogo | Anisotrópico | Cache de texturas (soft/hard/RTT) | Dither |
| --- | --- | --- | --- | --- | --- |
| **Baixa** | 1280×720 (1x) | backend | 1x | 192 / 384 / 16 MB | desligado |
| **Média** | 1280×720 (1x) | backend | 4x | 384 / 768 / 24 MB | desligado |
| **Alta** | 2560×1440 (2x) | backend | 8x | 512 / 1024 / 32 MB | desligado |
| **Ultra** | 3840×2160 (3x) | backend | 16x | 768 / 1536 / 48 MB | desligado |
| **Personalizada** | 1x–3x | backend | automático–16x | conforme a qualidade | on/off |

O preset **Média** (identificador interno `default`) é o default do launcher e
foi escolhido para manter o equilíbrio usado nas sessões principais; o build
principal sem flags usa os defaults do SDK. A equivalência visual não é
certificada bit a bit. A resolução interna é independente do tamanho da janela:
2x e 3x renderizam em 1440p/2160p e depois apresentam na janela. Isso aumenta o
custo de GPU; não é um filtro de nitidez sem custo.

A saída **1920×1080 (Full HD)** está disponível em todos os presets. A escala
interna real é 1x (720p), 2x (1440p) ou 3x (2160p); ainda não existe 1080p
interno exato em 1,5x. Em **Personalizada**, saída, escala interna, texturas,
filtragem, AA e FPS são independentes e persistentes.

Um probe curto do build principal de 30 fps com este preset
(`preset30-default-001`, 12,52 s) carregou o XEX, aceitou as CVars e fez 461
apresentações sem fatal, em FSI/FIFO e perfil isolado. O relatório fica em
`.aster/reports/rexglue-runtime-probe-default-preset-30.json`. O prazo curto não
completa a inicialização (`ready=false`); o teste confirma aceitação das flags,
não jogabilidade.

As flags geradas são:

```text
--resolution_scale=N
--anisotropic_override=-1..5
--texture_cache_memory_limit_soft=MB
--texture_cache_memory_limit_hard=MB
--texture_cache_memory_limit_render_to_texture=MB
--present_dither=true|false
```

`present_dither` é uma CVar real do SDK, definida em
`src/ui/presenter.cpp` com default `false`; ela atua no passe final de
apresentação. As demais flags também foram conferidas no plugin Vulkan local.

## Geração local atual

O launcher gera um host local para os três alvos. Todos usam saves e cache
compartilhados na pasta de dados do usuário, independentemente dos gráficos.
Veja [PORTABLE_BUILD.md](PORTABLE_BUILD.md). Desligar VSync em30/60 muda a apresentação, mantendo o
relógio guest sincronizado. O falso controle de MSAA foi desabilitado: no backend
FSI usado, `native_2x_msaa=false` não desliga MSAA.

## Alvos de FPS

| Alvo | Save/cache | VSync / apresentação | Estado |
| --- | --- | --- | --- |
| **30 fps** | `.aster/runtime/green-lantern/` | escolha do usuário | padrão |
| **60 fps** | mesmo perfil | escolha do usuário | experimental, opt-in |
| **Ilimitado** | mesmo perfil | desligado / imediato | experimental, opt-in; ganho acima de60 não comprovado |

O alvo ilimitado usa um hook que remove a espera de pacing e força a
apresentação imediata. A engine recebe alvo 60, mas remover a espera não garante uma simulação fixa;
“ilimitado” descreve a apresentação, não uma garantia de física acelerada. O
modo pode causar tearing, consumir muito mais GPU e não substitui a validação
humana de jogabilidade.

## Pelo launcher

1. Abra **Gráficos**.
2. Escolha **Baixa**, **Média**, **Alta**, **Ultra** ou **Personalizada**.
3. Escolha **30 fps**, **60 fps** ou **ILIMITADO**.
4. Volte a **Jogar** e clique em **Jogar agora**.

Os controles de **Ajustes personalizados** ficam editáveis. Alterar resolução
interna, anisotrópico, cache de texturas ou dithering troca o preset para
**Personalizada** automaticamente; os botões de preset continuam disponíveis
para voltar a um valor fixo.

Sem build, o botão principal oferece **Gerar port nativo** para a pasta com
`default.xex`. Com build íntegro, oferece **Jogar agora**. **Jogo e arquivos** mostra os
caminhos e o estado da compilação. **Diagnóstico** reúne tarefas e logs.

Os alvos 60 e ilimitado pedem confirmação e mostram um aviso antes de abrir.
Todos os alvos compartilham o mesmo perfil/save do usuário; trocar de alvo não
cria um save separado. Fechar o launcher ou usar **Encerrar sessão** termina
apenas o processo aberto por ele.

## Pelo terminal

```sh
# Padrão: 30 fps, preset Média
python3 scripts/play_green_lantern.py --validar
python3 scripts/play_green_lantern.py

# Preset Alta em 30 fps
python3 scripts/play_green_lantern.py --graphics-preset high

# 60 fps experimental, save compartilhado
python3 scripts/play_green_lantern.py --fps-target 60 --validar
python3 scripts/play_green_lantern.py --fps-target 60

# Ilimitado experimental, save compartilhado
python3 scripts/play_green_lantern.py --fps-target unlimited --validar
python3 scripts/play_green_lantern.py --fps-target unlimited
```

`--experimental-60fps` continua aceito como atalho antigo para
`--fps-target 60`. Os presets também aceitam ajustes explícitos:
`--render-scale`, `--msaa`, `--anisotropic`, `--texture-quality` e `--dither`.
Qualquer ajuste explícito muda o preset para **Personalizada**.

## Requisitos para outra pessoa

- O mesmo dump identificado pelo SHA-256
  `3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1`.
- Port gerado na própria máquina para a revisão e plataforma suportadas.
- Suporte a Vulkan FSI (fragment shader interlock), testado localmente na
  RTX 5060.
- O caminho do dump é escolhido na interface; o launcher não redistribui
  assets nem código proprietário.

O build é gerado localmente, não baixado pelo launcher. Os comandos de
compilação e os objetos esperados estão em [BUILD_PIPELINE.md](BUILD_PIPELINE.md)
e [DEVELOPMENT.md](DEVELOPMENT.md). O script `scripts/build_rex_experiment.py`
cria os hosts experimentais em `.aster/build/`; o build principal usa o staging
local descrito no pipeline.

O `--validar` confere o hash do XEX, do executável e do plugin, exige o caminho
FSI, XEX carregado, apresentação observada e ausência de erros fatais. Para o
modo ilimitado, exige também as flags experimentais, VSync desligado,
apresentação imediata e média acima de 60 apresentações/s.

## Limites atuais

- A qualidade visual de Baixa/Alta/Ultra e a sensação de 60/ilimitado ainda
  precisam de comparação humana no mesmo trecho.
- Há capturas limitadas de movimento e ataques nos modos experimentais. Isso
  não certifica a campanha nem gameplay acima de60FPS. Contagens antigas de
  presents guest não equivalem a quadros efetivamente apresentados.
- Outras GPUs, VRAM, tearing, áudio e campanha completa não foram validados.
- Não limpe arenas `xenia_memory_*` em `/dev/shm` sem auditoria e autorização.
