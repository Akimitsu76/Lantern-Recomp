# Correções gráficas — 29/10/2026

O usuário autorizou retomar o jogo após o trabalho do launcher. Saves e instalação
humana permanecem preservados. A fonte agora exige integração23; os pacotes do
launcher0.1.4-rc.3 entregues em28/10 continuam sendo artefatos anteriores.

## Travadas e texturas

O patch público0034 retém até128MiB de dados DDS e metadados de mip já validados
em RAM, com descarte LRU. Isso evita repetir leitura e hash quando a textura
perde todos os donos na GPU, mas sua fonte ainda cabe no cache. Pequenas estruturas
de controle ficam além desse limite. Não amplia VRAM, não carrega toda a biblioteca,
não elimina upload GPU e não remove a primeira leitura. A criação de shaders
inéditos ainda pode interromper a apresentação; não está declarada resolvida.

A correção usa o mesmo cabeçalho nos backends Vulkan/Linux e D3D12/Windows, está
registrada nas receitas do SDK e do plugin Linux e altera a identidade do backend.
Por acrescentar armazenamento a um tipo público, força conservadoramente novo
host CPU. Não substituir DLLs do backend anterior manualmente.

##60FPS e ilimitado

O hook portátil ganhou medições agregadas opt-in de pacing, simulação, renderização
e chamada de apresentação. A lógica de cadência existente e seus limites de
callbacks/modos foram preservados. Desligado, o diagnóstico não lê estado adicional
do guest nem consulta o relógio. Ligado, registra agregados a cada5s por thread e
função; janelas não são alinhadas e os custos podem se sobrepor. Não somar tempos
de renderização e apresentação. Esses registros não provam quadros únicos.

Os modos continuam experimentais. A instrumentação serve para localizar o limite
residual antes de mexer em relógios, física ou animação. Não há novo ganho de FPS
medido nesta rodada.

## Interface e legendas

O atlas ampliado e FXAA anteriores ainda compõem texto na imagem interna do jogo;
não constituem interface em resolução própria. O presenter pode desenhar em pixels
da saída, mas falta confirmar geometria, shader, transparência, scissor e ordem das
legendas, vinculando o overlay à imagem correta. Existe um protótipo diagnóstico
privado limitado ao atlas/par de shaders já identificado, sem suprimir desenhos.
Ele passou na checagem de sintaxe Linux; não está no backend público nem instalado.

## Custo gráfico e validação pendente

Sem o dump montado, não houve nova medição de GPU, gameplay ou comparação de
30/60/ilimitado. O arquivo XEX privado preservado confere com o hash conhecido,
mas não substitui os demais arquivos do jogo no disco games. Não reduzir qualidade
nem reaproveitar resultados antigos como benchmark do novo backend.

O SDK novo compilou Release e RelWithDebInfo no Linux, em prefixo isolado, após
reconstrução exata das fontes a partir da revisão fixada e patches públicos.
A instalação anterior do workspace passou novamente na verificação de hashes.
74 testes selecionados passaram (cache, timing, receitas, presets, prewarm,
preparação e probes). São contratos de CPU/integridade; Windows nativo e gameplay
continuam pendentes. Evidências privadas: .aster/reports/graphics-2026-10-29.

O host privado com os quatro medidores também compilou e linkou, com as quatro
rotinas originais preservadas por símbolo. As dependências resolvem com o SDK
novo. Uma tela Xvfb isolada confirmou carregamento e inicialização SDL/X11;
o argumento --help continuou até a exigência de game_data_root (retorno1), logo
não é teste de gameplay nem smoke de lançamento completo. Nada foi instalado
no AppImage humano e nenhum novo pacote público foi gerado nesta etapa.

## Fechamento da rc.4 — 29/10/2026

Os pacotes `v0.1.4-rc.4` foram gerados depois desta nota. O smoke Linux e
Windows/Wine passou com versão `0.1.4-rc.4`, fontes escaláveis, imagem inicial e
aba de atualizações, sem abrir o jogo. Não houve nova medição de GPU ou campanha
nesta entrega; os controles 197/198/201 permanecem a evidência de apresentação
descrita em `STATUS.md`. O dump não foi usado para uma nova sessão de gameplay.
