import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


packaging = module('packaging_tk_test', 'package_launcher.py')
builder = module('builder_tk_test', 'build_launcher_tk.py')


class TkRuntimeTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt', 'Linux PyInstaller invocation')
    def test_linux_freeze_includes_pillow_dynamic_tk_finder(self):
        class CommandCaptured(Exception):
            pass
        with tempfile.TemporaryDirectory() as temporary:
            fake_script = Path(temporary) / 'scripts/package_launcher.py'
            with patch.object(packaging, '__file__', str(fake_script)), \
                 patch.object(packaging.sys, 'argv', ['package_launcher.py', '--output', temporary]), \
                 patch.object(packaging, 'launcher_resource_arguments', return_value=[]), \
                 patch.object(packaging, 'needs_tk_xft_overlay', return_value=False), \
                 patch.object(packaging.subprocess, 'run', side_effect=CommandCaptured) as run:
                with self.assertRaises(CommandCaptured):
                    packaging.main()
            command = run.call_args.args[0]
            imports = [command[index + 1] for index, value in enumerate(command) if value == '--hidden-import']
            self.assertIn('PIL._tkinter_finder', imports)

    def make_runtime(self, root):
        prefix = root / 'runtime'
        files = {'lib/libtcl9tk9.0.so': b'Tk9 Xft',
                 'lib/libfontconfig.so.1': b'Fontconfig',
                 'tk_data/tk.tcl': b'set tk_patchLevel 9.0.4',
                 'launcher_fontconfig.conf': b'<fontconfig/>',
                 'LICENSES/tk-license.terms': b'Tk license'}
        for name, raw in files.items():
            file = prefix / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
        manifest = {'schema': 1, 'tk': '9.0.4', 'abi': 'Tcl9', 'xft': True,
                    'glibc_ceiling': '2.27',
                    'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in files.items()}}
        (prefix / 'TK_RUNTIME.json').write_text(json.dumps(manifest))
        bundle = root / 'bundle'
        (bundle / '_internal').mkdir(parents=True)
        (bundle / '_internal/libtcl9tk9.0.so').write_bytes(b'old no-xft')
        return prefix, bundle, manifest

    def test_overlay_replaces_backend_and_copies_scripts_config_and_license(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix, bundle, _ = self.make_runtime(Path(temporary))
            packaging.apply_tk_runtime(bundle, prefix)
            self.assertEqual((bundle / '_internal/libtcl9tk9.0.so').read_bytes(), b'Tk9 Xft')
            self.assertTrue((bundle / '_internal/_tk_data/tk.tcl').is_file())
            self.assertTrue((bundle / '_internal/launcher_fontconfig.conf').is_file())
            self.assertTrue((bundle / 'LICENSES/Tk9-Xft/tk-license.terms').is_file())
            self.assertTrue((bundle / 'LICENSES/Tk9-Xft/TK_RUNTIME.json').is_file())

    def test_tampering_is_rejected_before_replacing_original_backend(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix, bundle, _ = self.make_runtime(Path(temporary))
            (prefix / 'lib/libfontconfig.so.1').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed'):
                packaging.apply_tk_runtime(bundle, prefix)
            self.assertEqual((bundle / '_internal/libtcl9tk9.0.so').read_bytes(), b'old no-xft')

    def test_unlisted_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix, bundle, _ = self.make_runtime(Path(temporary))
            (prefix / 'lib/extra.so').write_bytes(b'unlisted')
            with self.assertRaisesRegex(ValueError, 'inventory'):
                packaging.apply_tk_runtime(bundle, prefix)

    def test_linked_runtime_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix, bundle, _ = self.make_runtime(Path(temporary))
            path = prefix / 'lib/libfontconfig.so.1'
            outside = Path(temporary) / 'outside'
            outside.write_bytes(path.read_bytes())
            path.unlink()
            try:
                path.symlink_to(outside)
            except OSError:
                self.skipTest('symlinks not supported')
            with self.assertRaisesRegex(ValueError, 'changed'):
                packaging.apply_tk_runtime(bundle, prefix)

    def test_tk8_and_wrong_abi_do_not_accept_tk9_overlay(self):
        with tempfile.TemporaryDirectory() as temporary:
            prefix, bundle, manifest = self.make_runtime(Path(temporary))
            (bundle / '_internal/libtcl9tk9.0.so').unlink()
            with self.assertRaisesRegex(ValueError, 'Tcl9/Tk9'):
                packaging.apply_tk_runtime(bundle, prefix)
            manifest['abi'] = 'Tcl8'
            (prefix / 'TK_RUNTIME.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                packaging.apply_tk_runtime(bundle, prefix)

    def test_no_xft_portable_build_is_detected_before_packaging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lib = root / 'lib/libtcl9tk9.0.so'
            lib.parent.mkdir()
            lib.write_bytes(b'9.0.4.no-xft.x11')
            self.assertTrue(packaging.needs_tk_xft_overlay(root))
            lib.write_bytes(b'XftFontOpen')
            self.assertFalse(packaging.needs_tk_xft_overlay(root))

    def test_builder_rejects_host_glibc_or_build_search_paths(self):
        for versions, dynamic, problem in [
                ('GLIBC_2.38', '', 'glibc2.27'),
                ('GLIBC_2.14', '(RUNPATH) /host/build', 'search path')]:
            with patch.object(builder, 'elf', side_effect=[versions, dynamic]):
                with self.assertRaisesRegex(ValueError, problem):
                    builder.audit_elf(Path('libtk.so'))
        with patch.object(builder, 'elf', side_effect=[
                'GLIBC_2.2.5 GLIBC_2.27', '(NEEDED) Shared library: [libXft.so.2]']):
            self.assertEqual(builder.audit_elf(Path('libtk.so')), ['libXft.so.2'])

    def test_pinned_inputs_are_official_and_hashes_complete(self):
        inputs = json.loads((ROOT / 'scripts/launcher_tk_inputs.json').read_text())
        for source in inputs['sources'].values():
            self.assertTrue(source['url'].startswith('https://codeload.github.com/tcltk/'))
            self.assertEqual(len(source['sha256']), 64)
        self.assertGreaterEqual(len(inputs['packages']), 35)
        for source in inputs['packages'].values():
            self.assertTrue(source['url'].startswith('https://archive.ubuntu.com/ubuntu/pool/'))
            self.assertEqual(len(source['sha256']), 64)
            self.assertGreater(source['bytes'], 0)

    def test_extract_cannot_write_outside_private_sysroot(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = io.BytesIO()
            with tarfile.open(fileobj=raw, mode='w') as archive:
                item = tarfile.TarInfo('../outside')
                item.size = 3
                archive.addfile(item, io.BytesIO(b'bad'))
            with self.assertRaises(tarfile.FilterError):
                builder.unpack(raw.getvalue(), Path(temporary) / 'sysroot')
            self.assertFalse((Path(temporary) / 'outside').exists())


if __name__ == '__main__':
    unittest.main()
