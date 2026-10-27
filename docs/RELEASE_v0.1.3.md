# v0.1.3 — pré-release experimental (26/10/2026)

Esta é uma **pré-release experimental** do Aster Native para *Green Lantern:
Rise of the Manhunters* (Xbox 360). Ela não é uma versão estável. A campanha
completa, o jogo nativo em Windows/GPU e os alvos de 60 FPS ainda não estão
certificados.

Os downloads desta release são apenas o launcher. O jogo, o dump, os saves, as
texturas extraídas/HD e o código gerado do jogo **não** estão incluídos.

## Correções e recursos

- **Patch 0024 — profundidade em escala interna 2x/3x.** As coordenadas da cópia
  de profundidade liam o pixel vizinho nas escalas 2x/3x. A correção aplica a
  fase de meio pixel após a divisão, tanto no emissor SPIR-V quanto no DXBC. O
  caminho 1x, o teste de profundidade e a ordem dos desenhos são preservados;
  profundidade e oclusão não foram desativadas. A abertura foi testada em 1440p
  e 4K; isso não certifica a campanha inteira.
- **Patch 0025 — pré-compilação de shaders conhecidos.** A opção
  **Pré-compilar shaders conhecidos antes de jogar** vem ligada por padrão.
  Desligá-la preserva o cache e não impede a preparação sob demanda. Variantes
  inéditas ainda podem causar engasgos; não há promessa de zero stutter nem de
  que toda compilação ocorra uma única vez.
- **Patch 0026 — cache de formato do pipeline final do presenter Vulkan.** O
  presenter não guardava o formato do swapchain depois de criar o pipeline final.
  Isso fazia a apresentação esperar pela GPU e recriar o pipeline a cada quadro.
  Agora o formato é registrado apenas após sucesso, pipelines compatíveis são
  reutilizados, mudanças reais de formato mantêm a sincronização necessária e
  uma falha de criação pode ser tentada novamente. O defeito específico é do
  caminho Vulkan; não há ganho medido equivalente em D3D12/Windows.
- **Presets e imagem independentes.** O menu Gráficos oferece Baixa, Média, Alta,
  Ultra e Personalizada. A saída **1920×1080 (Full HD)** está disponível em todos
  os presets. Em Personalizada, saída, escala interna, texturas, filtragem, AA e
  FPS podem ser escolhidos separadamente — por exemplo, saída 1080p com texturas
  Ultra e escala 1x, sem obrigar 4K interno.
- **Escala interna atual.** 1x = 720p, 2x = 1440p, 3x = 2160p. Ainda **não
  existe** 1080p interno exato em 1,5x; implementar isso exige adaptar
  endereçamento, resolves e amostragem, não apenas trocar um seletor.
- **Saves e cache compartilhados.** Os dados pertencem ao usuário e são comuns
  entre configurações gráficas e alvos de FPS. Atualizações do launcher instalam
  apenas os recursos públicos e preservam builds, preferências, cache e saves.
- **Preparação de requisitos.** Ao confirmar **Gerar port**, o launcher pode
  preparar dependências ausentes usando planos fixos para distribuições Linux
  conhecidas e IDs oficiais do WinGet/VS2022/C++/Clang/runtime no Windows. Isso
  pode exigir administrador e vários GB. Drivers de GPU não são instalados;
  WinGet/PolicyKit ausentes e sistemas sem plano conhecido produzem erro
  explicativo. A função foi testada por contratos, não em uma máquina limpa.
  A toolchain C++23 continua necessária para **gerar** o port; abrir um port já
  preparado não deve reinstalar as ferramentas.

## Desempenho observado

Controle local 142→143, na abertura: renderização interna 1440p, saída 1080p,
ilimitado, sem AA/AF, mesma base de cache e mesmas entradas. Nas janelas de 5
segundos após 100 s, a mediana passou de **24,80 para 44,28 apresentações
Vulkan/s**, e as criações de pipeline nessas janelas caíram de **1.232 para 0**.

O controle 144, em modo 60 com FSR 1/FXAA/8x, teve mediana de 43,70
apresentações/s. O controle 141, em 720p interno e saída 1080p, teve 60,00/s.
São testes curtos de abertura, não um benchmark universal de GPU, campanha ou
conteúdo único. Não há garantia de 60 FPS constantes em 2x, de ganho acima de 60
FPS ou de ausência de engasgos.

## O que ainda não está validado

- Campanha inteira, transições, mortes/recarregamentos e todas as cenas.
- Jogo nativo em Windows real, D3D12 e GPU Windows; Wine valida apenas o
  launcher/contratos, não gameplay.
- Compilação C++ nativa em Windows via CI; nenhum workflow de CI foi publicado
  nesta revisão e nenhuma execução de CI ocorreu.
- 60 FPS estáveis em 2x, desempenho acima de 60 e ausência de stutter.
- Avaliação visual completa de FSR/FXAA, sombras, partículas e texturas HD.
- Instalação real de dependências em máquina limpa Windows/Linux.
- Assinatura digital dos executáveis; eles não são assinados.

As texturas HD são recursos locais derivados do dump, com um catálogo revisado
de 253 materiais. Não são o jogo inteiro em HD e não acompanham esta release.

## Como usar

### Linux

1. Baixe `AsterNative-linux-x86_64.AppImage` e `SHA256SUMS`.
2. Dê permissão de execução: `chmod +x AsterNative-linux-x86_64.AppImage`.
3. Abra o AppImage. Se o sistema não tiver FUSE, use
   `./AsterNative-linux-x86_64.AppImage --appimage-extract-and-run`.
4. Selecione a pasta extraída que contém `default.xex` e os demais arquivos do
   jogo.
5. Use **Atualizar port** (ou **Gerar port**) para obter o backend novo.

### Windows

1. Baixe `AsterNative-windows-x64.exe` e `SHA256SUMS`.
2. Abra o `.exe` (não é necessário instalar Python).
3. Selecione a pasta extraída do jogo.
4. Use **Atualizar port** (ou **Gerar port**) para obter o backend novo.

O primeiro uso instala os recursos públicos em
`%LOCALAPPDATA%/AsterNative/app` no Windows ou
`${XDG_DATA_HOME:-~/.local/share}/aster-native/app` no Linux. O jogo não é
baixado. É necessário fornecer um dump próprio completo da revisão suportada.
Confira `SHA256SUMS` antes de abrir os executáveis.

## Verificação desta revisão

- Linux: 379 testes, 1 ignorado, sem falhas, com Xvfb e acesso de display.
- Contratos Windows/Wine: 353 testes, 25 ignorados, sem falhas. Os testes C++
  que exigem compilador são ignorados no Wine; a compilação C++ nativa em
  Windows continua pendente e não foi coberta por CI nesta revisão. Isso não
  substitui uma partida nativa.
- Os testes C++ do 0026 executam o ramo real do presenter no Linux.

Evidências privadas de sessões e relatórios não são enviadas ao repositório nem
aos assets.
