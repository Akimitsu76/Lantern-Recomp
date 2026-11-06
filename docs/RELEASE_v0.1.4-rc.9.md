# v0.1.4-rc.9 — Link Windows corrigido (`roundevenf`)

Esta pré-release experimental publica o launcher `0.1.4-rc.9`. Ela não é stable
e não certifica a campanha completa.

## O que mudou

A geração do port no Windows falhava no link final com:

```text
lld-link: error: undefined symbol: roundevenf
```

O clang-cl se apresenta ao CMake como MSVC. O helper do SDK aplica `-msse4.1`
somente quando `NOT MSVC`, então o projeto ficava sem SSE4.1 no Windows. Sem
esse baseline, o SIMDe do código gerado usa `__builtin_roundevenf`, que o
clang-cl rebaixa para a função C23 `roundevenf`, ausente no CRT da Microsoft.
No Linux o mesmo helper adiciona SSE4.1 e o símbolo resolve pela libc.

O CMakeLists gerado para Windows agora recebe `add_compile_options(-msse4.1)`,
sem substituir os flags padrão do CMake/MSVC. O flag também entra na receita
(`project_flags`), então um port Windows gerado antes desta correção é
recompilado em vez de reutilizar o cache quebrado. O modo leve da rc.8 continua
incluído e habilitado por padrão.

## Evidência desta revisão

- O `aster_green_lantern_recomp.63.cpp` real foi compilado com clang para
  Windows: sem o flag, o objeto contém `U roundevenf`; com `-msse4.1`, nenhuma
  referência ao símbolo.
- A suíte completa passou no Linux com **507 testes, 27 skips e 322 subtests**,
  sem falhas.
- O smoke do AppImage Linux informa versão `0.1.4-rc.9`, Tk 9.0, fontes
  escaláveis, arte de fundo pronta, aba de atualizações e `game_launched=false`.
- O smoke do EXE Windows passou sob Wine com perfil `ASTER_DATA_HOME` isolado:
  versão `0.1.4-rc.9`, Tk 8.6, fontes escaláveis, aba de atualizações e
  `game_launched=false`. Windows nativo/D3D12 continua sem certificação.
- Os pacotes não incluem conteúdo do jogo; o payload público foi auditado.

## Limites

Windows nativo/D3D12 continua sem validação; o EXE é exercitado sob Wine, que
não certifica GPU ou gameplay nativos. A campanha completa, o tutorial do
Disparo do Anel e os modos 60 FPS/ilimitado seguem experimentais. Não há
arquivos do jogo nestes pacotes; é necessário seu próprio dump compatível.

## Downloads

- `AsterNative-linux-x86_64.AppImage` (55.970.296 bytes) — SHA-256
  `1dfaceb7f1923568e994a2773740b1abdcf3492693ed4cb252701f27bf2b69cb`
- `AsterNative-windows-x64.exe` (69.459.518 bytes) — SHA-256
  `03c5f8f9cd837bea9d6eae924e440b4d958dada9e1bf0cb841b7145521fe6833`
- `SHA256SUMS`
- `LEIA-ME-ATUALIZACAO.md`

No Linux, marque o AppImage como executável; se FUSE não estiver disponível,
use `--appimage-extract-and-run`. Usuários de launchers anteriores à rc.3
precisam baixar esta versão manualmente uma vez.
