# Viabilidade — 22/10/2026

**Atualização posterior à autorização:** decodificação, análise Ghidra e recompilação
de uma função real concluídas. Veja [NATIVE_PROGRESS.md](NATIVE_PROGRESS.md) para
resultados atuais e limitações. A avaliação inicial abaixo permanece histórica.


**Atualização:** o usuário forneceu uma pasta extraída com XEX válido por
cabeçalho/Title ID. Veja [avaliação do XEX real e XenonRecomp](XENONRECOMP_EVALUATION.md).
As observações da ISO abaixo permanecem históricas. O novo bloqueio imediato é
o carregamento do XEX criptografado e a preparação das ferramentas; nenhum
código do jogo foi recompilado.

## Conclusão

A estratégia candidata é híbrida: recompilar CPU PowerPC antecipadamente e
fornecer runtime para APIs, gráficos, áudio e demais serviços. ReXGlue merece
um experimento isolado após obter um XEX válido. **A compatibilidade de Green
Lantern com qualquer recompilador ainda não foi demonstrada.** Não há base
para declarar um port completo ou estimar seu prazo.

## Evidência local

O repositório estava vazio, sem commits. REA MCP 6.7.0 respondeu ao comando
`binary_session({})`. O provider Ghidra 12.1.4 está disponível com Java 21 e
decompilador ELF x86_64. Nenhum alvo do jogo foi importado. A lista da sessão
anuncia 207 ferramentas, incluindo open_binary, binary_session, binary_overview,
procedure_pseudo_code, procedure_references e xrefs. As operações de funções
exigem um alvo aberto e uma importação concluída; sua existência não prova
que o loader XEX está instalado. O relatório local do REA foi preservado em
`.aster/reports/rea-session.json`.

GCC, Clang, Ninja e Python disponíveis. CMake, XenonRecomp e rexglue ausentes do
PATH. O teste C++ compilou e executou um programa próprio, sem código do jogo.
Veja ENVIRONMENT.md para versões.

A busca limitada encontrou `/caminho/do/jogo/Green Lantern.iso`,
7.838.695.424 bytes. O usuário confirmou ter apenas a ISO. A leitura dos cinco
offsets usados como candidatos pelo Xenia não encontrou XDVDFS; uma busca
somente de leitura por toda a imagem também não encontrou `MICROSOFT*XBOX*MEDIA`
nem `CD001`. A varredura reproduzível encontrou duas ocorrências de XEX2, ambas com
cabeçalhos inconsistentes: offsets 0x6c9da883 e 0xd3d9f05d, com 856.857.230
e 987.085.316 cabeçalhos opcionais declarados. Nenhuma é XEX reconhecido.
SHA-256 local: `9b34f86d8846252e0b87ef80496f1049582518154e5f43de9c61fc051af5dc70`.

Não foi demonstrado que o arquivo seja uma imagem XDVDFS utilizável, nem que
pertença ao jogo. Ausência de assinatura não prova DRM, corrupção ou origem
incorreta. Formato desconhecido, conteúdo transformado, dump inconsistente e
proteção são hipóteses. Não houve tentativa de descriptografia ou contorno.
A extração e a importação do jogo no Ghidra permanecem bloqueadas.

## Projetos pesquisados (fontes primárias)

