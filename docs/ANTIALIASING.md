# Antisserrilhado antes da ampliação

O launcher envia `--swap_post_effect` ao ReXGlue nos dois sistemas. A opção
`none` desliga apenas esse pós-processamento; ela não desliga o MSAA original
do jogo. `fxaa` suaviza bordas de alto contraste e `fxaa_extreme` usa a variante
mais sensível do SDK. O preset Baixa usa `none`; Média, Alta e Ultra usam
`fxaa`. Uma escolha manual muda o preset para Personalizada e é salva nas
preferências do launcher, sem separar ou alterar o progresso do usuário.

A sequência dos backends é a mesma: saída do jogo → correção de gamma e
luminância → FXAA → presenter e filtro de ampliação → janela. O FXAA trabalha
na resolução de origem, antes de ampliar, evitando pagar seu custo por pixel
em toda a resolução de saída. Não há histórico temporal nem vetores de
movimento. EASU reconstrói a ampliação; não substitui o passo de antisserrilhado.

O caminho Vulkan do SDK contém o shader compute GLSL com grupos 16×8. Ele
consulta o centro e quatro diagonais, mantém regiões sem contraste e filtra
as bordas com até quatro consultas adicionais. O caminho D3D12 contém os
pipelines compute FXAA e FXAA Extreme, seus shaders DXBC e a textura
intermediária para luminância. Ambos recebem o mesmo CVar e executam antes
da apresentação. Isso comprova a implementação e sua seleção; não comprova
qualidade visual ou desempenho no Windows real.

O passo custa uma textura intermediária, processamento de gamma/luminância,
um dispatch compute e sincronização de recursos. O custo em milissegundos
depende da GPU e precisa ser medido na máquina de destino. FXAA também pode
suavizar texto fino, HUD e detalhes da textura; o controle permite desligá-lo
ou escolher a variante intensa. Não elimina todo serrilhado ou cintilação de
movimento, nem adiciona detalhes que não existem nas texturas originais.

## Verificação desta alteração

Os testes cobrem a mesma política nos dois sistemas, a validação das opções,
a conversão em CVar real, migração de preferências antigas e o caminho do
controle visual até o comando que abre o jogo. Os shaders Vulkan FXAA e
FXAA Extreme extraídos do SDK local foram compilados por glslang e validados
por spirv-val. O relatório local `.aster/reports/aa-validation/report.json`
registra uma referência CPU do algoritmo em quatro bordas sintéticas e um
campo uniforme. Esse diagnóstico distingue referência matemática de execução
GPU: seus números não são benchmark nem validação visual do jogo ou Windows.
