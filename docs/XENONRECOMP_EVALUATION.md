# XenonRecomp e dump XEX real — 22/10/2026

**Atualização posterior à autorização:** decodificação, análise Ghidra e recompilação
de uma função real concluídas. Veja [NATIVE_PROGRESS.md](NATIVE_PROGRESS.md) para
resultados atuais e limitações. A avaliação inicial abaixo permanece histórica.


## Resultado da inspeção local

Fonte selecionada pelo usuário:
`/caminho/do/jogo/Green_Lantern`.

| Campo | Observado no cabeçalho / inventário |
|---|---|
| Arquivos | 135, sendo 1 XEX e 134 outros arquivos |
| Total | 3.602.346.061 bytes; completude dos assets não certificada |
| Executável | default.xex, 9.023.488 bytes |
| SHA-256 | 3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1 |
| Title ID | 575207E9, corresponde ao módulo Green Lantern |
| Media ID | 2F347A2A |
| Versão bruta | 00000004; não é identificação por hash de revisão conhecida |
| Image base | 0x82000000, valor declarado, não endereço verificado em disassembly |
| Entry point | 0x822FC750, valor declarado, não função analisada |
| Payload offset | 0x3000 |
| Criptografia | 1 (normal) |
| Compressão | 1 (basic), 4 blocos declarados |
| Bytes armazenados / expandidos | 9.011.200 / 14.680.064, segundo tabela de blocos |
| Imports | xam.xex: 120 registros; xboxkrnl.exe: 331 registros |

Os números de registros de imports não são contagens de APIs únicas. Resolver
ordinais exige ler as entradas no código/payload; isso não foi feito.

Bibliotecas estáticas declaradas incluem D3D9, D3DX9, XAUDIO2, XAPILIB, XNET e
bibliotecas do compilador. São metadados, não prova de quais funções são usadas,
de uma engine específica ou de compatibilidade com runtime hospedeiro.

O primeiro ensaio revelou um erro do nosso parser: tipo opcional 1 foi tratado
como offset no arquivo, embora contenha DWORD inline. A correção foi verificada
com [GetOptHeader do Xenia](https://github.com/xenia-project/xenia/blob/master/src/xenia/cpu/xex_module.cc)
e com o XEX real. Adicionados testes sintéticos de regressão, imports e compressão.
Nenhum byte proprietário foi incorporado a fixtures.

Relatório completo local, ignorado pelo Git:
`.aster/reports/green-lantern-xex.json`. O hash do original foi conferido novamente
depois da preparação e permaneceu igual. A última pasta foi salva no launcher.

## REA/Ghidra

O REA rejeitou `open_binary(path=default.xex, provider_id=ghidra)` com
`target_unavailable`, `unsupported binary format`, constraint `file_format_rejected`.
Nenhuma importação nem autoanálise do jogo foi concluída. A primeira chamada com
snapshot_path também falhou porque esse parâmetro tentou ler uma evidência
inexistente; a segunda chamada sem snapshot é a observação relevante do formato.
Não tentar interpretar bytes criptografados como PowerPC raw.

## Revisão real do XenonRecomp

Código obtido somente para inspeção em `.aster/tools/XenonRecomp`.
Commit: **ddd128bcca99fe8bfbb99bea583c972351fa6ace** (log local: 2025-08-04).
Clone sem submódulos recursivos; nenhum script, CMake ou binário externo executado.
A falha inicial de DNS do sandbox foi resolvida pelo clone autorizado fora dele.
Licença principal MIT, confirmada no LICENSE.md local.

Arquivos consultados: CMakeLists.txt, thirdparty/CMakeLists.txt, .gitmodules,
XenonUtils/{image.cpp,xex.cpp,xex.h,CMakeLists.txt}, XenonAnalyse/main.cpp,
XenonRecomp/{main.cpp,recompiler.cpp,recompiler_config.cpp,CMakeLists.txt}.

- [Xex2LoadImage](https://github.com/hedge-dev/XenonRecomp/blob/ddd128bcca99fe8bfbb99bea583c972351fa6ace/XenonUtils/xex.cpp)
  tem tratamento explícito de criptografia normal e compressão basic. Isso confirma
  um caminho no código para esse formato, não um teste de sucesso com nosso dump.
- [CLI](https://github.com/hedge-dev/XenonRecomp/blob/ddd128bcca99fe8bfbb99bea583c972351fa6ace/XenonRecomp/main.cpp)
  recebe configuração TOML e cabeçalho de contexto PPC; configurações do jogo,
  chamadas indiretas e helpers ainda precisam ser identificados. Não gerar
  endereços fictícios ou usar configuração de outro jogo.
- [README](https://github.com/hedge-dev/XenonRecomp/blob/ddd128bcca99fe8bfbb99bea583c972351fa6ace/README.md)
  esclarece que o projeto não fornece runtime. CPU traduzida não implementa GPU,
  áudio, input, arquivos, memória ou serviços Xbox por si só.
- CMake mínimo 3.20 e C++17. CMake continua ausente do PATH. Os seis submódulos
  não foram baixados/compilados, nem tiveram suas licenças transitivas auditadas.

Revisões referenciadas pelo superprojeto:

| Submódulo | Commit |
|---|---|
| fmt | 873670ba3f9e7bc77ec2c1c94b04f1f8bef77e9f |
| libmspack | 305907723a4e7ab2018e58040059ffb5e77db837 |
| simde | a532a12ca9bbdc5e6547eb602e6256b71a5377d4 |
| tiny-AES-c | 23856752fbd139da0b8ca6e471a13d5bcc99a08d |
| tomlplusplus | c4369ae1d8955cae20c4ab40b9813ef4b60e48be |
| xxHash | 2bf8313b934633b2a5b7e8fd239645b85e10c852 |

## Próximo experimento delimitado

1. Resolver a autorização para carregar/decodificar o XEX criptografado. O prompt
   original manda documentar o bloqueio quando houver descriptografia e não
   contornar controles automaticamente. Criptografia no formato não foi
   classificada como DRM; a restrição foi preservada por prudência com a instrução.
2. Disponibilizar CMake em ambiente local isolado, sem alterar pacotes/configurações
   do sistema; revisar submódulos e fixar seus commits antes de executar o build.
3. Compilar e testar primeiro as ferramentas com fixtures originais e somente
   depois carregar uma cópia isolada do XEX. Registrar retornos, logs e hashes.
4. Se o carregamento produzir uma imagem PE coerente, validar arquitetura e entrada
   e tentar análise no Ghidra/REA; depois identificar funções/helpers/indireções.
5. Gerar C++ para um experimento controlado, verificar semântica e só então evoluir
   um runtime. Não habilitar o jogo apenas porque o gerador terminou.

Estado: **XEX identificado; metadados analisados; código criptografado não
carregado; recompilador não compilado; jogo não recompilado ou executado.**
