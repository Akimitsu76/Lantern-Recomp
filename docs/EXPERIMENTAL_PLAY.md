# Abrir a compilação experimental

## Pela interface gráfica

O launcher tem quatro abas: **Jogar**, **Gráficos**, **Jogo e arquivos** e
**Diagnóstico**. Selecione em **Jogar** a pasta que contém `default.xex` e clique
em **Jogar agora**. A validação roda em segundo plano; se falhar, o motivo
aparece no status e em **Diagnóstico**. Os botões normais de compilar e iniciar
continuam indisponíveis enquanto o backend integral não for validado.

Na aba **Gráficos**, escolha o preset (**Baixa**, **Média**, **Alta**, **Ultra**
ou **Personalizada**) e o alvo (**30 fps**, **60 fps** ou **ILIMITADO**). A tabela
completa está em [GRAPHICS_PRESETS.md](GRAPHICS_PRESETS.md).

- **30 fps** é o padrão e usa o perfil do usuário.
- **60 fps** é opt-in e usa o build v9; compartilha o perfil do usuário.
- **Ilimitado** é opt-in, usa o build v10 com VSync desligado e apresentação
  imediata; compartilha o mesmo perfil do usuário.

Os dois modos experimentais pedem confirmação e mostram aviso. Eles usam o mesmo
save do usuário; não criam um save separado. O launcher nunca troca de alvo
sozinho; as opções valem para a próxima sessão.

**Jogar agora** só habilita quando a pasta tem `default.xex` e o build/referência
FSI do alvo selecionado existem. **Jogo e arquivos** mostra os caminhos, os
requisitos e o estado da compilação. Se o build faltar, o launcher explica o que
fazer em vez de tentar abrir um executável ausente.

Durante a sessão, os controles de abertura ficam desabilitados. **Encerrar
sessão** termina somente o processo aberto por essa interface; fechar o launcher
também encerra essa sessão. A janela do jogo pode ser fechada normalmente. O log
do launcher fica em `.aster/reports/launcher-play-*.log`, com o caminho do log do
runtime impresso na abertura. Não há marcação automática de port pronto.

## Pelo terminal

As opções a seguir só afetam a próxima abertura; não alteram uma sessão que já
está rodando. O padrão mantém compilação de shaders novos em segundo plano e
VSync ligado:

```sh
python3 scripts/play_green_lantern.py --shader-mode async --vsync on
```

Para o alvo 60 opt-in, use o build experimental v9; o perfil é compartilhado:

```sh
python3 scripts/play_green_lantern.py --fps-target 60 --validar
python3 scripts/play_green_lantern.py --fps-target 60
```

A validação do modo 60 usa `.aster/reports/rexglue-runtime-probe-60fps.json`
(probe 057, FSI) e não substitui a referência principal 047. Saves, cache e
configurações ficam no perfil compartilhado `.aster/runtime/green-lantern/`
para todos os alvos.

Para o alvo ilimitado opt-in:

```sh
python3 scripts/play_green_lantern.py --fps-target unlimited --validar
python3 scripts/play_green_lantern.py --fps-target unlimited
```

O modo ilimitado usa o build v10
`.aster/build/rex-fps-unlimited-v10/aster_green_lantern` e o perfil compartilhado
`.aster/runtime/green-lantern/`. Ele exige VSync desligado e apresentação
imediata; o script rejeita combinações contrárias. A referência é
`.aster/reports/rexglue-runtime-probe-unlimited.json`, gerada em FSI com
38.627 apresentações em 90,16 s, sem fatal. O probe ainda registra
`gameplay_verified=false`; a captura X11 de gameplay no Xwayland não funciona
nesta máquina.

O modo ilimitado remove a espera de pacing do build v10. A simulação observada
continua com alvo 60 e acompanha o tempo de parede; “ilimitado” descreve a
apresentação, não uma garantia de física acelerada. Pode causar tearing e
consumir muito mais GPU. Se o jogo parecer acelerado ou instável, volte para
30 fps.

