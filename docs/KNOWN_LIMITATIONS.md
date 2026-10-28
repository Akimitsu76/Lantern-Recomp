# Limitações conhecidas

- Revisão atual (27/10): dois probes Linux de dez minutos em modo 60 alcançaram
  Oa, tutorial, combate inicial e morte/recarregamento sem fatal ou falha de
  renderização detectada. Cache aquecido reduziu as pausas observadas, sem
  eliminá-las. O ilimitado alcançou a abertura nos controles de 26/10, mas ganho
  real acima de 60 FPS, campanha e Windows nativo continuam sem certificação.
  Ver RELEASE_READINESS.md; contagens e modos anteriores abaixo são históricos.
- O workflow público `native-graphics-windows.yml` só produz evidência se for
  publicado e executado. Sem escopo `workflow` no token, ele precisa ser incluído
  manualmente; não há resultado de CI Windows nesta revisão.

- Texturas HD automáticas: 253 difusos opacos revisados, com usos nas dez missões,
  Alta 2x/Ultra 4x. Os demais materiais permanecem originais. A resolução de
  saída não aumenta sozinha a escala interna, selecionável em 1x/2x/3x.
  Não existe escala interna exata de 1080p (1,5x).
  Não há certificação da campanha nem de gameplay D3D12 em Windows real.

- O backend nativo próprio do Aster Native continua sem runtime completo,
  renderização, áudio, controles ou gameplay implementados. O host experimental
  ReXGlue recompilado abre menus e o começo da missão 1; não é um port completo
  nem valida a campanha. Veja PLAYABILITY.md.
- A função de oito bytes recompilada/executada como experimento não valida o
  restante do jogo. O host ReXGlue usa código recompilado e hints; veja
  NATIVE_PROGRESS.md, XENONRECOMP_EVALUATION.md e PLAYABILITY.md.
- XEX decodificado após autorização. O original permanece intacto; os derivados
  privados ficam em `.aster/`. A antiga ISO continua sem formato reconhecido.
- REA MCP rejeita XEX e PE PowerPCBE. Ghidra direto funciona com linguagem explícita,
  mas loader PE genérico tem limitações de imports/exceptions/TLS/RTTI e VMX.
- Contagem de funções do analisador não prova cobertura completa nem nomes originais.
  Nenhuma tabela reconhecida pelo XenonAnalyse não significa ausência de indireções.
- Validadores verificam limites/estrutura, sem autenticar assinaturas criptográficas,
  mídia completa, integridade de todos os assets ou equivalência integral de CPU.
- O hash de um dump foi analisado; não há catálogo de revisões compatíveis.
- CMake e XenonRecomp locais estão disponíveis. Builds locais foram executados sem
  instalar pacotes do sistema. Dependências e obrigações de distribuição constam
  de TOOLING_LICENSES.md. Launchers Linux/Windows foram empacotados; o jogo e seus assets não são redistribuídos.
- Relatórios de análise só são associados ao mesmo hash de origem e PE normalizado
  correspondente. Compilação C++ usa incremento do Ninja; relatórios de preparação
  continuam recalculando hash/diagnóstico. Não há retomada automática de jobs.
- GUI mantém Compilar/Iniciar desabilitados para o jogo; **Jogar agora** abre o
  build local validado. Os alvos 30/60/ilimitado e os presets
  Baixa/Média/Alta/Ultra/Personalizada ficam na aba **Gráficos**. 60 e
  ilimitado são opt-in, com confirmação. Todos os alvos compartilham o save por usuário; 30 fps continua o
  padrão. Preparar mostra análise validada e experimento nativo quando
  pertencem ao mesmo dump; não inicia o probe.
- Sessão humana 058 confirmou gameplay/combate visual em 60 fps, mas teve 6
  janelas de 5 s abaixo de 59 apresentações/s (3 abaixo de 55), incluindo uma
  queda de 822 ms em transição. A percepção desses engasgos e a qualidade de
  física, animações e áudio continuam sem certificação; a sessão não mediu áudio.
- O modo ilimitado v10 tem apenas evidência automatizada: 90,16 s, 38.627
  apresentações, FSI, simulação em alvo 60/tempo real e nenhum fatal. O probe
  registra `gameplay_verified=false`; não há captura visual de gameplay no
  Xwayland. Tearing, estabilidade, áudio e comportamento de combate/física
  continuam sem validação humana. A GPU observada foi 95–96% e ~91–107 W.
