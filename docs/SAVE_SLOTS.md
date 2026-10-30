# Slots de campanha no menu do jogo

Disponível na integração nativa 24, distribuída pelas mesmas fontes no launcher
Linux (AppImage) e Windows (.exe). Atualizar somente o launcher não altera um
backend antigo: use **Gerar port / Atualizar port** uma vez para recompilá-lo.

- **New Game** abre seis slots dentro da janela do jogo. Escolha o destino e
  prossiga pelas opções originais de jogadores e dificuldade.
- **Continue** abre os mesmos slots e permite carregar os que possuem dados.
- Slots ocupados exigem confirmação para uma nova campanha. O port cria uma
  cópia de segurança antes de entregar a substituição ao jogo original.
- B/Backspace ou Esc cancela o seletor. Voltar da seleção de jogadores de New Game restaura a seleção anterior.

Os slots guardam campanhas com os checkpoints/autosaves originais. Não são
snapshots completos de memória. O seletor não aparece no Continue da tela de
derrota nem substitui o menu de pausa.

O Slot 1 mantém exatamente o diretório legado, sem mover ou converter o save.
Os slots 2–6 ficam em `user/<XUID>/575207E9/NativeSlots/02` até `06`, cada um
com seu container e cabeçalho. Backups ficam em `NativeSlots/Backups`.
A preferência `NativeSlots/active.txt` pertence ao perfil desse usuário.
Trocar 30/60/ilimitado, preset ou resolução não cria outros slots.

## Validação desta entrega

Linux: campanha nova no Slot 2 chegou ao início da primeira fase, preservando o
arquivo do Slot 1. Após reiniciar com o Slot 2 ativo, Continue carregou o Slot 1
com a fase de voo do progresso anterior; houve leitura real do container antes
de aplicar o estado. Cancelamento do seletor, backup e retorno de New Game
foram exercitados. O teste da build pública também usou 60 FPS.

O contrato C++ compila o hook real contra o SDK e verifica os limites do menu,
o callback de IO, a preservação do contexto e a restauração após erro de leitura.
A rotina de armazenamento testa isolamento por usuário, troca de slots,
cancelamento e backup. O workflow Windows contém esses mesmos contratos.

AppImage e .exe passaram pela abertura gráfica isolada; o .exe foi verificado
em Wine. Isso não certifica gameplay D3D12 em Windows real nem campanha completa.

O aviso original de sobrescrita ainda pode aparecer ao iniciar em um slot vazio,
pois o menu original consulta dados em cache. A gravação é dirigida ao slot
escolhido. A remoção desse aviso redundante não foi certificada nesta entrega.
