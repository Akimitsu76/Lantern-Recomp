# v0.1.4-rc.8 — Modo leve após geração/atualização

Esta pré-release experimental publica o launcher `0.1.4-rc.8`. Ela não é stable
e não certifica a campanha completa.

## O que mudou

O launcher passa a aplicar o **modo leve** por padrão depois de gerar ou
atualizar o port e depois de preparar texturas HD manualmente. A limpeza remove
ferramentas de compilação, texturas intermediárias e builds antigos, preservando
o build ativo, o pack HD em uso, saves, preferências, shaders decodificados e
recibos de validação.

A opção **Manter instalação leve** fica em **Diagnóstico** e vem marcada. A
limpeza confere o build ativo por hash, não segue links simbólicos e, em caso de
dúvida ou geração em andamento, não apaga nada. Numa atualização posterior, o
launcher baixa novamente apenas o que faltar e reaplica o modo leve.

Esta entrega é do launcher. Não altera gameplay, renderer, shaders, FPS, saves
ou o backend compilado. As correções do atualizador (launcher único e caminhos
canônicos) já estavam na rc.7 e continuam incluídas.

## Evidência desta revisão

- A suíte completa passou no Linux com **506 testes, 27 skips e 322 subtests**,
  sem falhas.
- O smoke do AppImage Linux informou versão `0.1.4-rc.8`, Tk 9.0, fontes
  escaláveis, arte de fundo pronta, aba de atualizações e `game_launched=false`.
- O smoke do EXE Windows passou sob Wine com perfil `ASTER_DATA_HOME` isolado:
  versão `0.1.4-rc.8`, Tk 8.6, fontes escaláveis, aba de atualizações e
  `game_launched=false`. Windows nativo/D3D12 continua sem certificação.
- Os pacotes não incluem conteúdo do jogo: o payload público foi auditado e
  contém `native_port/retention.py` e os demais arquivos de código/documentação
  permitidos.

## Limites

Windows nativo/D3D12 continua sem validação; o EXE é exercitado sob Wine, que
não certifica GPU ou gameplay nativos. O tutorial do Disparo do Anel continua
pendente, a campanha completa não está certificada e 60 FPS/ilimitado seguem
experimentais. Não há arquivos do jogo nestes pacotes; é necessário seu próprio
dump compatível.

## Downloads

- `AsterNative-linux-x86_64.AppImage` (55.966.200 bytes) — SHA-256
  `c23f6ee20f05024233e5a50bb46fcddc945bd9553d6ddc296b3faba3b85e2870`
- `AsterNative-windows-x64.exe` (69.460.215 bytes) — SHA-256
  `59e0adad8dc656b80a565a96ec42871903b81194e4390fab09a9d7e3f5c0d651`
- `SHA256SUMS`
- `LEIA-ME-ATUALIZACAO.md`

No Linux, marque o AppImage como executável; se FUSE não estiver disponível,
use `--appimage-extract-and-run`. Usuários de launchers anteriores à rc.3
precisam baixar esta versão manualmente uma vez.
