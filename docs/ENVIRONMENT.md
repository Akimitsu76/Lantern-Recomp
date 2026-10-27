# Reconhecimento — 2026-10-22

CachyOS x86_64. Repositório Git sem commits e sem arquivos de aplicação prévios.
Shell efetivo desta sessão: Bash (o prompt menciona Fish).

| Ferramenta | Observação local |
|---|---|
| Ghidra | 12.1.4; REA provider disponível, ainda sem alvo importado |
| Java/Javac | 21.0.12.1 |
| GCC | 16.2.1 |
| Clang | 23.1.1 |
| CMake | ausente do PATH |
| Ninja | 1.13.2 |
| Python | 3.14.8 |
| Node | 24.22.0 |
| Tkinter | Tk 8.6 importável; display :1 inacessível ao processo |
| Xvfb | /usr/bin/Xvfb |
| XenonRecomp / rexglue | ausentes do PATH |

REA MCP respondeu a binary_session({}); Ghidra passou nas verificações de
instalação, arquitetura, Java e decompilador. Isso não demonstra importação
de XEX nem compatibilidade de um jogo. Hopper, IDA e Kuna indisponíveis.

Busca limitada a Documentos, Downloads e Games, até quatro níveis.
Encontrado: `/caminho/do/jogo/Green Lantern.iso`, 7.838.695.424 bytes.
Nenhum XEX encontrado nessa busca. Fontes abertas somente para leitura.
Nenhum pacote instalado e nenhuma configuração do sistema alterada.

## Ferramentas locais adicionadas depois da autorização

CMake 3.31.10 extraído para .aster/tools/cmake-runtime, sem instalação global.
XenonRecomp/XenonAnalyse e adaptadores compilados com Clang 23.1.1/Ninja.
Ghidra headless executou análise com settings/cache/temp redirecionados ao projeto.
O diagnóstico do launcher consulta também os caminhos de ferramentas locais.
Nenhuma alteração de pacotes, PATH global, instalação Ghidra ou configuração MCP.
