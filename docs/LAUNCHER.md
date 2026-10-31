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

Controles mostra cartões com imagens de produto do Xbox Wireless Controller e
do DualSense, com seleção de layout por clique ou teclado. Os campos ficam
agrupados em combate, movimento, câmera, navegação e ajustes dos analógicos, e a
página rola com o mouse. O schema de preferências, os binds, a validação,
**Salvar** e **Restaurar padrão** não mudaram. As imagens acompanham o launcher
e são carregadas localmente, sem downloads na abertura.

Os recibos de validação HD reutilizam artefatos já conferidos quando os arquivos
permanecem inalterados. A primeira abertura após a atualização ainda faz a
validação integral. Fontes DejaVu acompanham os executáveis e são registradas
somente no processo, sem instalar fontes no sistema ou no perfil do usuário.
A arte de fundo é procedural e original. As imagens de produto dos controles
vêm das páginas oficiais dos fabricantes, com URLs, titulares e hashes em
`native_port/resources/controllers/`, e não são arte original do projeto. Não
há código de launcher fornecido como referência nem conteúdo do jogo nos pacotes.

Atalhos: Ctrl+O escolhe a pasta; Ctrl+S salva preferências. A interface foi revisada
em 1200×820 e 1088×720, e as opções gráficas continuam acessíveis por rolagem.
