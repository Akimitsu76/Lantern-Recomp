from native_port.errors import PortError


class GreenLantern:
    api_version = 1
    id = 'green-lantern'
    version = '0.1.0'
    title_id = '575207E9'  # Xenia game-compatibility issue #1803; not a dump hash.
    native_probe = {
        'source_sha256': '3218a70a78f2d258cd236c204ddbca0cee21c197d6de463f68f6e504385852d1',
        'address': '0x823968F8', 'size': 8,
        'harness': 'games/green_lantern_probe.cpp',
    }


    def identify(self, source):
        title = source.get('title_id')
        if title and title != self.title_id:
            raise PortError('WRONG_GAME', 'Title ID pertence a outro jogo.', title_id=title)
        return {'confirmed': title == self.title_id,
                'basis': 'execution-info-title-id' if title else 'unidentified',
                'known_revision': False}

    def dependencies(self):
        return ('clang', 'cmake', 'ninja', 'git')

    def plan(self, source):
        return [
            {'task': 'inspect', 'supported': True},
            {'task': 'fingerprint', 'supported': True},
            {'task': 'prepare-report', 'supported': True},
            {'task': 'extract-assets', 'supported': False,
             'reason': 'Extrator XDVDFS ainda não implementado.'},
            {'task': 'analyze-code', 'supported': False,
             'reason': 'Análise é uma ação separada via scripts/analyze_xex.py; prepare não a executa.'},
            {'task': 'generate-and-build', 'supported': False,
             'reason': 'Backend de recompilação/runtime do jogo não integrado.'}]

    def build(self, context):
        raise PortError('NO_NATIVE_BACKEND', 'Port nativo ainda não implementado. Nenhum jogo compilado.')

    def verify(self, artifact):
        raise PortError('NO_NATIVE_BACKEND', 'Não existe artefato do jogo verificável.')

    def launch(self, artifact):
        raise PortError('NOT_READY', 'Não há executável nativo validado para iniciar.')