| Projeto | Evidência e licença | Adequação / limite |
|---|---|---|
| [XenonRecomp](https://github.com/hedge-dev/XenonRecomp) | README: PPC → C++; MIT. CMake exige >=3.20/C++17. Repositório apresenta 181 commits. Histórico de commits retornou HTTP 429; último push não confirmado. | Não fornece runtime. Exige identificar funções, indireções e serviços. Sem teste com este jogo. |
| [ReXGlue SDK](https://github.com/rexglue/rexglue-sdk) | C++ antecipado, fundamentos do Xenia; [licença BSD de três cláusulas](https://github.com/rexglue/rexglue-sdk/blob/main/LICENSE), preserva atribuições de Tom Clay e Xenia. [Build](https://github.com/rexglue/rexglue-sdk/blob/main/CMakeLists.txt): >=3.25, versão-base 0.10.0. Histórico consultado inclui commits de agosto/2026; README avisa sobre API instável. | Candidato para CPU + runtime reaproveitado. Ainda não integrado ou compilado localmente. Auditoria de dependências/licenças transitivas e revisão fixada ainda pendentes. |
| [XEXLoaderWV](https://github.com/zeroKilo/XEXLoaderWV) | Extensão de importação Ghidra, não recompilador. [Código do loader](https://github.com/zeroKilo/XEXLoaderWV/blob/master/XEXLoaderWV/src/main/java/xexloaderwv/XEXLoaderWVLoader.java) seleciona `PowerPC:BE:64:A2ALT-32addr`. Histórico consultado inclui dezembro/2025. Não foi localizada licença de redistribuição na raiz consultada; licença permanece não confirmada. | Não instalado/integrado; compatibilidade com Ghidra 12.1.4 não comprovada. Não executar automaticamente suas rotinas de tratamento de conteúdo protegido. |

As páginas web podem ser indexadas com atraso; não afirmamos o último commit
atual de cada projeto. Nenhum script externo foi executado. Não foi encontrado
projeto específico de recompilação de Green Lantern nas buscas efetuadas;
isso não comprova inexistência.

O [relato Xenia #1803](https://github.com/xenia-project/game-compatibility/issues/1803)
associa Green Lantern a Title ID **575207E9** e descreve gameplay com falha num
build de 2021. É evidência histórica de **emulação**, não de recompilação ou
compatibilidade deste dump. O módulo usa esse ID como identificação inicial;
nenhuma revisão foi reconhecida por hash.

## Distinções técnicas

- Recompilação estática: instruções do jogo viram código hospedeiro antes da execução.
- Reimplementação: novo código reproduz comportamento da engine ou de seus serviços.
- Tradução dinâmica: instruções convidadas são traduzidas durante a execução.
- Emulação: reproduz a plataforma; pode usar intérprete ou tradução dinâmica.

Um runtime reutilizado do Xenia pode acompanhar CPU estaticamente recompilada;
isso exige descrever também a tradução de comandos GPU e os serviços mantidos.
Não significa engine inteiramente reescrita. Um launcher de emulador não satisfaz
o objetivo e não foi implementado.

## Obstáculos e plano priorizado

1. **Entrada:** identificar o formato/proveniência do dump e obter uma imagem
   estruturalmente válida. Implementar extrator XDVDFS só após validar limites,
   árvore de diretórios e casos malformados; nunca escrever na origem.
2. **Executável:** extrair XEX/assets para workspace isolado. Ler execution info,
   versão, criptografia/compressão e imports sem contornar proteções. Validar loader
   e arquitetura em Ghidra; registrar hash, entrada, regiões e chamadas observadas.
3. **Experimento CPU:** fixar revisão/licenças do backend escolhido; inspecionar
   fontes/build antes de executar. Recompilar função identificada e comparar efeitos
   em memória/registradores com referência. O host probe atual não faz isso.
4. **Runtime:** inventariar APIs realmente usadas; memória big-endian e ponteiros
   de 32 bits, chamadas indiretas, VMX, exceções, threads e temporização. Depois
   implementar arquivos, input, áudio e GPU Xenos conforme evidência do binário.
5. **Jogo:** provar inicialização, primeiro frame, áudio, controle, salvamento,
   progressão e estabilidade. Só marcar pronto após validar esse artefato real.

## Protótipo já verificável

Launcher + seleção de pasta com XEX/assets, preferências persistentes, logs
exportáveis e inspeção/preparação com fixtures sintéticas, relatórios e identificação
por Title ID. C++ host probe valida apenas toolchain/ELF. A ISO real é rejeitada
com erro rastreável. Não existe pipeline de recompilação do jogo implementado.

Referências de formato: [Xenia disc_image_device.cc](https://github.com/xenia-project/xenia/blob/master/src/xenia/vfs/devices/disc_image_device.cc),
[XEX2 structs](https://github.com/xenia-project/xenia/blob/master/src/xenia/kernel/util/xex2_info.h),
[GetOptHeader](https://github.com/xenia-project/xenia/blob/master/src/xenia/cpu/xex_module.h).
Os validadores implementados são parciais e não verificam assinatura criptográfica.
