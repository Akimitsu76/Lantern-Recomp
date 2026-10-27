# Jogabilidade observada — 22/10/2026

Atualização: sessão humana 027 alcançou combate em outras áreas da missão 1 com
personagem Lv.2; a cópia do perfil retomou o checkpoint no teste 031. A sessão
humana durou 35 min 52 s, sem fatal nos logs retidos. Cache/FPS/GPU e limites
atuais: [GRAPHICS_POLISH.md](GRAPHICS_POLISH.md). O relato abaixo preserva a etapa
anterior de testes automatizados.

A compilação experimental permite jogar o começo da missão 1. O ponto mais
avançado observado foi o grupo de inimigos após destruir os primeiros destroços,
com o tutorial de defesa na tela. **Esse é o limite da validação atual, não um
bloqueio técnico confirmado nessa passagem.** A missão inteira não foi concluída.

## Histórico dos testes iniciais

| Recurso | Evidência observada | Limite |
| --- | --- | --- |
| Inicialização e menus | START/A, perfil GL_10, partida carregada | Mesmo dump e hardware locais |
| Renderização | Cenário, personagens, inimigos, HUD e efeitos com Vulkan FSI | Há efeitos/transparências ainda sem comparação com o console |
| Movimento e combate | Deslocamento, golpes X/Y, contador de combo e dano recebido | Combate automatizado não equivale a uma partida humana completa |
| Obstáculos | Destroços destruídos por ataques; passagem liberada | Não foi necessário alterar a lógica do jogo |
| Progressão | Grupo seguinte e tutorial de defesa após a passagem | Primeiro salto contextual e áreas posteriores pendentes |
| Pausa | Menu PAUSED e retorno ao jogo | Opções/upgrades não foram todas exercitadas |
| Derrota e retomada | GAME OVER seguido de CONTINUE e retorno à arena inicial | Não demonstra persistência de checkpoint em disco |
| Perfil | Criação e releitura em execução posterior | Save de campanha continua pendente |
| Áudio | Sinal não nulo capturado exclusivamente de um stream do PID do jogo | Qualidade, sincronia, canais e todas as vozes não foram validados |

O teste 024 durou 900,44 s sem fatal registrado. Incluiu tempo parado; não é uma
medição de quinze minutos de gameplay contínuo nem um benchmark de FPS. No teste
026 houve derrota por perda de vida e continuação, com o executável funcionando.
As sequências guiadas têm intervalos para capturar a janela e são insuficientes
para concluir que um confronto seja impossível ou que a dificuldade esteja correta.

## Evidências privadas

- Combate e combo: `022-combat-and-camera/input-before-12.png`.
- Pausa: `022-combat-and-camera/input-before-35.png`.
- Obstáculo destruído: `026-jump-and-audio/window-47.png`.
- Grupo seguinte/tutorial de defesa: `026-jump-and-audio/live-1187.png`.
- Derrota: `026-jump-and-audio/live-1781.png`.
- Continuação e novo combate: `026-jump-and-audio/live-2164.png`.
- Áudio: `026-jump-and-audio/audio-evidence.json`, 574.464 amostras s16 estéreo,
  pico 26.829 e RMS 3.965,213; sinal atribuído ao PID 581789. A captura tem cerca
  de seis segundos e não inclui microfone nem mixagem de outros aplicativos.

Os caminhos acima estão em `.aster/reports/rex-history/`. Logs por tentativa
preservam encerramento, eventos enviados, capturas, hash do executável e do XEX.
`ready=false` e `gameplay_verified=false` permanecem: ainda não há certificação
integral de jogabilidade. O SDK não foi modificado e o build nativo é o mesmo
validado antes destes polimentos.

## Polimentos entregues

O launcher foi redesenhado com as abas **Jogar**, **Gráficos**, **Jogo e
arquivos** e **Diagnóstico**. O layout padrão é 1160×720, com mínimo 1088×696, e
os controles principais continuam visíveis em captura e testes. A suíte completa
terminou com **152 testes aprovados**, sem falhas ou skips.

Na aba **Gráficos** ficam os presets **Baixa/Média/Alta/Ultra/Personalizada** e
os alvos **30/60/ilimitado**. 30 fps continua o padrão; 60 e ilimitado são
opt-in, pedem confirmação e compartilham o mesmo perfil/save do usuário. O botão **Jogar agora** valida
dump, build, plugin e referência FSI antes de abrir. O backend completo próprio
permanece indisponível. O comando de abertura ganhou ajuda em português,
controles completos, erros claros, validação sem abrir e bloqueio de sessões
concorrentes. Novos probes usam o mesmo bloqueio e podem aceitar comandos locais
registrados, incluindo movimento e salto simultâneos, sempre dirigidos à janela
do próprio processo.

Consulte [EXPERIMENTAL_PLAY.md](EXPERIMENTAL_PLAY.md) e
[GRAPHICS_PRESETS.md](GRAPHICS_PRESETS.md) para abrir o jogo.

A sessão humana 058 jogou o checkpoint Lv.2 no modo 60, com combate, pausa,
cutscene e carregamento; as capturas são evidência visual. A sessão teve mediana
de 59,995 apresentações/s, mas 6 janelas de 5 s abaixo de 59 e 3 abaixo de 55.
A percepção desses engasgos e a qualidade de física, animações e áudio ainda
precisam ser registradas pelo jogador.

O modo ilimitado v10 tem evidência automatizada, não humana: 90,16 s, 38.627
apresentações (428,4/s), FSI, simulação com alvo 60 em tempo real e nenhum
fatal. O probe registra `gameplay_verified=false`, e a captura X11 de gameplay
no Xwayland não funciona nesta máquina. Portanto, ainda não há confirmação
visual de combate, física, animações, áudio, tearing ou estabilidade nesse modo.
A avaliação dos presets Baixa/Alta/Ultra também depende do usuário.

## Próximo teste recomendado

Jogar manualmente a partir da missão 1, concluir o tutorial de defesa, ativar o
primeiro salto contextual e atingir um checkpoint posterior. Depois, fechar o
processo e conferir CONTINUE em uma nova sessão para validar save de campanha.
Também vale repetir com áudio monitorado e comparar os mesmos trechos em 30 fps.
O roteiro comunitário da [missão 1](https://gamerch.com/xboxwalkthrough/409144)
foi usado somente para orientar as tentativas de navegação: suas descrições não
certificam o comportamento desta compilação. Nenhuma lógica do jogo foi alterada
para contornar objetivos ou combate.
