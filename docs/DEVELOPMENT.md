# Desenvolvimento e validação

**Atualização:** as ferramentas Xenon e CMake locais estão compiladas. Consulte
NATIVE_PROGRESS.md, BUILD_PIPELINE.md e VALIDATION.md para o estágio atual.
Os testes PE/adapter em test_pe_xenon.py usam fixtures originais; testes opcionais
que exigem ferramentas geradas são skipped em checkout sem build. A suíte atual
tem **152 testes aprovados**, incluindo GUI, presets/CVars, schema 2, os três
alvos e o probe nativo.


O projeto roda diretamente com Python, sem instalar pacotes ou alterar o sistema.
Requisitos locais e versões: ENVIRONMENT.md. Não existe dependência Python externa
para o núcleo; a GUI requer o módulo tkinter fornecido pelo ambiente.

Comandos na raiz:

```sh
python3 scripts/host_probe.py
python3 -m unittest discover -s tests -v
xvfb-run -a -s '-screen 0 1440x900x24' python3 -m unittest discover -s tests -v
python3 -m native_port doctor
python3 -m native_port gui
```

Fixtures em tests/fixtures.py são bytes sintéticos, sem código do jogo. Testam
metadados big-endian, opcionais XEX por ponteiro/imediatos, volume XDVDFS, arquivo
incompleto, permissões e identidade. Testes cobrem escape por caminho/symlink,
confirmação e escopo da limpeza, mudanças da chave de cache, erro propagado e
registrado, cancelamento de hash/tarefa/processo, timeout, dependências ausentes,
artefato ELF/hash real e UI com arquivos inválidos e dependências ausentes.

A validação de ELF real requer executar host_probe primeiro; caso contrário esse
teste é marcado como skipped. GUI sem display acessível também é skipped, não
aprovada. Com Xvfb foi possível executar os testes da interface. Na primeira
tentativa, o sandbox impediu o display virtual; a execução autorizada fora do
sandbox passou. Nenhuma configuração permanente foi alterada.

CMake e o host experimental foram compilados localmente em `.aster/`. O formato
da ISO antiga não foi reconhecido; o trabalho atual usa a pasta extraída com
`default.xex` e os assets fornecidos pelo usuário. Consulte BUILD_PIPELINE.md e
VALIDATION.md para os comandos e limites.

Para resultados e comandos efetivamente executados, veja VALIDATION.md.

Testes adicionais cobrem seleção da pasta pela GUI, persistência isolada de
preferências, exportação limitada ao workspace, ambiguidade de múltiplos XEX,
manifesto de assets, XEX em subpasta, layout mínimo 1088×696, presets/CVars,
migração do schema 1 para o 2 e os alvos 30/60/ilimitado. Pillow é opcional e
usado somente para capturar a janela do teste, nunca imagens do jogo. O snapshot
é ignorado se o display virtual for menor que a janela; use
`xvfb-run -a -s '-screen 0 1440x900x24'` para capturá-lo.
