import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from native_port.spatial_sdk import CAPABILITY, verify_product, normalized_patch
from native_port.errors import PortError


class SpatialSdkTests(unittest.TestCase):
    def test_plain_and_git_patches_inventory_new_and_modified_files_equally(self):
        plain = ('--- /dev/null\n+++ b/include/new.h\n@@ -0,0 +1 @@\n+new\n'
                 '--- a/src/a.cpp\n+++ b/src/a.cpp\n@@ -1 +1 @@ old function\n-old\n+new\n')
        git = ('diff --git a/include/new.h b/include/new.h\nnew file mode 100644\n' +
               plain.replace('--- a/src/a.cpp', 'diff --git a/src/a.cpp b/src/a.cpp\n--- a/src/a.cpp'))
        self.assertEqual(normalized_patch(plain), normalized_patch(git))
        self.assertEqual(set(normalized_patch(plain)), {'include/new.h', 'src/a.cpp'})
        with self.assertRaises(PortError):
            normalized_patch(plain + plain)

    def test_capability_requires_complete_matching_hashes_and_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory)
            recipe = {'platform': 'win-amd64', 'patch': 'reviewed'}
            files = {}
            for name in ('bin/rexglue.exe', 'bin/rexruntimerd.dll', 'lib/cmake/rexglue/rexglueConfig.cmake'):
                path = prefix / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'public test artifact')
                files[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest = prefix / 'aster-spatial-sdk.json'
            manifest.write_text(json.dumps({'recipe': recipe, 'capability': CAPABILITY, 'files': files}))
            self.assertTrue(verify_product(prefix, recipe))
            self.assertFalse(verify_product(prefix, dict(recipe, patch='different ABI')))
            runtime = prefix / 'bin/rexruntimerd.dll'
            runtime.write_bytes(b'changed runtime')
            self.assertFalse(verify_product(prefix, recipe))
            files.pop('bin/rexruntimerd.dll')
            manifest.write_text(json.dumps({'recipe': recipe, 'capability': CAPABILITY, 'files': files}))
            self.assertFalse(verify_product(prefix, recipe), 'generator alone cannot establish a renderer capability')

    def test_capability_manifest_cannot_reference_files_outside_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            outside = base / 'outside.dll'
            outside.write_bytes(b'outside')
            prefix = base / 'sdk'
            prefix.mkdir()
            recipe = {'platform': 'win-amd64'}
            files = {'../outside.dll': hashlib.sha256(outside.read_bytes()).hexdigest()}
            (prefix / 'aster-spatial-sdk.json').write_text(json.dumps({
                'recipe': recipe, 'capability': CAPABILITY, 'files': files}))
            self.assertFalse(verify_product(prefix, recipe))
