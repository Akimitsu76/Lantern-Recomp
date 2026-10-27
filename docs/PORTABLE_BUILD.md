# Gerar o port no seu PC

O pacote contém o launcher, Python/Tk e as ferramentas portáteis CMake/Ninja.
Não contém o jogo, saves, shaders extraídos, código recompilado ou executável
do jogo. O port é gerado **localmente a partir do seu dump**.

## Compatibilidade

- Linux x86-64 com glibc >=2.34, driver Vulkan e fragment shader interlock, CPU x86-64-v2.
  O launcher usa Python portátil; o SDK oficial tem requisitos adicionais de
  C++23/libstdc++. Outras distribuições e GPUs ainda precisam de validação.
- Windows 10/11 x64: o launcher é um `.exe` com Python/Tk embutidos. O gerador
  usa o SDK Windows e D3D12/ROV. A interface foi testada via Wine; a compilação
  e execução **do jogo no Windows real ainda não foram validadas**.
- A geração exige Clang >=18 e biblioteca padrão C++23. O código atual do
  launcher oferece preparação automática dos requisitos ausentes ao confirmar
  **Gerar port**. Windows usa WinGet e os instaladores oficiais de Build Tools,
  SDK/Clang e runtime C++; Linux usa pacotes da distribuição e autorização
  gráfica PolicyKit. A preparação pode exigir administrador e vários GB.
  WinGet/PolicyKit ausentes e distribuições sem plano conhecido produzem erro
  explicativo. Drivers de GPU não são instalados por esse procedimento.
  Os planos e a detecção têm testes automatizados; instalações em máquinas
  limpas Windows/Linux ainda precisam de validação. A pré-release v0.1.3 inclui
  essa função nos launchers; pacotes anteriores não a recebem sem uma nova
  distribuição.
- O único XEX validado atualmente tem SHA-256
  `3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1`.
  Outra revisão é rejeitada antes de baixar ferramentas ou gerar código.

## Primeiro uso

### Arquivo único (recomendado)

Baixe `AsterNative-windows-x64.exe` ou `AsterNative-linux-x86_64.AppImage`.
O `.exe` abre diretamente. No Linux, dê permissão de execução ao AppImage e
abra-o. Não é necessário extrair um ZIP nem manter pastas ao lado do arquivo.
O AppImage usa FUSE; se o sistema não o oferecer, execute
`./AsterNative-linux-x86_64.AppImage --appimage-extract-and-run`.

Os recursos públicos são instalados automaticamente na pasta de dados do usuário:
`%LOCALAPPDATA%/AsterNative/app` no Windows e
`${XDG_DATA_HOME:-~/.local/share}/aster-native/app` no Linux.
Builds, downloads, preferências e saves ficam em `.aster` dentro dessa pasta,
preservados entre aberturas e atualizações. Mover o arquivo baixado não apaga os
dados. O primeiro uso e a geração precisam de espaço livre nessa pasta.
Os requisitos de Clang/C++23 e do dump continuam os mesmos.

### Pacotes em pasta (formato anterior)

1. Extraia **toda** a pasta `AsterNative` do ZIP (Windows) ou TAR.GZ (Linux)
   em um local gravável. Mantenha `app` e `_internal` ao lado do executável.
2. Abra `AsterNative.exe` no Windows ou `AsterNative` no Linux. Não é necessário
   instalar Python nem rodar pip para usar o launcher.
3. Selecione a pasta extraída que contém `default.xex` e os demais arquivos do
   jogo. ISO e XEX isolado não são suficientes para esta geração.
4. Clique **GERAR PORT NATIVO**, ou abra a página **Gerar port**.
5. Confirme a preparação das dependências e o download das fontes públicas do
   SDK ReXGlue nas revisões fixadas. A primeira geração compila o SDK gráfico
   completo nos dois sistemas. Fontes/builds ficam na pasta do usuário;
   compilador e bibliotecas ausentes podem ser instalados no sistema pelo seu
   gerenciador oficial, com autorização administrativa. Artefatos verificados
   são reutilizados; jogar um port já gerado não reinstala a toolchain.
6. Acompanhe **Gerar port**. As seis etapas mostram downloads em bytes, compilação
   em alvos Ninja e atividade indeterminada quando não existe um total conhecido.
   O launcher verifica o dump, gera C++ pelo ReXGlue,
   configura CMake e compila. Não feche o launcher durante a geração; para
   interromper use **Cancelar tarefa**. Logs ficam em `app/.aster/native/`.
7. Após **Port gerado**, clique **JOGAR AGORA**. Compilação concluída não é
   certificação de gameplay: inicialização, áudio e campanha devem ser testados.

O dump é lido sem alterações. Todos os alvos de FPS e configurações gráficas
compartilham saves e cache em `.aster/runtime/green-lantern/` na pasta de dados
do usuário do sistema. O perfil de 30 FPS já existente continua como principal.
Pastas antigas de 60 FPS/ilimitado são preservadas, sem sobrescrever progresso.

## Compilação incremental

O build é identificado pelo hash do XEX, versão do SDK, plataforma, hints e hook.
Ao repetir **Gerar port**, os hashes dos artefatos são conferidos. Um build
íntegro é reutilizado sem rodar codegen ou compilador. Builds incompletos mantêm
seus objetos para o Ninja continuar. Novas receitas usam outra pasta; builds
anteriores e seus logs são preservados. O registro fica em
`app/.aster/config/native-install.json`.

