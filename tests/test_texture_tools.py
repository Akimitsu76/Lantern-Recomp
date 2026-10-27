import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_port.errors import PortError
from native_port import texture_tools as tools
from native_port.tasks import Cancellation
from native_port.workspace import Workspace


class TextureToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.work = Workspace(self.root / '.aster', self.root)
        self.recipe = {'revision': 'pinned', 'patches': {}, 'platform': 'linux-x86_64'}
        self.prefix = self.work.path('tools/spatial-sdk/test/install')
        self.source = self.prefix.parent / 'source'
        self.headers = self.source / 'thirdparty/libmspack/libmspack/mspack'
        self.headers.mkdir(parents=True)
        (self.source / '.git').mkdir()
        for name in ('mspack.h', 'lzx.h'):
            (self.headers / name).write_bytes(name.encode())

    def pointer(self, source):
        key = hashlib.sha256(json.dumps(self.recipe, sort_keys=True).encode()).hexdigest()[:20]
        self.work.write_json('tools/spatial-sdk-sources/' + key + '/source-location.json', {'source': str(source)})

    def test_source_can_be_prefix_tree_or_recorded_workspace_tree(self):
        self.assertEqual(tools._source_directory(self.prefix, self.work, self.recipe), self.source)
        other_prefix = self.work.path('tools/spatial-sdk/new/install')
        self.pointer(self.source)
        self.assertEqual(tools._source_directory(other_prefix, self.work, self.recipe), self.source)

    def test_source_pointer_outside_tools_and_header_symlinks_are_rejected(self):
        self.pointer(self.root)
        with self.assertRaises(PortError) as caught:
            tools._source_directory(self.work.path('tools/spatial-sdk/new/install'), self.work, self.recipe)
        self.assertEqual(caught.exception.code, 'TEXTURE_TOOLS_SOURCE')
        (self.headers / 'lzx.h').unlink()
        outside = self.root / 'outside.h'
        outside.write_bytes(b'outside')
        (self.headers / 'lzx.h').symlink_to(outside)
        with self.assertRaises(PortError):
            tools._source_directory(self.prefix, self.work, self.recipe)

    def manifest(self, files=None):
        base = self.work.path('tools/texture-tools/test')
        (base / 'bin').mkdir(parents=True)
        for name in tools.HELPERS.values():
            (base / 'bin' / name).write_bytes(name.encode())
        files = files if files is not None else {p.relative_to(base).as_posix(): tools._digest(p) for p in (base / 'bin').iterdir()}
        (base / 'texture-tools.json').write_text(json.dumps({'recipe': self.recipe, 'files': files}))
        return base

    def test_only_exact_verified_helper_cache_is_reused(self):
        base = self.manifest()
        cached = tools._verified_files(base, self.recipe)
        self.assertEqual(cached['decoder'], base / 'bin/aster_xctd_decode')
        cached['decoder'].write_bytes(b'tampered')
        with self.assertRaises(PortError) as caught:
            tools._verified_files(base, self.recipe)
        self.assertEqual(caught.exception.code, 'TEXTURE_TOOLS_CHANGED')
        self.assertEqual(cached['decoder'].read_bytes(), b'tampered')

    def test_cached_manifest_escape_and_symlink_are_refused(self):
        base = self.manifest()
        manifest = base / 'texture-tools.json'
        data = json.loads(manifest.read_text())
        data['files']['../../outside'] = 'bad'
        manifest.write_text(json.dumps(data))
        with self.assertRaises(PortError):
            tools._verified_files(base, self.recipe)
        data['files'].pop('../../outside')
        manifest.write_text(json.dumps(data))
        decoder = base / 'bin/aster_xctd_decode'
        payload = decoder.read_bytes()
        decoder.unlink()
        (base / 'elsewhere').write_bytes(payload)
        decoder.symlink_to(base / 'elsewhere')
        with self.assertRaises(PortError):
            tools._verified_files(base, self.recipe)

    def test_no_manifest_is_a_cache_miss_but_malformed_manifest_is_preserved(self):
        base = self.work.path('tools/texture-tools/empty')
        self.assertIsNone(tools._verified_files(base, self.recipe))
        base.mkdir(parents=True)
        manifest = base / 'texture-tools.json'
        manifest.write_text('[]')
        with self.assertRaises(PortError):
            tools._verified_files(base, self.recipe)
        self.assertEqual(manifest.read_text(), '[]')

    def test_header_validation_uses_pinned_gitlink_and_exact_blob_hash(self):
        git_hash = 'header-object'
        def run(argv, cwd, cancel, **kwargs):
            command = argv[3:]
            if command == ['rev-parse', 'HEAD']:
                value = self.recipe['revision'] if Path(cwd) == self.source else tools.MSPACK_REVISION
            elif command[0] == 'ls-tree':
                value = f'160000 commit {tools.MSPACK_REVISION}\tthirdparty/libmspack'
            else:
                value = git_hash
            return {'stdout': value, 'stderr': ''}
        with patch.object(tools.shutil, 'which', return_value='/git'), patch.object(tools, 'run_process', side_effect=run):
            headers, hashes = tools._validate_pinned_headers(self.source, self.recipe, Cancellation(), {})
            self.assertEqual(headers, self.headers)
            self.assertEqual(hashes['lzx.h'], tools._digest(self.headers / 'lzx.h'))
        def changed(argv, *args, **kwargs):
            value = run(argv, *args, **kwargs)
            if 'hash-object' in argv:
                value['stdout'] = 'changed-object'
            return value
        with patch.object(tools.shutil, 'which', return_value='/git'), patch.object(tools, 'run_process', side_effect=changed):
            with self.assertRaises(PortError):
                tools._validate_pinned_headers(self.source, self.recipe, Cancellation(), {})

    def test_cancellation_does_not_start_toolchain_or_sdk_build(self):
        cancel = Cancellation()
        cancel.cancel()
        with patch('native_port.native_build.toolchain') as toolchain:
            with self.assertRaises(PortError) as caught:
                tools.ensure_texture_tools(self.root, self.work, cancel=cancel)
        self.assertEqual(caught.exception.code, 'CANCELLED')
        toolchain.assert_not_called()
