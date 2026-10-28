# v0.1.4-rc.2 — pré-release experimental (27/10/2026)

Esta é uma **pré-release experimental** do Aster Native para *Green Lantern:
Rise of the Manhunters* (Xbox 360). Ela **não é stable** e não deve ser anunciada
como tal. A campanha completa, o jogo nativo em Windows/GPU, a ausência de
engasgos e ganhos acima de 60 FPS continuam sem certificação. **30 FPS segue
como padrão**; 60 FPS e ilimitado permanecem experimentais.

Os downloads são apenas o launcher. O jogo, o dump/XEX/ISO, os saves, as
texturas extraídas ou ampliadas e o código recompilado do jogo **não** estão
incluídos. Os executáveis não são assinados digitalmente.

## Mudanças desta candidata

- **Patch 0031 — FXAA Quality 3.11 no Vulkan.** O filtro simplificado anterior
  desgastava contornos finos de letras. O adaptador Vulkan passa a usar o mesmo
  caminho de qualidade do D3D12, com os presets normal 12/subpixel 0.75 e
  extremo 39/subpixel 1.0. O bytecode FXAA Quality já existente no D3D12 é
  preservado. As comparações 163–167 separaram FSR e FXAA e mantiveram FSR e a
  fonte original; o texto do menu ficou visualmente mais contínuo. Isso corrige
  uma etapa de apresentação, **não** cria fonte vetorial/HD nem certifica todas
  as legendas, partículas ou cenas.
- **Patch 0032 — apresentação após tamanho nativo repetido.** Quando o evento
  nativo repete um tamanho que o Window já conhece, a conexão do presenter é
  atualizada sem reenviar listeners de resize. O caso observado era uma
  superfície em 1920×1030 em cache contra uma janela 1920×1080; a sessão 174
  voltou a preencher Full HD. O teste C++ reproduz o contrato e cobre resize
  real, listener duplicado e destruição da janela. Não é validação de todos os
  monitores, DPI ou gerenciadores de janela.
- **Patch 0030 — ASTERUI2 RGBA8 opcional.** O formato de cobertura branca
  preserva alpha de 8 bits sem uma nova compressão BC3, mantendo métricas, UVs e
  fingerprints da fonte. Recursos e views correspondentes foram ajustados em
  Vulkan e D3D12; ASTERUI1 continua compatível. É uma experiência explícita de
  CLI (`texture-ui-prepare --coverage-format rgba8`), **não** habilitada
  automaticamente nos presets e **não** uma promessa de todas as fontes HD.
- **Patch 0029 — diagnóstico opcional de c255.** Os bits crus da constante
  pixel float4 255 podem ser registrados junto ao diagnóstico limitado de
  transparência. O patch não altera recorte/alpha por suposição nem amplia todo
  atlas de partículas. A observação 166 é limitada e não cobre todos os rastros.
- **Revisão r4 — gate de backend compartilhado.** Launcher e comando de execução
  verificam versão/correções do backend em Linux e Windows e registram no log a
  integração efetivamente instalada. Os próprios AppImage/EXE rejeitaram um
  manifesto sintético de backend 20 **antes** de abrir o jogo ou acessar save.
  Trocar apenas o launcher não recompila um renderizador antigo.
- **Experimentos privados rejeitados.** Desativar a otimização do driver e
  pré-otimizar SPIR-V não eliminaram o custo de pipeline inédito. Esses IRs,
  capturas e bibliotecas de experimento **não** fazem parte da receita pública.

## Evidência resumida

- Suítes registradas na revisão r4: **398 testes Linux (2 ignorados)** e **372
  testes Windows/Wine (32 ignorados)**, sem falhas. Uma re-execução de
  publicação no Linux também passou 398 testes com 0 falhas e 5 ignorados por
  pré-requisitos opcionais do ambiente. Wine valida launcher/contratos; não
  substitui compilação SDK/D3D12 nem gameplay em Windows real.
- **126 entradas públicas por plataforma** foram comparadas entre payload e
  fontes, com `README.md` mapeado para `docs/PORTABLE_BUILD.md`; nenhum conteúdo
  proibido foi encontrado. O teto GLIBC medido do launcher Linux é **2.27**;
  isso não reduz automaticamente os requisitos do SDK/jogo descritos em
  `PORTABLE_BUILD.md`.
- O XEX original (`3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1`)
  e os três arquivos do perfil humano permaneceram idênticos.
- Sessão **175**: 190,38 s em combate a 60 FPS. Entre 100–170 s, mediana de
  16,75 ms, máximo de 35,18 ms e **zero** intervalos de apresentação acima de
  50 ms com cache aprendido. São timestamps de apresentação; isso não prova
  campanha, tempo de GPU, conteúdo único ou FPS constante em todos os trechos.
