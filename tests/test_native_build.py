import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import zipfile

from native_port.errors import PortError
from native_port.native_build import build_native, read_install, safe_extract, verify_install, cpu_sdk_identity
from native_port.native_cache import apply_patch_exact
from native_port.tasks import Cancellation
from native_port.workspace import Workspace


class NativeBuildTests(unittest.TestCase):
    def test_versioned_c_and_cpp_compilers_stay_paired(self):
        from native_port.native_build import companion_c_compiler
        self.assertEqual(Path(companion_c_compiler('/usr/bin/clang++-18')).name, 'clang-18')
        self.assertEqual(Path(companion_c_compiler('/usr/bin/clang++')).name, 'clang')
        self.assertEqual(Path(companion_c_compiler('clang-cl.exe')).name, 'clang-cl.exe')
        self.assertEqual(Path(companion_c_compiler('clang-cl.EXE')).name, 'clang-cl.EXE')

    def test_cpu_reuse_keeps_presenter_and_unknown_patches_abi_sensitive(self):
        base = {'revision': 'pinned', 'platform': 'linux-amd64', 'baseline_flags': 'x86-64-v2',
                'patches': {'0004-embedded-spatial-sdk.patch': 'presenter-abi'}}
        graphics = dict(base, patches={**base['patches'], '0008-hd-selection-cache.patch': 'gpu-fix'})
        self.assertEqual(cpu_sdk_identity(base), cpu_sdk_identity(graphics))
        clock = dict(base, patches={**base['patches'], '0023-guest-vblank-video-mode-clock.patch': 'implementation-only'})
        self.assertEqual(cpu_sdk_identity(base), cpu_sdk_identity(clock))
        centers = dict(base, patches={**base['patches'], '0024-scaled-pixel-parameter-centers.patch': 'implementation-only'})
        self.assertEqual(cpu_sdk_identity(base), cpu_sdk_identity(centers))
        for name in ('0004-embedded-spatial-sdk.patch',
                     '0022-idle-notification-presentation.patch',
                     '0034-bounded-hd-source-cache.patch', 'future-unknown.patch'):
            changed = dict(base, patches={**base['patches'], name: 'new'})
            self.assertNotEqual(cpu_sdk_identity(base), cpu_sdk_identity(changed))
        self.assertNotEqual(cpu_sdk_identity(base), cpu_sdk_identity(None))
        self.assertNotEqual(cpu_sdk_identity(base), cpu_sdk_identity(dict(base, platform='win-amd64')))

    def test_zip_cannot_escape_or_create_symlinks(self):
        for name, mode in [('../outside', 0), ('C:/outside', 0), ('/outside', 0),
                           ('link', 0o120777 << 16)]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                archive = root / 'input.zip'
                with zipfile.ZipFile(archive, 'w') as z:
                    item = zipfile.ZipInfo(name)
                    item.external_attr = mode
                    z.writestr(item, 'unsafe')
                with self.assertRaises(PortError):
                    safe_extract(archive, root / 'out')
                self.assertFalse((root / 'outside').exists())

    def test_reviewed_patch_rejects_wrong_context_without_changing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'file.cpp'
            source.write_text('one\ntwo\n')
            patch_text = ('diff --git a/file.cpp b/file.cpp\n--- a/file.cpp\n+++ b/file.cpp\n'
                          '@@ -1,2 +1,2 @@\n one\n-wrong\n+new\n')
            with self.assertRaises(PortError):
                apply_patch_exact(root, patch_text)
            self.assertEqual(source.read_text(), 'one\ntwo\n')
            changed = apply_patch_exact(root, patch_text.replace('-wrong', '-two'))
            self.assertEqual(changed, [source])
            self.assertEqual(source.read_text(), 'one\nnew\n')

    def test_reviewed_new_file_and_cross_file_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            new = ('diff --git a/include/new.h b/include/new.h\nnew file mode 100644\n'
                   '--- /dev/null\n+++ b/include/new.h\n@@ -0,0 +1,2 @@\n+one\n+two\n')
            bad = ('diff --git a/old.h b/old.h\n--- a/old.h\n+++ b/old.h\n'
                   '@@ -1 +1 @@\n-wrong\n+fixed\n')
            (root / 'old.h').write_text('original\n')
            with self.assertRaises(PortError):
                apply_patch_exact(root, new + bad)
            self.assertFalse((root / 'include/new.h').exists())
            apply_patch_exact(root, new)
            self.assertEqual((root / 'include/new.h').read_text(), 'one\ntwo\n')
            with self.assertRaises(PortError):
                apply_patch_exact(root, new)

    def test_patch_new_file_rejects_escape_symlink_and_bad_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'sdk'
            root.mkdir()
            (root / 'alias').symlink_to(Path(directory), target_is_directory=True)
            for name in ('../escape.h', '/escape.h', 'alias/escape.h', 'C:/escape.h'):
                text = f'--- /dev/null\n+++ b/{name}\n@@ -0,0 +1 @@\n+unsafe\n'
                with self.subTest(name=name), self.assertRaises(PortError):
                    apply_patch_exact(root, text)
            with self.assertRaises(PortError):
                apply_patch_exact(root, '--- /dev/null\n+++ b/new.h\n@@ -0,0 +1,2 @@\n+only one\n')
            self.assertFalse((root / 'new.h').exists())

    def test_local_generation_is_cached_preserves_case_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / 'Green_Lantern Assets'
            game.mkdir()
            xex = game / 'Default.XEX'
            xex.write_bytes(b'original synthetic dump')
            sha = hashlib.sha256(xex.read_bytes()).hexdigest()
            for relative in ['games/green_lantern_rex_hints.toml',
                             'integrations/rexglue/portable_timing.cpp',
                             'integrations/rexglue/runtime_save_slots.cpp',
                             'integrations/rexglue/runtime_languages.cpp',
                             'integrations/rexglue/plugin-only/CMakeLists.txt',
                             'integrations/rexglue/patches/0001-vulkan-driver-pipeline-cache.patch',
                             'integrations/rexglue/patches/0003-vulkan-deferred-pipelines.patch',
                             'integrations/rexglue/patches/0005-texture-inspection-capture.patch',
                             'integrations/rexglue/patches/0006-reviewed-hd-texture-override.patch',
                             'integrations/rexglue/presenter-filter/CMakeLists.txt']:
                p = root / relative
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text('public fixture')
            prefix = root / 'sdk'
            (prefix / 'bin').mkdir(parents=True)
            (prefix / 'lib').mkdir()
            (prefix / 'lib' / ('rexruntimerd.dll' if os.name == 'nt' else 'librexruntimerd.so')).write_bytes(b'runtime')
            cache = root / '.aster/tools/cache-plugin/librexgpu-xenosrd.so'
            cache.parent.mkdir(parents=True)
            cache.write_bytes(b'patched cache')
            work = Workspace(root / '.aster', root)
            info = {'game_directory': str(game), 'path': str(xex)}
            # Exercise the platform's actual orchestration branch with a fully
            # mocked toolchain. Windows intentionally cannot select legacy SDK.
            def spatial_recipe(project_root, platform):
                renderer = Path(project_root) / 'integrations/rexglue/patches/0006-reviewed-hd-texture-override.patch'
                return {'revision': 'synthetic-sdk', 'platform': platform,
                        'patches': {renderer.name: hashlib.sha256(renderer.read_bytes()).hexdigest()}}
            def process(arguments, cwd, cancel, **options):
                if 'init' in arguments:
                    project = Path(arguments[arguments.index('--project-root') + 1])
                    project.mkdir(parents=True)
                    (project / 'aster_green_lantern_manifest.toml').write_text('[entrypoint]\nincludes=[]\n')
                    (project / 'CMakeLists.txt').write_text('rexglue_setup_target(aster_green_lantern)\n')
                if 'codegen' in arguments:
                    manifest = Path(arguments[-1])
                    parsed = tomllib.loads(manifest.read_text())
                    self.assertEqual(parsed['entrypoint']['includes'], ['hints.toml'])
                    self.assertEqual((manifest.parent / parsed['entrypoint']['file_path']).resolve(), xex)
                    generated = manifest.parent / 'generated/default/file.cpp'
                    generated.parent.mkdir(parents=True)
                    generated.write_text('synthetic generated fixture')
                if '--build' in arguments:
                    build = Path(arguments[arguments.index('--build') + 1])
                    build.mkdir(parents=True, exist_ok=True)
                    (build / ('aster_green_lantern.exe' if os.name == 'nt' else 'aster_green_lantern')).write_bytes(b'fresh generated executable')
                return {'stdout': 'ok', 'stderr': '', 'returncode': 0}
            with patch.dict('os.environ', {'ASTER_USE_LEGACY_SDK': '0'}), \
                    patch('native_port.native_build.XEX_SHA256', sha), \
                    patch('native_port.native_build.inspect_source', return_value=info), \
                    patch('native_port.native_build.ensure_sdk', return_value=prefix), \
                    patch('native_port.spatial_sdk.spatial_sdk_recipe', side_effect=spatial_recipe), \
                    patch('native_port.spatial_sdk.build_spatial_sdk', return_value=prefix), \
                    patch('native_port.native_build.toolchain', return_value=('cmake', 'ninja', 'clang++', {})), \
                    patch('native_port.native_build.run_process', side_effect=process) as command, \
                    patch('native_port.native_cache.build_cache_plugin', return_value=cache), \
                    patch('native_port.native_cache.build_presenter_filter', return_value=cache), \
                    patch('native_port.native_cache.build_arena_lifetime', return_value=cache):
                first = build_native(game, work)
                count = command.call_count
                second = build_native(game, work)
                self.assertEqual(first, second)
                project = root / Path(first['binary']).parent.parent / 'project'
                for name in ('runtime_save_slots.cpp', 'runtime_languages.cpp'):
                    self.assertIn(name, (project / 'CMakeLists.txt').read_text())
                    self.assertEqual((project / name).read_text(), 'public fixture')
                self.assertEqual(command.call_count, count, 'cache hit must not run codegen/compiler')
                before_codegen = sum('codegen' in call.args[0] for call in command.call_args_list)
                (root / '.aster/config/native-install.json').unlink()
                resumed = build_native(game, work)
                self.assertEqual(sum('codegen' in call.args[0] for call in command.call_args_list), before_codegen)
                self.assertEqual(resumed['binary'], first['binary'])
                self.assertFalse(first['ready'])
                self.assertFalse(first['gameplay_verified'])
                verify_install(root, first)
                self.assertEqual(read_install(root), first)
                previous_codegen = sum('codegen' in call.args[0] for call in command.call_args_list)
                previous_host = (root / first['binary']).read_bytes()
                (root / 'integrations/rexglue/patches/0006-reviewed-hd-texture-override.patch').write_text('updated renderer only')
                first = build_native(game, work)
                self.assertEqual(sum('codegen' in call.args[0] for call in command.call_args_list), previous_codegen,
                                 'renderer-only updates must reuse the verified CPU host')
                self.assertEqual((root / first['binary']).read_bytes(), previous_host)
                verify_install(root, first)
                (root / first['binary']).write_bytes(b'changed')
                with self.assertRaises(PortError):
                    verify_install(root, first)
            self.assertEqual(xex.read_bytes(), b'original synthetic dump')
            self.assertFalse((root / '.aster/runtime').exists())

    def test_malformed_install_cannot_escape_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / '.aster/config/native-install.json'
            path.parent.mkdir(parents=True)
            from native_port.native_build import XEX_SHA256
            for files in [['bad'], {'../escape': 'a' * 64}]:
                path.write_text(json.dumps({'schema': 1, 'state': 'built', 'xex_sha256': XEX_SHA256,
                                           'binary': '../escape', 'files': files,
                                           'game_root': 'dump', 'renderer': 'vulkan-fsi'}))
                with self.assertRaises(PortError):
                    read_install(root)

    def test_unsupported_dump_stops_before_downloading_or_compiling(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            game = root / 'dump'
            game.mkdir()
            source = game / 'default.xex'
            source.write_bytes(b'unsupported')
            with patch('native_port.native_build.inspect_source', return_value={
                    'path': str(source), 'game_directory': str(game)}), \
                    patch('native_port.native_build.toolchain') as compiler, \
                    patch('native_port.prerequisites.ensure_build_dependencies') as dependencies, \
                    self.assertRaises(PortError) as error:
                build_native(game, Workspace(root / '.aster', root), allow_download=True, install_dependencies=True)
            self.assertEqual(error.exception.code, 'BUILD_REVISION')
            compiler.assert_not_called()
            dependencies.assert_not_called()
            self.assertFalse((root / '.aster').exists())