O perfil de compilação usa `RelWithDebInfo` para corresponder ao SDK/runtime.
O controle legado de tipo de build da inspeção não altera esse contrato de ABI.
No Linux o plugin Vulkan com cache de driver é compilado contra o SDK fixado;
não é substituído pelo plugin original no staging final.

## Gráficos e FPS

30 FPS continua padrão. 60 e ilimitado são experimentais e pedem confirmação.
Ilimitado remove a espera da engine; não é renderização independente de uma
simulação fixada em 60 atualizações/s. Gameplay, física e áudio desse modo não
estão certificados.

No Linux, desligar VSync seleciona apresentação imediata e preserva o relógio
guest de 60 Hz. Assim os limites de 30/60 continuam funcionando. No Windows,
o caminho usa o presenter D3D12; comportamento visual ainda precisa de teste
nativo. O MSAA é controlado pelo jogo/backend: o launcher não anuncia um falso
botão para desligá-lo. “Cache de texturas” altera orçamento de memória, não a
resolução dos arquivos de textura.

A opção **Resolução da janela** inclui **1920x1080 (Full HD)** e controla a saída.
Com SDK atualizado pelo patch 0024, Baixa/Média usam 720p interno, Alta 1440p e
Ultra 4K. **Personalizada** permite escolher escala interna, saída, texturas,
filtragem, antisserrilhado e FPS separadamente. Por exemplo: saída1080p com
texturas Ultra e escala1×. Ainda não existe escala interna exata de1080p (1,5×).
O patch corrigiu a cópia de profundidade nas primeiras cenas testadas em2×/3×;
desempenho e campanha nessas escalas permanecem em validação. As fontes dos
dois sistemas recebem a correção; GPU Windows nativa ainda não foi validada.

FSR1 espacial e FXAA são opções do SDK compartilhado. Filtrar a imagem de saída
não acrescenta detalhes aos arquivos originais. As texturas HD usam recursos
preparados localmente do próprio dump; seu custo é independente da resolução.

Após atualizar o AppImage, use **Atualizar port** para gerar o backend novo.
Saves e o cache do usuário são preservados; o build anterior permanece em outra
pasta. A biblioteca de apresentação é compilada localmente contra o SDK Linux
0.10.0 fixado e carregada somente no processo do jogo.

**Pré-compilar shaders conhecidos antes de jogar** fica ligada por padrão e
pode ser desmarcada. Desmarcar preserva o cache; não impede a preparação sob
demanda. O cache comum aos FPS guarda microcódigo, receitas de pipeline e, no
Vulkan, dados do driver. Novos pipelines são preparados por workers no modo
`async`, mas tradução/análise de shaders inéditos ainda pode bloquear e causar
engasgos. Mudanças de driver, resolução ou versão podem exigir novas variantes.
Não existe promessa de compilar uma única vez todas as cenas futuras.
O backend Linux evita compilar um pipeline provisório na thread de
desenho; os pipelines definitivos são preparados por workers. Shaders com
efeitos sobre a memória guest preservam o caminho síncrono. Quadros incompletos
continuam retidos para evitar objetos e sombras desaparecendo. Por isso a
primeira visita a uma cena ainda pode ter pausas; não há garantia de zero
travadas. O cache persistente é comum a todos os alvos de FPS.

## Pelo terminal

```sh
# No código-fonte:
python3 -m native_port build /caminho/Green_Lantern --download-sdk --install-dependencies --jobs 2
python3 scripts/play_green_lantern.py /caminho/Green_Lantern --validar

# No pacote Linux:
./AsterNative build /caminho/Green_Lantern --download-sdk --jobs 2
./AsterNative gui
```

No Windows, substitua `./AsterNative` por `AsterNative.exe` e informe o caminho
do dump entre aspas. O primeiro build pode demorar e consumir bastante RAM/disco;
comece com uma ou duas tarefas paralelas.

## Empacotar o launcher

Use Python/PyInstaller da plataforma de destino. O script
`scripts/package_launcher.py` aceita `--cmake-data` e `--ninja` para incluir as
ferramentas portáteis e produz os arquivos em `dist/`. O pacote Linux é gerado
com Python standalone e Ninja manylinux, evitando depender da glibc 2.44 desta
máquina de desenvolvimento. Para Windows foi usado Python Windows sob Wine;
isso testa o launcher, não substitui testes do jogo em um PC Windows.

A distribuição usa uma lista explícita de fontes/recursos públicos. `.aster`,
dumps e gamecode gerado nunca entram no pacote. `PACKAGE.json` contém os hashes
dos arquivos distribuídos. Consulte `LICENSES` e `THIRD_PARTY_NOTICES.md`.

FSR 1 (EASU + RCAS) e FXAA são compartilhados entre Linux/Windows. Alta prepara automaticamente 253 materiais revisados usados nas dez missões em 2x;
Ultra em 4x, com o mesmo master Real-ESRGAN em cache. Isso acontece antes da partida;
veja `HD_TEXTURES.md`. Não é um pacote de texturas completo do jogo.
