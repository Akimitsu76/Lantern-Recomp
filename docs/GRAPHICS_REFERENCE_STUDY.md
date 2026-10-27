# Referências para qualidade gráfica e distribuição

Consulta: 25/10/2026. Complementa `PORT_REFERENCES.md`, cuja investigação inicial
de boot é histórica. Os projetos abaixo não foram compilados nem executados aqui.
Documentação, anúncios e código têm níveis de evidência diferentes; uma opção no
README não comprova estabilidade nem permite transferir endereços entre jogos.

## Mecanismos relevantes

| Referência e evidência lida | Aprendizado aplicável ao Green Lantern | Limite |
| --- | --- | --- |
| [Unleashed: FPS](https://github.com/hedge-dev/UnleashedRecomp/blob/main/UnleashedRecomp/patches/fps_patches.cpp) e [vídeo](https://github.com/hedge-dev/UnleashedRecomp/blob/main/UnleashedRecomp/patches/video_patches.cpp), código | Existem correções distintas para câmera, interpolação, partículas e temporizadores de chefes. A filtragem de primitivas 2D também recebe tratamento próprio. Nosso teste de FPS precisa cobrir esses subsistemas, além de contar frames. | As funções e condições são específicas do Sonic. Um desbloqueio global não equivale a independência de FPS. |
| [Hell's Gate: hooks D3D](https://github.com/florinp93/hells-gate-recomp/blob/main/src/renderer/d3d_hooks.cpp), [cache de texturas](https://github.com/florinp93/hells-gate-recomp/blob/main/src/renderer/texture_cache.cpp) e [tempo da UI](https://github.com/florinp93/hells-gate-recomp/blob/main/src/frame_rate_hooks.cpp), código | Hooks observam os desenhos e encaminham operações gráficas; recursos resolvidos podem ser encontrados pelo endereço de origem. A UI possui atualização e histórico de botões próprios para taxas altas. Separar produtor, resolve, consumidor e apresentação é uma direção útil de diagnóstico. | Substituir o renderizador exige mapear as interfaces e a sincronização do nosso XEX. Não é uma troca de configuração. |
| [Forza Horizon 1: renderização](https://github.com/Dyotson/ForzaHorizon1-ReImagined/blob/main/docs/rendering.md), documentação técnica | O relato separa escala da cena e HUD e descreve corrupção ao transferir resolves entre escalas, com layout em grupos de 16 bytes e endian. Também distingue arte de um atlas da resolução do alvo da interface. | É uma pista de investigação; nossos controles não usam caches de cena/HUD com escalas diferentes. Não demonstra a causa das nossas áreas pretas. |
| [Crash of the Titans: preparação de shaders](https://github.com/VitoMiguelF/crashott-pc/blob/main/runtime/gpu/shader_warmup.cpp), código | Inventaria fontes do jogo e microcódigo observado, prepara variantes normal/escalada, verifica hashes e grava arquivos temporários antes de renomear. O trabalho em segundo plano tem prioridade baixa. | Preparar shaders conhecidos não cobre variantes nunca vistas nem, por si só, todas as combinações de pipeline do driver. |
| [Budokai 3: cache HD](https://github.com/novapowers0/DBZ-Budokai-3-HD-Collection/blob/main/patches/rexglue-sdk/src/graphics/dbz3_texture_pack.cpp), código | Há filas de decodificação, orçamento de cache, pré-carregamento e persistência dos recursos usados. Essas etapas precisam ter limites de memória e não bloquear o caminho de desenho. | Não comprova ausência de engasgos em nosso backend nem autoriza aplicar o mesmo processamento a fontes, normal maps e transparência. |
| [SpartanPort: pesquisa de upscaling](https://github.com/FelipePrado0/SpartanPort/blob/main/docs/upscaler.md), documentação com estado explícito | Reconstrução temporal depende de cena, profundidade, movimento e histórico corretos; HUD deve ser composto depois. O documento registra custos e regressões da escala de passes intermediários. | O aviso de 14/10 informa que os upscalers descritos foram desativados no caminho atual. A pesquisa não é promessa de recurso estável do release. É PS4, com arquitetura distinta. |
| [inFAMOUS Second Son](https://github.com/HayatoG/iss_pc), README | Relata cache versionado, compilação assíncrona, limites de memória e problemas ainda em teste nas partículas. É útil para organizar invalidação e diagnóstico. | Código original x86-64 de PS4 com GPU traduzida para Vulkan; não é recompilação PowerPC. As correções de ondas/subgrupos não transferem diretamente para Xenos. |
| [BLACK](https://github.com/Spark198rus/black-pc), README | Relata ajustes separados de resolução, efeitos e costuras geométricas. Distingue dependências para desenvolver das necessárias para executar. | Xbox original x86; Linux documentado via Wine/DXVK. Isso não valida um backend Linux nativo do nosso port. |
| [Azimuth](https://almost-there-games.itch.io/azimuth), página oficial | Referência de produto: presets alteram sombras, reflexos e modelos, além da resolução. | Wrapper de Xbox One, Windows e Proton; a página não fornece a implementação para inspeção. |

As referências anteriores — [Asura](https://github.com/PauloUbirajara/asuras-wrath-recomp),
[MCLA](https://github.com/holdmysocks/mcla-recomp),
[Mojo](https://github.com/OAleex/MojoRecomp) e
[XenonRecomp](https://github.com/hedge-dev/XenonRecomp) — continuam no catálogo
`PORT_REFERENCES.md`. Os achados anteriores sobre manifestos, identidade do jogo,
boot e empacotamento permanecem úteis; não constituem nova validação gráfica.

## Aplicação e ordem de trabalho

1. Corrigir as áreas pretas em escala interna maior, identificando o primeiro
   passe incorreto e suas entradas. Os controles já realizados constam em
   `VISUAL_QUALITY.md`. Não ativar 2×/3× nos presets sem comparação visual.
2. Separar arte e amostragem de fontes, HUD, partículas e materiais opacos.
   Preservar transparência e métricas. O atlas experimental de fontes já foi
   selecionado em execução, mas a melhora visual ainda precisa ser demonstrada.
3. Medir preparação de shaders e pipelines com cache frio e quente. Registrar
   compilações durante a partida e tempos de frame; compilação assíncrona que
   omite desenhos temporariamente também precisa de avaliação visual.
4. Validar 30/60/ilimitado em movimento, câmera, ataques, partículas, interface,
   transições, física e chefes; registrar o alcance real na campanha. A campanha
   inteira e uma partida Windows nativa ainda não estão certificadas.
5. Somente depois desses problemas e da validação de campanha, concluir o
   launcher e a distribuição Linux/Windows conforme solicitado pelo usuário.

## Requisito de distribuição reservado para a etapa seguinte

O usuário quer baixar o executável da sua plataforma, selecionar o próprio dump,
preparar o jogo e jogar sem procurar ferramentas de desenvolvimento por fora.
O pacote deve oferecer o runtime necessário e uma preparação guiada, com
progresso por etapas, retomada e tamanho de downloads informado.

O projeto deve avaliar um runtime pré-compilado com metadados locais, a preparação
embutida, ou ferramentas de geração isoladas e removíveis após a preparação.
A escolha ainda não está implementada. A geração local atual usa compilador e
SDK; esconder seus downloads não elimina o consumo de disco. Para executar um
port já preparado, o produto final não deve exigir reinstalar essas ferramentas.
Medir separadamente download, pico de disco na preparação e tamanho permanente.
Não embutir dumps, saves, shaders extraídos ou texturas derivadas do jogo nos releases.

## Proveniência

Consulta pela API do GitHub em branches padrão; hashes abaixo identificam os
blobs efetivamente lidos, não commits de todo o projeto. Os links podem evoluir.

| Arquivo | Git blob SHA |
| --- | --- |
| Unleashed `patches/fps_patches.cpp` | `322073cfcb756e2a318c806c140e3550bccebb18` |
| Unleashed `patches/video_patches.cpp` | `a2320b37ba215ac3cfecd28f286bb22beb923b0a` |
| Hell's Gate `src/renderer/d3d_hooks.cpp` | `8420732ede19392b38ba0dcc2a17da856a66da4b` |
| Hell's Gate `src/renderer/texture_cache.cpp` | `5d8be47913d64188fde21da9be3f2128a47bab42` |
| Hell's Gate `src/frame_rate_hooks.cpp` | `b2a4ef250ee11917d847277d98dc02a33494768a` |
| Forza `docs/rendering.md` | `29ef3af6e461b04c3064882d471cb5c53d5d2fbb` |
| Crash `runtime/gpu/shader_warmup.cpp` | `5e7a228bb7f8df516910556a17185047d2e4e15e` |
| Budokai `patches/rexglue-sdk/src/graphics/dbz3_texture_pack.cpp` | `f6e9c6ab2b3a7b6273396ae9df36692b32b2c290` |
| Spartan `docs/upscaler.md` | `66688f9387e274850b60d66c0b27bd8a76e1533b` |
| ISS `README.md` | `44de7873c89eda3a811ca18ae92a3b1e94186fdc` |
| BLACK `README.md` | `277addec5379bc8acad83748d8f1e9b174ea729d` |

Nenhum código ou asset desses projetos foi incorporado nesta consulta.