Com VSync ligado, o launcher também solicita apresentação sincronizada **FIFO**.
O SDK antes preferia apresentação imediata mesmo com o vblank do jogo
sincronizado. A mudança mantém a resolução e os recursos gráficos; os resultados
locais e limites estão em [GPU_OPTIMIZATION.md](GPU_OPTIMIZATION.md). Para
restaurar somente a escolha anterior de apresentação, conservando VSync:

```sh
python3 scripts/play_green_lantern.py --vsync on --present-mode auto
```

O launcher passa explicitamente `--store_shaders=true`, conserva o diretório de
cache existente e não limpa shaders. `--shader-mode blocking` aguarda a
compilação de shaders novos; `async` usa o caminho assíncrono do SDK. A
reutilização e o aquecimento dos shaders já conhecidos dependem do cache e do
backend do SDK; as opções do launcher não comprovam, por si, que todos foram
pré-compilados.

Os presets também podem ser escolhidos na linha de comando:

```sh
python3 scripts/play_green_lantern.py --graphics-preset high --validar
python3 scripts/play_green_lantern.py --graphics-preset high
```

Ajustes explícitos (`--render-scale`, `--msaa`, `--anisotropic`,
`--texture-quality`, `--dither`) mudam o preset para **Personalizada**. O
`--experimental-60fps` continua aceito como atalho antigo para
`--fps-target 60`.

Na aba **Gráficos**, as mesmas escolhas aparecem em **Sessão** (VSync e shaders)
e **Ajustes personalizados**. Elas ficam em `.aster/config/settings.json`
(schema 2) e não alteram saves, perfil do jogo ou configurações da sessão ativa.

Desligar VSync com `--vsync off` é experimental, pode aumentar o uso da GPU e
não garante FPS destravado nem velocidade correta do jogo. Não há ajuste de
sombras comprovado nesta interface.

Na raiz do projeto, confira os arquivos sem abrir uma janela ou iniciar o jogo:

```sh
python3 scripts/play_green_lantern.py --validar
python3 scripts/play_green_lantern.py --validar --fps-target 60
python3 scripts/play_green_lantern.py --validar --fps-target unlimited
```

`--dry-run` continua aceito e faz a mesma validação. O comando confere o hash
do `default.xex`, o executável, o plugin e o último probe FSI correspondente.
Para o modo ilimitado, também exige as flags experimentais, VSync desligado,
apresentação imediata e média acima de 60 apresentações/s. Uma validação
bem-sucedida não certifica a campanha completa.

Para jogar:

```sh
python3 scripts/play_green_lantern.py
```

Para escolher outra pasta com o mesmo dump validado, use o caminho entre aspas:

```sh
python3 scripts/play_green_lantern.py "/caminho/para/Green_Lantern"
```

Informe a pasta que contém `default.xex`. A pasta original permanece protegida
contra escritas relativas do runtime. Saves, cache e configurações ficam em
`.aster/runtime/green-lantern/` para todos os alvos. O launcher mostra o caminho
do log de cada sessão.

O launcher e os novos probes compartilham um bloqueio para impedir duas sessões
usando os mesmos saves ao mesmo tempo. O bloqueio é liberado quando o processo
termina; o arquivo `play.lock` pode permanecer no disco e não precisa ser
removido.

| Tecla | Botão do Xbox 360 |
| --- | --- |
| Enter | Start |
| Espaço | A |
| Backspace | B |
| WASD | Stick esquerdo |
| L | X |
| Setas | Stick direito |
| P | Y |
| Q / E | LT / RT |
| 1 / 3 | LB / RB |
| F / K | LS / RS (clique dos sticks) |
| Tab | Back |
| Shift + setas | Direcional digital (D-pad) |

Esses são os botões enviados pelo SDK. A ação correspondente depende do
contexto e dos comandos apresentados pelo jogo.

O perfil usa Vulkan FSI e depende de suporte a fragment shader interlock. Para o
estado de jogabilidade e as limitações observadas, consulte o
[checkpoint](RESUME_CHECKPOINT.md) e o [relatório de revisão](OPENCODE_REVIEW.md).
