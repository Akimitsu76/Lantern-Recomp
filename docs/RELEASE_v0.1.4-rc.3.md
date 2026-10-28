# v0.1.4-rc.3 — Novo launcher e atualização integrada

Esta pré-release melhora o launcher Linux e Windows. A página inicial recebeu
novo visual, ajustes rápidos e ações de Salvar/Jogar acessíveis nas outras abas.
A preparação do port mostra o avanço geral e o progresso de cada etapa. As fontes
acompanham os executáveis; o AppImage usa um runtime Tk com fontes escaláveis.

A nova aba **Atualizações**, ao lado de **Diagnóstico**, avisa quando há uma
versão publicada mais recente. Ela permite consultar as notas, baixar o pacote
correto para o sistema, acompanhar o download e instalar diretamente. O launcher
confere tamanho, formato x64 e SHA-256, guarda a versão anterior e reinicia.
Se a interface nova não iniciar, restaura e reabre a versão anterior.

O download pode ser cancelado. A instalação fica indisponível durante uma sessão
ou preparação do jogo. Saves, preferências, dump e caches são preservados.
A consulta inclui pré-releases por padrão, com opção para desabilitá-las.

**Para começar a usar o atualizador, baixe e abra uma vez o novo EXE/AppImage.**
Launchers antigos não possuem essa função. Após esta instalação, os próximos
releases compatíveis poderão ser instalados pela própria aba Atualizações.

Downloads:
- `AsterNative-linux-x86_64.AppImage`
- `AsterNative-windows-x64.exe`
- `SHA256SUMS`
- `LEIA-ME-ATUALIZACAO.md`

Não há arquivos do jogo nestes pacotes; é necessário seu próprio dump compatível.
No Linux, marque o AppImage como executável; se FUSE não estiver disponível,
use `--appimage-extract-and-run`.

Validação: interface e transações com arquivos de teste em Linux e Windows via
Wine, incluindo reinicialização e recuperação, além de testes automatizados.
Isso não certifica Windows nativo nem a campanha completa. O port continua
experimental; 60 FPS e ilimitado permanecem experimentais. O bloqueio relatado
no tutorial do Disparo do Anel continua pendente. Esta atualização não declara
esse problema corrigido.
