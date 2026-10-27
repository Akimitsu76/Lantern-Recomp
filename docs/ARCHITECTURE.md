# Arquitetura

Aster Native usa Python >=3.11 para o núcleo e Tkinter/Tk 8.6 para um launcher
Linux local. Tk já está presente: nenhuma dependência gráfica pesada foi adicionada.
Isso é uma escolha para o protótipo de preparação, independente da futura stack
C++ do jogo. Nenhuma parte do jogo foi traduzida para Python.

`native_port/sources.py` reconhece cabeçalhos XEX2 e volumes XDVDFS sem escrever
nas entradas. Pastas extraídas são inventariadas com limites e detecção de XEX
principal (default.xex na raiz, ou um único candidato). `settings.py` valida e
persiste caminhos, última entrada e opções de build em JSON local. `workspace.py` limita saídas ao workspace dentro do projeto, resolve
symlinks e cria JSONs por substituição atômica. `tasks.py` gere subprocessos sem
shell, timeout e cancelamento por grupo de processos.

`modules.py` define a API v1; `games/green_lantern.py` contém o ID e os bloqueios
específicos do jogo. `pipeline.py` encadeia inspeção, identidade, hash, dependências
e relatórios. Dados de arquivos não são carregados como plugins ou comandos.

`launcher.py` usa uma thread de trabalho e uma fila consumida pelo event loop Tk.
Os botões executam operações concretas. Nenhum worker acessa widgets; iniciar fica
desabilitado porque não existe backend nativo validado.

`diagnostics.py` consulta somente ferramentas enumeradas internamente.
`artifacts.py` valida ELF do utilitário hospedeiro, sem aprovar um jogo. O script
host_probe compila código original do projeto com argumentos internos explícitos.
Os módulos e arquivos de entrada não fornecem comandos ao executor.

Resultados, cache e utilitário compilado ficam em `.aster/`, fora dos fontes e
ignorados pelo Git. O cache atual armazena relatórios por fingerprint, sem reutilizar
objetos C++ ou alegar compilação incremental do jogo.

A GUI exporta logs/diagnósticos em JSON no workspace, exibe durações por tarefa e
usa animação indeterminada apenas durante operações reais. Não inventa percentuais.
As preferências de build são registradas para uso futuro e participam da chave de
cache; o backend do jogo ainda não existe.

A integração local Xenon está em integrations/xenonrecomp e native_port/xenon.py.
Ela exporta a imagem antes da alteração de thunks, valida/normaliza PE e resolve
imports, sem fornecer runtime. Parâmetros do probe específico pertencem ao módulo
GreenLantern; o harness original está em games/green_lantern_probe.cpp. Resultados
associados por hash são exibidos pela preparação e nunca habilitam lançamento.
