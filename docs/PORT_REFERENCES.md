# Referências de ports Xbox 360 → PC

Complemento de 25/10/2026: [qualidade gráfica e distribuição](GRAPHICS_REFERENCE_STUDY.md).
A investigação inicial de boot abaixo registra o estado de 22/10; seus próximos
passos não descrevem a fase atual do projeto.

Consulta: 22/10/2026. Repositórios indicados pelo usuário. Foram lidos READMEs,
manifestos, CMake e arquivos de inicialização/diagnóstico selecionados pela API do
GitHub. Não compilamos nem executamos esses ports. Alegações de jogabilidade e
desempenho continuam sendo relatos dos mantenedores, sem validação independente.
Nenhum código, patch, endereço de outro jogo ou arte foi importado.

## O que cada referência esclarece

| Projeto | Evidência consultada | Aplicação ao Green Lantern |
| --- | --- | --- |
| [Forza Horizon 1: ReImagined](https://github.com/Dyotson/ForzaHorizon1-ReImagined) | `forza-recomp/forza_manifest.toml` separa hints por finalidade e declara módulos XEX auxiliares. Há manifestos distintos para o jogo base e TU4. | Inventariar módulos realmente usados; manter metadados vinculados à versão exata do nosso executável. Não presumir módulos ou endereços compartilhados. |
| [Hell's Gate](https://github.com/florinp93/hells-gate-recomp) | Manifesto com entradas manuais; CMake compila hooks D3D e renderizador próprio DiligentCore/Vulkan sobre ReXGlue. | Distinguir tradução da CPU, serviços do console e renderização. Um renderizador próprio exige análise adicional das interfaces gráficas do nosso jogo. |
| [Asura's Wrath](https://github.com/PauloUbirajara/asuras-wrath-recomp) | Manifesto inclui `includes/funcs.toml`; CMake solicita `GPU_PLUGINS xenos`. README documenta caminhos de dados/cache/saves e diferenças FBO/FSI. | Conferir staging do plugin e seleção explícita dos diretórios. Opções gráficas são hipóteses a testar no nosso hardware, não correções universais. |
| [MCLA](https://github.com/holdmysocks/mcla-recomp) | Manifesto distingue hints de análise, referências de dados/código e descobertas em execução. `config/mcla.toml` documenta erros UnresolvedCall; `src/mcla_app.cpp` configura caminhos e plugin. | É a referência mais direta para nosso bloqueio de destinos não reconhecidos. Registrar evidência de cada limite e separar falhas estáticas das observadas em execução. |
| [Unleashed Recompiled](https://github.com/hedge-dev/UnleashedRecomp) | README e `.gitmodules` identificam XenonRecomp e XenosRecomp; fonte organiza CPU, kernel, GPU, áudio e input em componentes distintos. | CPU recompilada não basta para obter imagem e som. O renderizador próprio é referência arquitetural, com adaptações específicas do Sonic que não transferem automaticamente. |
| [DBZ Budokai 3 HD Collection](https://github.com/novapowers0/DBZ-Budokai-3-HD-Collection) | Manifestos US/EU separados; CMake inclui fontes geradas por variante, liga runtime/plugin e exclui hooks incompatíveis com a região. | Verificar identidade do XEX antes de escolher código e metadados; empacotar dependências explicitamente. Mods e interface ficam para depois do boot validado. |
| [MojoRecomp](https://github.com/OAleex/MojoRecomp) | `runtime/boot_probe.cpp` conecta CPU, memória, kernel, GPU e diagnóstico; CMake define testes de host. README distingue jogos e estados de maturidade. | Manter diagnósticos por subsistema e distinguir executável de teste, inicialização e jogo jogável. A versão consultada anuncia suporte oficial somente a Windows. |

O conjunto reforça duas possibilidades: usar o runtime ReXGlue e seu plugin Xenos
como primeira base experimental, ou desenvolver substituições específicas para
serviços/renderização. A preferência inicial por ReXGlue é uma decisão de engenharia
para testar mais cedo; os outros ports não demonstram compatibilidade do Green Lantern.

## Aplicação imediata

O nosso ReXGlue v0.10.0 encontrou 12 erros UnresolvedCall no XEX do usuário.
O arquivo `games/green_lantern_rex_hints.toml` contém somente metadados da nossa
análise, vinculados aos hashes do XEX/PE. Oito limites concordam com Ghidra e
instruções; quatro são inferidos de fluxo, referências e/ou `.pdata`. Três retornos
internos são absorvidos nas funções que os contêm, sem inventar funções independentes.

Esses hints não vieram do MCLA: a referência ajudou na organização e no diagnóstico.
Os endereços e tamanhos foram obtidos do Green Lantern anteriormente. A execução do
gerador, mesmo quando bem-sucedida, não comprova correção semântica nem boot do jogo.

Próximas verificações: resolver a análise sem `--force`, compilar o host, conferir
carregamento do runtime/plugin, e executar uma tentativa limitada com logs e dados
originais preservados. Testar boot, apresentação de frames, áudio, input e saves
separadamente antes de habilitar o launcher como port jogável.

## Proveniência e limites

Os commits abaixo são snapshots dos HEADs retornados durante a consulta; a primeira
leitura de README/CMake usou a branch padrão. Os arquivos de inicialização e hints
selecionados posteriormente foram consultados com ref explícita nesses commits.
Os links das tabelas apontam para os projetos, cujas branches podem evoluir.

| Projeto | HEAD consultado |
| --- | --- |
| [Dyotson/ForzaHorizon1-ReImagined](https://github.com/Dyotson/ForzaHorizon1-ReImagined) | `043a4d3546e2d5974eb83c4358737e3da7df0bb4` |
| [florinp93/hells-gate-recomp](https://github.com/florinp93/hells-gate-recomp) | `3ce3993b0f03c77353f8f10fdcd982160c9a2d18` |
| [PauloUbirajara/asuras-wrath-recomp](https://github.com/PauloUbirajara/asuras-wrath-recomp) | `92989e4d81731c17cecacbdf4414ef12ae5a8100` |
| [holdmysocks/mcla-recomp](https://github.com/holdmysocks/mcla-recomp) | `3447641c025755536209ee621570d48390f4cbcb` |
| [hedge-dev/UnleashedRecomp](https://github.com/hedge-dev/UnleashedRecomp) | `cf829a9eca8fb680fba4b0409ddeb6ca92f22e3c` |
| [novapowers0/DBZ-Budokai-3-HD-Collection](https://github.com/novapowers0/DBZ-Budokai-3-HD-Collection) | `16228b5571fb86c706aaaf36af0351758625d82e` |
| [OAleex/MojoRecomp](https://github.com/OAleex/MojoRecomp) | `b5450a73f0e74b4eb06d592e623ba526873389e3` |

Não há adoção de código de terceiros nesta revisão. Licenças de ferramentas e
dependências continuam independentes; qualquer incorporação futura exige conferir
os arquivos e avisos correspondentes na revisão escolhida. Consultar arquitetura
não transfere os direitos sobre código gerado, assets ou marcas dos jogos.
