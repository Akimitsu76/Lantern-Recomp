"""The real Vulkan adapter must compile both licensed FXAA Quality variants."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import generate_swap_aa as aa
from native_port.spatial_sdk import normalized_patch, PATCHES
from native_port.native_build import cpu_sdk_identity

NAME = '0031-vulkan-fxaa-quality-parity.patch'


class SwapQualityTests(unittest.TestCase):
    def test_pinned_vendor_generated_source_and_sdk_patch_match(self):
        files = normalized_patch((ROOT / 'integrations/rexglue/patches' / NAME).read_text())
        # Extract the added private header from the exact SDK patch.
        rows = files['src/graphics/vulkan/aster_fxaa_quality.h']
        # normalized_patch returns normalized hunk text rather than final bytes.
        patch = (ROOT / 'integrations/rexglue/patches' / NAME).read_text()
        hunk = patch.split('+++ b/src/graphics/vulkan/aster_fxaa_quality.h\n', 1)[1]
        generated = ('\n'.join(row[1:] for row in hunk.splitlines() if row.startswith('+')) + '\n').encode()
        self.assertEqual(generated, aa.header_bytes())
        self.assertEqual((aa.DIRECTORY / 'fxaa_quality_source.h').read_bytes(), aa.header_bytes())
        self.assertIn('integrations/rexglue/patches/' + NAME, PATCHES)
        before = {'patches': {'0004-embedded-spatial-sdk.patch': 'abi'}}
        self.assertEqual(cpu_sdk_identity(before), cpu_sdk_identity({'patches': {**before['patches'], NAME: 'shader-source-only'}}))

    @unittest.skipUnless(shutil.which('clang++') or shutil.which('c++'), 'C++ compiler unavailable')
    def test_embedded_cpp_source_returns_exact_validated_glsl(self):
        with tempfile.TemporaryDirectory(prefix='aster-fxaa-cpp-') as temp:
            temp = Path(temp)
            (temp / 'shader.h').write_bytes(aa.header_bytes())
            (temp / 'main.cpp').write_text('#include "shader.h"\n#include <cstdio>\nint main(int argc,char**argv){std::fputs(rex::graphics::vulkan::aster_fxaa::GetQualitySource(argc>1),stdout);return 0;}\n')
            compiler = shutil.which('clang++') or shutil.which('c++')
            binary = temp / ('check.exe' if sys.platform == 'win32' else 'check')
            result = subprocess.run([compiler, '-std=c++17', str(temp / 'main.cpp'), '-o', str(binary)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            for index, expected in enumerate(aa.sources()):
                actual = subprocess.check_output([str(binary)] + (['extreme'] if index else []), timeout=10)
                self.assertEqual(actual.decode('utf8'), expected)

    @unittest.skipUnless(shutil.which('glslangValidator') and shutil.which('spirv-val'), 'GLSL/SPIRV development tools unavailable')
    def test_real_compute_shaders_validate_without_derivatives_or_game_assets(self):
        with tempfile.TemporaryDirectory(prefix='aster-fxaa-test-') as temp:
            for name, text in zip(('normal', 'extreme'), aa.sources()):
                source = Path(temp) / (name + '.comp'); source.write_text(text)
                binary = source.with_suffix('.spv')
                result = subprocess.run(['glslangValidator', '-V', str(source), '-o', str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run(['spirv-val', str(binary)], capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
