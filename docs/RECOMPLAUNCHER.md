# Suporte ao RecompLauncher — níveis 1 e 2

O projeto publica `recomplauncher.json` na raiz e, a partir do empacotamento
`--single-file`, inclui esse arquivo no topo de um ZIP ao lado do executável.
Isso cobre os dois primeiros níveis do guia do RecompLauncher:

- **Nível 1:** o jogador aponta a pasta extraída do disco, o launcher confere
  `default.xex`/Title ID `575207E9` e **Play** inicia o recomp diretamente.
- **Nível 2:** o launcher mostra qualidade gráfica, resolução interna, janela,
  filtro de saída, antisserrilhado e FPS na página do jogo.

## Como o Play funciona

O executável recebe:

```text
AsterNative-windows-x64.exe --play "<pasta com default.xex>" [opções]
```

`--play` é implementado em `native_port/play_entry.py` e encaminha os
argumentos para `scripts/play_green_lantern.py`, sem abrir a interface do
launcher do projeto. O mesmo comando existe no código-fonte:

```bash
python -m native_port play "/caminho/para/pasta-do-jogo" --graphics-preset high
```

O comando também aceita todas as opções já documentadas em
`scripts/play_green_lantern.py`, por exemplo `--hd-texture-pack`,
`--subtitle-language` e `--voice-language`. Opções adicionais passadas pelo
próprio jogador são acrescentadas depois das opções escolhidas no launcher.

## Configuração escrita pelo launcher

O `config` do manifesto usa um JSON simples em
`{config}/AsterNative/recomplauncher.json` com a chave `game_root`, preenchida
com a cópia do jogador a cada partida. O recomp não lê esse arquivo: o caminho
também é passado como argumento, o que mantém o launcher original intacto. As
preferências gráficas do launcher do projeto continuam em
`<dados>/app/.aster/config/settings.json` e não são sobrescritas.

Não publicamos um arquivo de configuração dentro do release: ele seria
substituído a cada atualização. O RecompLauncher cria o arquivo quando ele
ainda não existe.

## Publicando

```bash
python scripts/package_launcher.py --single-file [...opções da plataforma]
```

Além de `AsterNative-windows-x64.exe` (ou `AsterNative-linux-x86_64.AppImage`),
o comando gera:

- `LanternRecomp-v<versão>-Windows-x64.zip`
- `LanternRecomp-v<versão>-Linux-x64.zip`

Cada ZIP contém o executável da plataforma e `recomplauncher.json` na raiz.
Os executáveis avulsos permanecem como antes, para o atualizador embutido.
Anexe os ZIPs ao release do GitHub; o RecompLauncher escolhe o arquivo pelo
nome da plataforma e do processador.

## Limites atuais

- A entrada aceita é a **pasta extraída** com `default.xex`; aceitar uma ISO
  diretamente exigiria uma etapa `prepare` (nível 3) para extrair o XDVDFS.
- É necessário ter gerado o port no launcher do projeto ao menos uma vez.
  Presets Alta/Ultra, FSR 1 e texturas HD dependem do backend atualizado.
- Windows nativo/D3D12, campanha completa e FPS acima de 60 seguem sem
  certificação. As opções experimentais são identificadas como tal no manifesto.
- Nenhum arquivo do jogo, código recompilado ou dump é distribuído.