- Sessão **178**: uma pausa de **334,67 ms** entre 175–225 s. Não foi observada
  destruição de imagens Vulkan nesse intervalo; o resultado não atribui todo
  stutter à falta de VRAM nem promete eliminá-lo nesta release.
- **176/178**: legendas da abertura visualmente mais contínuas com FSR, FXAA
  intenso, dithering e a biblioteca HD do usuário preservados. A comparação é
  visual, com palavras/fundos diferentes; **não** é fonte vetorial/HD nova nem
  certificação de todas as legendas.
- O AppImage Linux do usuário foi atualizado de backend 20 para **21** com 8
  arquivos verificados, saves preservados e o build anterior mantido. No
  Windows, o usuário recebe o EXE e as mesmas fontes públicas e gera o backend
  no próprio PC.

## Como atualizar

1. Baixe o novo `AsterNative-linux-x86_64.AppImage` ou
   `AsterNative-windows-x64.exe` e o `SHA256SUMS`; confira o hash antes de abrir.
2. Substitua o executável antigo. Atualize também atalhos/Steam que ainda
   apontem para o arquivo anterior.
3. Abra o launcher e use **Gerar port** ou **Atualizar port** para recompilar o
   backend com integração 21 e os patches até 0032. Apenas trocar o launcher
   não atualiza o renderizador.
4. **Não apague saves ou caches** para fazer a atualização. O build anterior é
   preservado; o novo backend é instalado ao lado.
5. Se o launcher informar backend antigo ou correções ausentes, repita
   **Atualizar port** antes de jogar.

### Linux

1. `chmod +x AsterNative-linux-x86_64.AppImage`.
2. Abra o AppImage. Sem FUSE, use
   `./AsterNative-linux-x86_64.AppImage --appimage-extract-and-run`.
3. Selecione a pasta extraída que contém `default.xex` e os demais arquivos.
4. Use **Atualizar port** (ou **Gerar port**).

### Windows

1. Abra o `.exe`; não é necessário instalar Python.
2. Selecione a pasta extraída do jogo.
3. Use **Atualizar port** (ou **Gerar port**) para gerar o backend localmente.

O primeiro uso instala recursos públicos em
`%LOCALAPPDATA%/AsterNative/app` no Windows ou
`${XDG_DATA_HOME:-~/.local/share}/aster-native/app` no Linux. O jogo não é
baixado. É necessário fornecer um dump próprio da revisão suportada.

## Limites conhecidos

- Um pipeline realmente inédito ainda pode reter um quadro por cerca de 0,5 s.
  Worker assíncrono e cache conhecido não prometem zero pausas na primeira vez.
- Rastros, partículas e todas as legendas/cenas ainda precisam de revisão. A
  melhoria observada nas legendas da abertura não se generaliza para a campanha.
- A sessão 175 é uma cena curta de combate; não certifica a campanha, o tempo de
  GPU, conteúdo único ou FPS constante. A pausa de 334,67 ms na sessão 178 não
  foi totalmente explicada e não deve ser atribuída apenas à VRAM.
- **Windows nativo com GPU/D3D12 não foi validado.** O EXE foi exercitado
  somente sob Wine, que valida launcher/contratos, não compilação ou gameplay
  D3D12 nativos. A compilação e execução nativas continuam pendentes.
- O workflow `native-graphics-windows.yml` foi atualizado para compilar o SDK
  sem assets de jogo e executar os contratos nativos/GUI. Se o token de
  publicação não tiver escopo `workflow`, o arquivo não pode ser enviado nem
  executado; nesse caso ele permanece no checkout local para inclusão manual e
  **nenhum resultado de CI deve ser anunciado**.
- A revisão corrige um defeito de apresentação e melhora o filtro; não é um
  remaster completo nem uma certificação stable.

## Assets desta release

- `AsterNative-linux-x86_64.AppImage` — 48.486.904 bytes —
  `a17367107334904bf1ce40a2a9baae1132732742f72c36de6f51fa24aa3fd85f`
- `AsterNative-windows-x64.exe` — 58.043.141 bytes —
  `eaf34a23bdf80ad1b51479fd13d12d185932a377a1e29c45ceb84096e78079fa`
- `SHA256SUMS`
- `LEIA-ME-CANDIDATA.txt`

Pastas de build, dumps, saves, capturas, logs privados, texturas e código
recompilado do jogo não fazem parte dos assets. Evidências privadas de sessões e
relatórios não são enviadas ao repositório nem aos assets. Consulte
`RELEASE_READINESS.md`, `KNOWN_LIMITATIONS.md` e `PORTABLE_BUILD.md` para os
critérios e limites completos.
