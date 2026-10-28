# Launcher Green Lantern — interface de 28/10/2026

A mesma interface é usada em Linux e Windows. A página Início apresenta o jogo,
a seleção do dump e ajustes rápidos de qualidade, resolução de saída, FPS e
janela/tela cheia. As escolhas editam as mesmas preferências da página Gráficos;
salvar e jogar ficam no rodapé de todas as páginas.

A ação principal gera ou atualiza o port quando necessário e abre o jogo quando
a instalação está preparada. A página Preparar mantém as seis etapas: conferência
do dump, ferramentas, gráficos, geração de código, compilação e verificação.
A barra principal e o percentual representam a preparação completa; a segunda
barra mostra a etapa atual. Etapas sem contagem conhecida mantêm indicador de
atividade, sem percentual inventado. Cancelar aparece durante uma tarefa;
Encerrar jogo aparece somente para a sessão iniciada pelo próprio launcher.

Gráficos conserva os presets e os controles personalizados, incluindo 1080p/4K
de saída, escala interna independente, texturas, filtragem, antisserrilhado,
VSync e preparação de shaders. As limitações de escala/FPS/campanha continuam
as mesmas descritas nos documentos de validação: esta é uma atualização de
launcher, não uma certificação nova do jogo.

Os recibos de validação HD reutilizam artefatos já conferidos quando os arquivos
permanecem inalterados. A primeira abertura após a atualização ainda faz a
validação integral. Fontes DejaVu acompanham os executáveis e são registradas
somente no processo, sem instalar fontes no sistema ou no perfil do usuário.
A arte de fundo é procedural e original. Não há imagens ou código do launcher
fornecido como referência nem conteúdo do jogo nos pacotes.

Atalhos: Ctrl+O escolhe a pasta; Ctrl+S salva preferências. A interface foi revisada
em 1200×820 e 1088×720, e as opções gráficas continuam acessíveis por rolagem.
