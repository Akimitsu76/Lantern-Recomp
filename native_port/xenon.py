"""Local XenonRecomp analysis adapter. Does not supply a game runtime."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
from .errors import PortError
from .pe import normalize_memory_pe
from .sources import inspect_source, digest_source
from .tasks import Cancellation, run_process

XENON_COMMIT = 'ddd128bcca99fe8bfbb99bea583c972351fa6ace'


def resolve_imports(xex_bytes, memory, info, xenon_root):
    header = next((h for h in info['optional_headers'] if h['key']=='0x000103FF'), None)
    if not header:
        return []
    offset, length = header['offset'], header['size']
    blob = xex_bytes[offset:offset+length]
    _, strings_size, count = struct.unpack_from('>III', blob)
    names, pos = [], 12
    for _ in range(count):
        end = blob.index(b'\0', pos, 12+strings_size)
        names.append(blob[pos:end].decode('ascii'))
        pos = 12+((end+1-12+3)//4)*4
    maps = {}
    for library, table in [('xam.xex','xam_table.inc'),('xboxkrnl.exe','xboxkrnl_table.inc')]:
        text = (xenon_root/'XenonUtils/xbox'/table).read_text(encoding='utf8')
        maps[library] = {int(ordinal,16): {'name': name, 'export_kind': kind} for ordinal,name,kind in
                        re.findall(r'XE_EXPORT\(\w+,\s*(0x[\da-fA-F]+),\s*(\w+),\s*(\w+)\)', text)}
    pos, result = 12+strings_size, []
    while pos < len(blob):
        size = struct.unpack_from('>I',blob,pos)[0]
        name_index, records = struct.unpack_from('>HH',blob,pos+36)
        library = names[name_index&255]
        for i in range(records):
            address = struct.unpack_from('>I',blob,pos+40+i*4)[0]
            rva = address-int(info['image_base'],16)
            if rva < 0 or rva+4 > len(memory):
                raise PortError('BAD_IMPORT', 'Registro de import fora da imagem.', address=address)
            descriptor = struct.unpack_from('>I',memory,rva)[0]
            ordinal, kind = descriptor&65535, descriptor>>24
            result.append({'library':library, 'ordinal':ordinal, 'descriptor_type':kind,
                           'address':f'0x{address:08X}', **maps.get(library,{}).get(ordinal,{'name':None})})
        pos += size
    return result


def analyze(source, workspace, allow_decode=False, probe=False, cancel=None, emit=None, game=None):
    cancel = cancel or Cancellation()
    emit = emit or (lambda _: None)
    project = workspace.project
    logs = []
    def command(task, argv, timeout=120):
        cancel.check()
        emit({'task':task,'state':'running'})
        r = run_process(list(map(str,argv)), project, cancel, timeout)
        logs.append(dict(task=task,**r))
        emit({'task':task,'state':'completed','seconds':r['seconds']})
        return r
    report = {'schema':1, 'game_ready':False, 'game_executed':False, 'logs':logs}
    try:
        info = inspect_source(source,cancel)
        sha = digest_source(info['path'],cancel)
        if info['format'] != 'xex2':
            raise PortError('NOT_XEX','Análise Xenon requer XEX.')
        if info.get('encryption') and not allow_decode:
            raise PortError('DECODE_AUTH_REQUIRED','Autorize explicitamente a decodificação local do XEX.')
        tool_root = workspace.path('tools/XenonRecomp')
        commit = command('Verificar revisão', ['git','-C',tool_root,'rev-parse','HEAD'])['stdout'].strip()
        if commit != XENON_COMMIT:
            raise PortError('TOOL_REVISION','Revisão Xenon não revisada.',commit=commit)
        build = workspace.path('build/xenon')
        decoder = build/'aster-xex-inspect'
        if not decoder.is_file():
            raise PortError('MISSING_DECODER','Compile integrations/xenonrecomp antes de analisar.')
        out = workspace.path('analysis/green-lantern')
        original = Path(info['path'])
        if original.is_relative_to(out) or (info.get('game_directory') and out.is_relative_to(Path(info['game_directory']))):
            raise PortError('SOURCE_OVERLAP','Fonte deve ficar fora da pasta de artefatos.')
        out.mkdir(parents=True,exist_ok=True)
        snapshot = workspace.path('analysis/green-lantern/source.xex')
        shutil.copyfile(original,snapshot)
        if digest_source(snapshot,cancel)!=sha:
            raise PortError('SOURCE_CHANGED','Hash da cópia divergente.')
        memory_file = workspace.path('analysis/green-lantern/decoded.pe')
        normalized_file = workspace.path('analysis/green-lantern/normalized.pe')
        decoded = command('Decodificar XEX',[decoder,snapshot,memory_file])
        decode_result = json.loads(decoded['stdout'])
        memory = memory_file.read_bytes()
        normalized, pe = normalize_memory_pe(memory)
        if pe['image_base'] != int(info['image_base'],16) or pe['entry_point'] != int(info['entry_point'],16):
            raise PortError('PE_IDENTITY','PE não corresponde aos endereços declarados no XEX.')
        normalized_file.write_bytes(normalized)
        imports = resolve_imports(snapshot.read_bytes(), memory, info, tool_root)
        workspace.write_json('analysis/green-lantern/imports.json',imports)
        report.update(state='decoded-and-validated', source_sha256=sha, source_path=str(original),
                      xenon_commit=commit, decoder_sha256=hashlib.sha256(decoder.read_bytes()).hexdigest(),
                      user_decode_authorization=allow_decode, decoded=decode_result, pe=pe,
                      normalized_path=str(normalized_file),
                      normalized_sha256=hashlib.sha256(normalized).hexdigest(),
                      imports={'records':len(imports),'unique_apis':len({(r['library'],r['ordinal']) for r in imports}),
                               'unresolved_records':sum(r['name'] is None for r in imports)},
                      blockers=['NO_NATIVE_RUNTIME','NO_FULL_GAME_BACKEND'])
        if probe:
            spec = getattr(game,'native_probe',None)
            if not spec or sha != spec['source_sha256']:
                raise PortError('UNKNOWN_PROBE_REVISION','O probe foi verificado apenas para o hash analisado.')
            analysis_file = out/'ghidra-analysis.json'
            if not analysis_file.is_file():
                raise PortError('NEEDS_ANALYSIS','Execute o Ghidra antes do experimento de função.')
            ghidra = json.loads(analysis_file.read_text(encoding='utf8'))
            fn = next((f for f in ghidra['functions'] if f['address'].lower()==spec['address'][2:].lower()), None)
            if ghidra['language']!='PowerPC:BE:64:A2ALT-32addr' or not fn or fn['body_bytes']!=spec['size']:
                raise PortError('PROBE_BOUNDARY','Fronteira da função não confirmada pelo Ghidra.')
            generated = workspace.path('analysis/green-lantern/leaf-generated')
            command('Recompilar função delimitada',[build/'aster-recompile-leaf', snapshot,spec['address'],
                                                    generated,tool_root/'XenonUtils/ppc_context.h'])
            executable = workspace.path('analysis/green-lantern/leaf-native-probe')
            command('Compilar função x86_64',['clang++','-std=c++17','-O2','-msse4.1',
                    '-I'+str(generated),'-I'+str(tool_root/'thirdparty/simde'),
                    generated/'ppc_recomp.0.cpp',project/spec['harness'],
                    '-o',executable])
            r = command('Verificar semântica nativa',[executable])
            proof = json.loads(r['stdout'])
            if proof.get('native_cases_passed')!=10000 or proof.get('game_ready') is not False:
                raise PortError('PROBE_FAILED','Resultado do experimento não confirmado.')
            report['native_leaf_probe'] = dict(proof, executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest())
        if digest_source(original,cancel)!=sha:
            raise PortError('SOURCE_CHANGED','O original mudou durante a análise.')
        report['source_unchanged'] = True
        workspace.write_json('reports/xenon-analysis.json',report)
        return report
    except PortError as e:
        report.update(state='failed', error=e.as_dict())
        workspace.write_json('reports/xenon-analysis.json',report)
        raise
