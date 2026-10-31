# Atualização integrada do launcher

A aba **Atualizações**, ao lado de **Diagnóstico**, consulta os releases do
repositório público [Lantern-Recomp](https://github.com/Akimitsu76/Lantern-Recomp).
A identidade GitHub é fixada pelo ID 1431033413, preservado após a mudança do
nome Green-Lantern-Recomp. A consulta usa a API pública, sem token do usuário.
É feita ao abrir a interface, a cada 30 minutos enquanto ela estiver aberta e
pelo botão **Verificar agora**; ocorre em uma thread sem bloquear a janela.

Somente versões numericamente posteriores à instalada são oferecidas. Releases
em rascunho ou sem o executável da plataforma e `SHA256SUMS` são ignorados.
A opção de incluir pré-releases começa habilitada porque o port está em testes.
Ao desabilitá-la, tags alpha/beta/rc também são excluídas, mesmo se o GitHub as
marcar como release comum. A opção vale para a consulta atual.

**Baixar e instalar** baixa somente o AppImage Linux ou EXE Windows, verifica
tamanho, formato e SHA-256 antes de mudar o executável atual. Se o GitHub também
publicar um digest do asset, ele deve concordar com o arquivo SHA256SUMS.
Conexões e redirecionamentos aceitam somente HTTPS nos hosts do GitHub previstos.
A [API de releases](https://docs.github.com/en/rest/releases/releases) fornece
os assets publicados; nenhum corpo de release é executado como script.

O botão deve ser usado fora de uma sessão do jogo ou de outra tarefa do launcher.
É possível cancelar o download. A instalação salva preferências, espera o
launcher fechar e substitui seu arquivo de forma atômica. Um helper copiado do
launcher atual faz isso também no Windows, onde o EXE em execução está bloqueado.
O launcher novo é aberto automaticamente; ele deve confirmar versão e nonce de
inicialização. Se não iniciar a interface, o helper restaura e reabre a versão
anterior. A cópia de rollback existe apenas durante a instalação, dentro da pasta
temporária de download: depois do sucesso, ela e o pacote baixado são apagados,
de modo que reste **um único launcher**. Cópias `*.previous-<hash>` deixadas ao
lado do executável por versões anteriores são removidas quando o hash confere.
Não são alterados dump, saves, caches ou configurações gráficas.

O EXE/AppImage deve estar em uma pasta gravável. O recurso não substitui arquivos
de um checkout Python nem atualiza automaticamente o backend do jogo. Uma nova
receita de backend continua seguindo o fluxo já existente de preparação local.
Falhas e o caminho do backup ficam em `updates/last-result.json` na pasta de dados
do launcher. O estado da última instalação aparece na aba Atualizações.

**Primeira instalação:** os launchers antigos não têm esta função. É necessário
baixar e abrir uma vez o novo EXE/AppImage com o atualizador. A partir dele, os
próximos releases compatíveis podem ser instalados pela própria interface.
Ao publicar, a versão de `native_port.__version__` deve corresponder à tag; o
health check recusa um pacote com versão diferente da anunciada.

A reinicialização dos executáveis PyInstaller usa a variável pública
[`PYINSTALLER_RESET_ENVIRONMENT`](https://pyinstaller.org/en/stable/advanced-topics.html#envvar-PYINSTALLER_RESET_ENVIRONMENT)
para que o novo processo extraia e use o próprio runtime, mesmo após o antigo sair.
A interface e o fluxo de substituição são verificados em Linux e em Windows sob
Wine; isso não certifica gameplay ou compatibilidade completa no Windows nativo.
