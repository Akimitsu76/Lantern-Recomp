# Preparação de shaders

O launcher usa duas fontes de preparação: pipelines aprendidos nas suas partidas
e um perfil pequeno de pipelines revisados que pode reconstruir do seu dump antes
da primeira partida. A opção fica em **Gráficos → Preparar shaders revisados e o
cache aprendido antes de jogar**. Ela é independente da compilação assíncrona de
shaders novos durante a partida.

O perfil inicial cobre o filtro cinematográfico da abertura e um efeito de
partículas do combate na primeira plataforma: quatro programas e dois estados
de pipeline Vulkan. D3D12 recebe os estados equivalentes ROV, com variantes de
ForcedSampleCount 1/4. **Isso não é um inventário de toda a campanha.** Estados ou
programas ainda não vistos podem exigir compilação e causar uma pausa.

`games/green_lantern_shader_prewarm.json` contém somente hashes, posições no banco
original, operandos de layout de vértices e estados gráficos escalares. Não contém
microcódigo do jogo, SPIR-V, DXBC ou cache de driver. O programa é extraído do dump
local, com conferência do XEX, contêiner, banco decodificado e hash de cada shader
reconstruído. Apenas operandos de vertex-fetch previamente revisados são ajustados;
opcodes e operações matemáticas não são modificados.

A decodificação é guardada no workspace do usuário. Preparações seguintes conferem
e reutilizam esse resultado. Entradas novas são acrescentadas ao cache compartilhado
entre 30/60/ilimitado; registros antigos são preservados. Se houver alteração, a
versão anterior dos arquivos é guardada ao lado com sufixo `before-prewarm-<hash>`.
Uma segunda execução sem novas entradas não regrava os arquivos. A preparação
usa a mesma trava de sessão do jogo e recusa alterações enquanto ele está aberto.
Formatos de cache desconhecidos ou corrompidos são preservados e informados como
erro; desativar a opção permite usar o caminho de inicialização sem esta preparação.

O backend cria os objetos gráficos antes de entrar no jogo. O cache do driver
reduz o custo nas próximas execuções; uma troca de GPU, driver ou formato do
backend pode exigir nova compilação. Não se distribui cache específico de outra
placa como solução universal.

O serializador mantém os formatos Vulkan/Linux e D3D12/Windows separados. Um teste
C++ compara os bytes produzidos com as declarações de tipos do SDK fixado. Testes
Python exercitam hashes, limites, preservação, repetição, corrupção e trava de
sessão. Compilação e gameplay nativos Windows precisam do workflow e de teste em
GPU Windows; testes pelo Wine não substituem essa validação.

O patch 0033 também aguarda a fila de apresentação Vulkan ao retirar uma swapchain,
além das submissões de renderização. Essa espera ocorre em troca de superfície ou
encerramento, sem acrescentar uma espera a cada quadro. O caminho atual usa WSI
legado, sem habilitar `swapchain_maintenance1`.

Em um par local de testes Linux com as mesmas entradas e cachebase, sem captura
PNG durante os comandos, o maior intervalo de apresentação entre100–170s caiu
de517,45ms para34,45ms ao preparar estes estados. A mediana ficou em16,82ms
nos dois casos. O pipeline caro foi criado antes da partida; este resultado
não demonstra eliminação de pausas em estados inéditos ou na campanha inteira.