- Os presets Baixa/Alta/Ultra não têm avaliação visual humana pareada nem
  medição de VRAM/desempenho em outras GPUs. O patch 0024 corrigiu a leitura de
  profundidade escalada; capturas da abertura em 2x/3x deixaram de apresentar
  as grandes áreas pretas. Isso não certifica todas as fases, sombras ou efeitos.
  FSR 1 e FXAA são aplicados à apresentação;
  resolução da janela e detalhe das texturas são conceitos separados.
- O launcher só habilita **Jogar agora** para o mesmo dump identificado e para
  builds/referências FSI presentes em `.aster/`. Não há suporte genérico a
  outras revisões do dump nem redistribuição de assets/código proprietário.
- Pasta é limitada a 100.000 arquivos e 32 níveis; links internos são rejeitados.
  Manifesto de assets usa nomes/tamanhos/mtime; completude não certificada.
- O runtime Linux atualizado usa um módulo separado para remover apenas arenas
  criadas com exclusividade por sua própria sessão. Builds anteriores podem deixar arenas `xenia_memory_*` em `/dev/shm`
  porque o runtime usa `_Exit`. A limpeza exige auditoria de inode/mapas e
  autorização explícita; não limpar `/dev/shm` genericamente.
- Isolamento de caminhos pressupõe uso local confiável; não fornece sandbox contra
  outro processo malicioso alterando symlinks em corrida.

- A integração HD é um protótipo de material revisado, com Real-ESRGAN local,
  derivada 2x e cache persistente. Não existe pacote de todas as texturas. A
  compilação e gameplay D3D12 no Windows real ainda precisam de validação.

Próximo marco: ampliar geração/análise e validar a compilação experimental
(combate, física, áudio, campanha e outras GPUs) antes de tratar o backend como
completo. Não simular sucesso de serviços ausentes para habilitar execução.

## Revisão de fontes/efeitos em 27/10 (SDK 0031–0032, integração 21)

O FXAA simplificado do Vulkan desgastava contornos finos de texto. O patch 0031
adota FXAA Quality 3.11 para acompanhar o caminho já existente no D3D12; a
comparação do parágrafo do menu manteve FSR e a fonte original, com contornos
mais contínuos. Isso corrige uma etapa de apresentação, não torna todos os atlas
originais HD. O formato opcional ASTERUI2 preserva alpha de 8 bits sem nova
compressão BC3; continua experimental, exige backend 0030 e não é ativado
automaticamente por presets.

Os logs 166 associaram uma fonte de efeitos ao seu estado de shader/sampler e
registraram c255. Essa observação não cobre todos os rastros nem autoriza alterar
seus recortes de profundidade/transparência. A qualidade de todas as partículas
e legendas durante a campanha ainda precisa de validação.

Pipelines inéditos ainda podem reter um quadro por cerca de meio segundo; os
workers e o cache persistente não garantem ausência dessa pausa na primeira vez.
Experimentos privados de compilação não fazem parte da receita pública.
No Niri/Xwayland, capturas da revisão 0031 mostraram barras laterais de cerca de
44 pixels em uma janela 1920x1080. O patch 0032 atualiza a conexão da superfície
mesmo quando a janela recebe um tamanho já conhecido; o teste 174 voltou a
preencher 1920x1080. Isso não certifica todas as configurações de monitor/DPI.

A sessão 175 (190,38 s de combate a 60 FPS) teve, entre 100–170 s, mediana de
16,75 ms, máximo de 35,18 ms e zero intervalos de apresentação acima de 50 ms
com cache aprendido. Isso não prova campanha, tempo de GPU, conteúdo único ou
FPS constante em todos os trechos. A sessão 178 teve uma pausa de 334,67 ms entre
175–225 s; não foi observada destruição de imagens Vulkan nesse intervalo. Não
atribuir todo stutter à falta de VRAM nem prometer sua eliminação nesta release.
As legendas 176/178 ficaram visualmente mais contínuas, mas a comparação não é
uma métrica pixel a pixel e não certifica todas as legendas/cenas.

O EXE foi exercitado somente sob Wine, que valida launcher/contratos, não
compilação ou gameplay D3D12 nativos. Windows nativo com GPU/D3D12 continua sem
validação. O workflow Windows foi atualizado, mas só produz evidência se for
publicado/executado; sem escopo `workflow`, ele permanece local para inclusão
manual e não há resultado de CI a anunciar.
