"""Exercise the real SDK DDS loader, with synthetic bytes and no GPU/game assets.

Set ASTER_TEST_UI_SDK_PREFIX to a built SDK. Windows CI must run this after its
native D3D12 build; Wine/Python contracts alone do not validate the native SDK.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('ASTER_TEST_UI_SDK_PREFIX'), 'Built native SDK not explicitly selected')
class NativeCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='aster-ui-native-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        root = Path(__file__).resolve().parents[1]
        prefix = Path(os.environ['ASTER_TEST_UI_SDK_PREFIX']).resolve()
        cls.environment = dict(os.environ)
        cls.environment['PATH'] = str(prefix / 'bin') + os.pathsep + cls.environment.get('PATH', '')
        cmake = shutil.which('cmake')
        if not cmake:
            raise AssertionError('Native UI contract requires CMake')
        build = cls.folder / 'build'
        subprocess.run([cmake, '-S', str(root / 'integrations/rexglue/ui-coverage-contract'),
                        '-B', str(build), '-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release',
                        '-DCMAKE_PREFIX_PATH=' + str(prefix)], check=True, capture_output=True, text=True,
                       env=cls.environment, timeout=120)
        result = subprocess.run([cmake, '--build', str(build), '--parallel', '2'],
                                capture_output=True, text=True, env=cls.environment, timeout=120)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.binary = build / ('aster_ui_coverage_contract.exe' if os.name == 'nt' else 'aster_ui_coverage_contract')

    def test_real_native_loader_accepts_both_formats_and_rejects_tampered_layout(self):
        import xxhash
        from PIL import Image
        from native_port.texture_ui import prepare_ui_pack
        source = self.folder / 'source.dds'
        image = Image.new('RGBA', (64, 64), 'white')
        image.putalpha(Image.frombytes('L', image.size, bytes(range(256)) * 16))
        image.save(source, format='DDS', pixel_format='DXT5')
        glyphs = [dict(codepoint=65, page=0, x=0, y=0, width=64, height=64, xoffset=0, yoffset=0, advance=32)]
        def check(folder, expected):
            result = subprocess.run([str(self.binary), str(folder), expected], capture_output=True,
                                    text=True, env=self.environment, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for fmt in ('bc3', 'rgba8'):
            target = prepare_ui_pack(source, glyphs, self.folder / fmt, reviewed=True, coverage_format=fmt)
            check(target, fmt)
        target = self.folder / 'rgba8'; original = (target / 'texture.dds').read_bytes()
        original_index = (target / 'texture.index').read_text().split()
        for offset, value in ((92, 0), (128, 0), (112, 1), (28, 1)):
            raw = bytearray(original); raw[offset] = value
            (target / 'texture.dds').write_bytes(raw)
            tokens = original_index.copy(); tokens[5] = xxhash.xxh3_128_hexdigest(raw)
            (target / 'texture.index').write_text(' '.join(tokens) + '\n')
            with self.subTest(offset=offset): check(target, 'reject')
