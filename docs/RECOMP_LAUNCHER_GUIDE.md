# Guia interno de launcher para recomps

Este documento registra o que um launcher de recomp precisa ter e como a
implementação está organizada. **A interface deste projeto é do Green
Lantern**, não de um “launcher universal”: a base fica nos bastidores, sem
marca ou texto genérico na tela.

## Camadas internas

| Camada | Arquivo | Papel |
| --- | --- | --- |
| Shell | `native_port/portal_shell.py` | janela, sidebar, paleta, estilos ttk, logo, navegação em constructos, cartões e rodapé. |
| Primitivas | `native_port/portal_widgets.py` | `RoundedCard`, `ConstructNav`, `PortalMark`, `draw_portal_mark`, `rounded_rect`. |
| Tema | `native_port/portal_theme.py` + `native_port/themes/*.json` | cores, fonte, glyph, textos e motivo do hero. |
| Arte procedural | `native_port/launcher_artwork.py` | hero com energia do anel, órbita, partículas e reveal. Usa só o tema. |
| Jogo | `native_port/launcher.py` | Green Lantern: páginas, comandos, gráficos, coop, saves, sessões e idiomas. |
| Sessões | `native_port/session_stats.py` | horas jogadas, última sessão e duração. |
| Saves | `native_port/save_manager.py` | exportar/importar `.zip` com backup automático. |

`PortalShell` não importa `games.green_lantern`, gráficos, XEX nem saves.
A camada do jogo implementa `PAGES` e fornece os builders; o shell apenas
monta o esqueleto. O tema é descoberto por `ASTER_PORTAL_THEME`, por
`.aster/config/portal-theme.json` ou pelo builtin `green_lantern`.

## Contrato preservado

- nomes de estilos ttk: `Card.TFrame`, `Card.TLabel`, `CardMuted.TLabel`,
  `H2.TLabel`, `Preset.TButton`, `PresetOn.TButton`, `Modern.TNotebook`, …;
- atributos `root`, `tabs`, `nav_buttons`, `nav_lines`, `status_bar`,
  `footer_progress` e as páginas nomeadas pelo jogo;
- `RoundedCard` continua sendo um `tk.Frame`;
- `LanternHero` continua sendo um `tk.Canvas` com tag `hero-status` e
  `set_status()`;
- `nav_buttons` continua apontando para `tk.Button`, agora dentro de
  `ConstructNav`, para atalhos e testes.

## O que um launcher de recomp precisa ter

1. Identidade do jogo, não do launcher: logo, arte, paleta e textos do título.
2. Navegação clara: Início, Gráficos, Controles, Jogo, Preparar,
   Diagnóstico e Atualizações.
3. Ação principal visível: jogar, continuar ou gerar/atualizar o port.
4. Estado do dump e do backend sem esconder bloqueios.
5. Gráficos honestos: presets, resolução interna, upscaler disponível e FPS
   real (30/60/120/240), sem prometer DLSS/FSR temporal.
6. Sessões: horas jogadas, última vez e duração da última sessão.
7. Saves: abrir a pasta, exportar `.zip` e importar com backup.
8. Idiomas: texto e voz separados; português brasileiro aplicado ao slot de
   texto correto, sem fingir dublagem que o dump não tem.
9. Feedback de tarefas longas, cancelamento e relatório local.
10. Nada de escrita no save, no dump ou no perfil sem ação explícita.

## Criando outro launcher de jogo

1. Copie `native_port/themes/green_lantern.json` e troque os campos.
2. Selecione com `ASTER_PORTAL_THEME=meu_recomp` ou
   `.aster/config/portal-theme.json`.
3. Crie uma classe que herde `PortalShell`, defina `PAGES` e chame
   `attach()` → `build_style()` → `build_shell()`.
4. Só a camada do jogo implementa flags, comandos e painéis específicos.

Temas inválidos nunca impedem a abertura: `PortalTheme.validate()` raising
`PortError` faz o launcher cair para o tema builtin e mostrar o motivo no
status.

## Identidade visual do Green Lantern

- **Logo:** `draw_portal_mark()` desenha um anel aberto, haste e núcleo; o
  `glyph` é `GL`.
- **Sidebar:** menu vertical com ícones e constructos de energia; o item ativo
  acende e o clique constrói o contorno antes de trocar de página.
- **Hero:** energia do anel no fundo, arcos girando, partículas subindo e
  reveal de texto. Sem assets externos.
- **Cards:** raio 20, bordas suaves e divisores em curva.

## Limite de quadros em números

A UI mostra **30 / 60 / 120 / 240 fps**. Internamente:

- `30` e `60` seguem com `fps_target` direto;
- `120` e `240` mapeiam para `fps_target='unlimited'` com
  `unlimited_target` real, porque o hook precisa desativar o pacing e elevar
  o relógio da engine ao número escolhido.

O menu F1 do jogo usa os mesmos quatro rótulos. Ainda é experimental e exige
validação manual de física, combate, animações e áudio. Como o hook mudou,
`INTEGRATION_VERSION` subiu para 26 e um port antigo pede
“Gerar port/Atualizar port”.

## Validação

```bash
PYTHONPATH=. xvfb-run -a -s "-screen 0 1440x900x24" uv run --with pytest \
  --with Pillow==12.3.0 --with xxhash==3.6.0 --with capstone==5.0.7 pytest -q
```

A suíte cobre geometria, abas, estilos, save, sessões, comandos de launch e os
alvos numéricos de FPS sem depender de assets externos.

## Limite de quadros em números

A UI mostra **30 / 60 / 120 / 240 fps**. Internamente:

- `30` e `60` seguem com `fps_target` direto;
- `120` e `240` mapeiam para `fps_target='unlimited'` com
  `unlimited_target` real, porque o hook precisa desativar o pacing e elevar
  o relógio da engine ao número escolhido.

O menu F1 do jogo usa os mesmos quatro rótulos. Ainda é experimental e exige
validação manual de física, combate, animações e áudio. Como o hook mudou,
`INTEGRATION_VERSION` subiu para 26 e um port antigo pede
“Gerar port/Atualizar port”.

## Validação

```bash
PYTHONPATH=. xvfb-run -a -s "-screen 0 1440x900x24" uv run --with pytest \
  --with Pillow==12.3.0 --with xxhash==3.6.0 --with capstone==5.0.7 pytest -q
```

A suíte cobre geometria, abas, estilos, save, comandos de launch e os alvos
numéricos de FPS sem depender de assets externos.
