# Suporte ao RecompLauncher — níveis 1, 2 e 3

O projeto publica `recomplauncher.json` na raiz e, a partir do empacotamento
`--single-file`, inclui esse arquivo no topo de um ZIP ao lado do executável.
Isso cobre os três níveis do guia do RecompLauncher:

- **Nível 1:** o jogador informa a ISO ou a pasta extraída do disco, o launcher
  confere o Title ID `575207E9` e **Play** inicia o recomp diretamente.
- **Nível 2:** o launcher mostra qualidade gráfica, resolução interna, janela,
  filtro de saída, antisserrilhado e FPS na página do jogo.
- **Nível 3:** uma etapa de preparação extrai a ISO sem abrir janela, os dumps
  conhecidos da Redump dão o selo de versão verificada e `prepare.done` permite
  ao launcher saber quando a extração já foi feita.

## Setup: o que o jogador vê

A entrada se chama `game` (o formato moderno de `inputs`; o campo `game` legado
não é usado). O manifesto aceita:

- uma imagem `.iso` XDVDFS de Xbox 360;
- uma pasta já extraída com `default.xex` na raiz.

O `check.ids` lê o Title ID do `default.xex` na imagem ou na pasta e recusa
cópias de outros jogos. Os dumps da Redump cadastrados são:

| Edição | Tamanho | CRC32 |
| --- | --- | --- |
| Europe (disc 61842) | 7838695424 | `b722866e` |
| USA (disc 90097) | 7838695424 | `1cb483fd` |

Uma cópia que não bate com esses valores ainda funciona; o jogador só não
recebe o selo de dump verificado.

Se escolheu uma ISO, o launcher executa:

```text
AsterNative-windows-x64.exe --prepare-game "<iso>"
```

`native_port/play_entry.py` extrai o XDVDFS com
`native_port/xdvdfs_extract.py` para
`<dados-do-launcher>/app/.aster/game-files/green-lantern`, verifica o SHA-256 do
`default.xex` e imprime linhas `progress <0..1> <texto>` durante a operação.
A extração é somente leitura em relação à imagem e nunca escreve dentro do
release, então atualizações não apagam nem sobrescrevem os arquivos do jogo.
Names, profundidade, tamanho de arquivo e total de bytes são limitados;
links simbólicos e caminhos com `..` são recusados.

O comando também existe no código-fonte:

```bash
python -m native_port prepare-game "/caminho/para/jogo.iso"
```

## Play

Ao pressionar Play, o launcher passa a mesma cópia escolhida no setup:

```text
AsterNative-windows-x64.exe --play "<iso ou pasta>" [opções do launcher]
```

`--play` resolve a ISO para a pasta extraída (extraindo-a se necessário) e
encaminha o resultado para `scripts/play_green_lantern.py`, sem abrir a
interface do launcher do projeto:

```bash
python -m native_port play "/caminho/para/jogo.iso" --graphics-preset high
```

O comando aceita todas as opções já documentadas em
`scripts/play_green_lantern.py`, por exemplo `--hd-texture-pack`,
`--subtitle-language` e `--voice-language`. Opções adicionadas pelo jogador
são acrescentadas depois das opções escolhidas no launcher.

Os placeholders do manifesto usam o formato atual (`{input:game}`). O launcher
também entende o antigo `{game}` como alias para a entrada principal.

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
nome da plataforma e do processador. O manifesto no `main` sozinho não é
lido pelo launcher — é preciso publicar uma release com os ZIPs.

## Limites atuais

- É necessário ter gerado o port no launcher do projeto ao menos uma vez.
  Presets Alta/Ultra, FSR 1 e texturas HD dependem do backend atualizado.
- Windows nativo/D3D12, campanha completa e FPS acima de 60 seguem sem
  certificação. As opções experimentais são identificadas como tal no manifesto.
- Nenhum arquivo do jogo, código recompilado ou dump é distribuído.
