import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from native_port.errors import PortError
from native_port.tasks import Cancellation
from native_port.texture_enhance import sha
from native_port.texture_pack import load_material_catalog, prepare_texture_pack, validate_texture_pack, SOURCE_XEX_SHA256
from native_port.workspace import Workspace


class TexturePackTests(unittest.TestCase):
    def catalog(self, root, count=2):
        entries = []
        for i in range(count):
            folder = root / ('source' + str(i)); folder.mkdir()
            Image.new('RGBA', (64, 64), (40 + 40*i, 100, 180, 255)).save(folder/'original.dds', pixel_format='DXT1')
            with Image.open(folder/'original.dds') as source: rgba = source.convert('RGBA')
            rgba.save(folder/'original.png')
            canonical = hashlib.sha256(b'aster-texture-rgba8-v1\0' + struct.pack('<II', 64, 64) + rgba.tobytes()).hexdigest()
            data = {'status': 'original-inspection-only', 'runtime_replacement': False,
                    'dds_sha256': sha(folder/'original.dds'), 'canonical_rgba8_sha256': canonical,
                    'capture_metadata': {'format': 18}, 'game_xex_sha256': SOURCE_XEX_SHA256}
            (folder/'inspection.json').write_text(json.dumps(data))
            entries.append({'classification': 'color-opaque', 'reviewed': True,
                            'inspection': folder.name + '/inspection.json',
                            'canonical_rgba8_sha256': canonical, 'dds_sha256': data['dds_sha256']})
        path = root/'catalog.json'
        path.write_text(json.dumps({'schema': 1, 'source_xex_sha256': SOURCE_XEX_SHA256, 'entries': entries}))
        return path

    def inference(self, argv, *args, **kwargs):
        source = Image.open(argv[argv.index('-i')+1]).convert('RGB')
        source.resize((256, 256)).save(argv[argv.index('-o')+1])
        return {'stdout': 'synthetic test', 'stderr': '', 'returncode': 0}

    def patches(self):
        return (patch('native_port.texture_enhance.ensure_engine', return_value=(Path('engine'), Path('models'), 'test-engine', {})),
                patch('native_port.texture_enhance.run_process', side_effect=self.inference))

    def test_real_batch_production_reuses_child_inference_and_verifies_all_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog(root); work = Workspace(root/'.aster', root)
            engine, inference = self.patches()
            with engine, inference as process:
                output = prepare_texture_pack(catalog, root, work)
                self.assertEqual(process.call_count, 2)
                self.assertEqual(validate_texture_pack(output), output)
                self.assertEqual(prepare_texture_pack(catalog, root, work), output)
                self.assertEqual(process.call_count, 2)
                manifest = json.loads((output/'pack.json').read_text())
                self.assertEqual(manifest['counts']['included'], 2)
                self.assertFalse(manifest['runtime_rendered'])
                child = manifest['materials'][0]['bc']
                (output/child/'texture.dds').write_bytes(b'tampered')
                with self.assertRaises(PortError): validate_texture_pack(output)
                with self.assertRaises(PortError): prepare_texture_pack(catalog, root, work)
                self.assertEqual(process.call_count, 2)

    def test_catalog_rejects_duplicates_traversal_symlinks_and_source_identity_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog(root); original = json.loads(catalog.read_text())
            for bad in ('../outside.json', '/absolute.json', 'C:/outside.json', 'source0\\inspection.json'):
                data = json.loads(json.dumps(original)); data['entries'][0]['inspection'] = bad
                catalog.write_text(json.dumps(data))
                with self.assertRaises(PortError): load_material_catalog(catalog)
            data = json.loads(json.dumps(original)); data['entries'][1] = data['entries'][0]
            catalog.write_text(json.dumps(data))
            with self.assertRaises(PortError): load_material_catalog(catalog)
            catalog.write_text(json.dumps(original)); (root/'source0'/'original.dds').write_bytes(b'tamper')
            with self.assertRaises(PortError): load_material_catalog(catalog)
            if hasattr(Path, 'symlink_to'):
                linked = root/'linked'; linked.symlink_to(root/'source1', target_is_directory=True)
                data = json.loads(json.dumps(original)); data['entries'] = [data['entries'][1]]
                data['entries'][0]['inspection'] = 'linked/inspection.json'; catalog.write_text(json.dumps(data))
                with self.assertRaises(PortError): load_material_catalog(catalog)

    def test_unknown_normal_ui_are_excluded_without_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog(root, 4); data = json.loads(catalog.read_text())
            for entry, classification in zip(data['entries'], ('unknown', 'normal', 'ui', 'shadow')):
                entry['classification'] = classification
            catalog.write_text(json.dumps(data))
            parsed = load_material_catalog(catalog)
            self.assertEqual(parsed['counts'], {'total':4, 'included':0, 'excluded':4})
            engine, inference = self.patches()
            with engine, inference as process:
                with self.assertRaises(PortError): prepare_texture_pack(catalog, root, Workspace(root/'.aster', root))
                process.assert_not_called()

    def test_cancellation_resumes_after_completed_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog(root); work = Workspace(root/'.aster', root)
            cancel = Cancellation()
            def progress(event):
                if event.get('message', '').startswith('Textura HD preparada'):
                    cancel.cancel()
            engine, inference = self.patches()
            with engine, inference as process:
                with self.assertRaises(PortError): prepare_texture_pack(catalog, root, work, cancel=cancel, emit=progress)
                self.assertEqual(process.call_count, 1)
                output = prepare_texture_pack(catalog, root, work)
                self.assertEqual(process.call_count, 2)
                self.assertEqual(validate_texture_pack(output), output)

    def test_pack_rejects_extra_file_recipe_change_and_wrong_xex(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog(root, 1); work = Workspace(root/'.aster', root)
            engine, inference = self.patches()
            with engine, inference: output = prepare_texture_pack(catalog, root, work)
            with self.assertRaises(PortError): validate_texture_pack(output, '0'*64)
            extra = output/'surprise'; extra.write_text('extra')
            with self.assertRaises(PortError): validate_texture_pack(output)
            extra.unlink()
            data = json.loads((output/'pack.json').read_text()); data['recipe']['materials'][0]['dimensions'] = [256,256]
            (output/'pack.json').write_text(json.dumps(data))
            with self.assertRaises(PortError): validate_texture_pack(output)

    def test_index_count_and_dds_budget_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog(root, 1); work = Workspace(root/'.aster', root)
            engine, inference = self.patches()
            with engine, inference:
                with patch('native_port.texture_pack.MAX_DDS_BYTES', 1):
                    with self.assertRaises(PortError): prepare_texture_pack(catalog, root, work)
                output = prepare_texture_pack(catalog, root, work)
            data = json.loads((output/'pack.json').read_text())
            child = output / data['materials'][0]['bc']
            self.assertEqual(validate_texture_pack(child), child)
            index = output/'texture-pack.index'
            index.write_text(index.read_text().replace('ASTERHDPACK1 1', 'ASTERHDPACK1 2'))
            data['files']['texture-pack.index'] = sha(index)
            (output/'pack.json').write_text(json.dumps(data))
            with self.assertRaises(PortError): validate_texture_pack(output)

    def test_catalog_has_bounded_entry_count(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog(root, 1); data = json.loads(catalog.read_text())
            data['entries'] *= 257; catalog.write_text(json.dumps(data))
            with self.assertRaises(PortError): load_material_catalog(catalog)

    def test_batch_scales_are_real_and_share_per_material_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); catalog = self.catalog(root, 2); work = Workspace(root/'.aster', root)
            engine, inference = self.patches()
            with engine, inference as process:
                high = prepare_texture_pack(catalog, root, work, host_scale=2)
                ultra = prepare_texture_pack(catalog, root, work, host_scale=4)
                self.assertEqual(process.call_count, 2)
                for output, scale in [(high, 2), (ultra, 4)]:
                    self.assertEqual(validate_texture_pack(output), output)
                    manifest = json.loads((output/'pack.json').read_text())
                    self.assertEqual(manifest['recipe']['host_scale'], scale)
                    for material in manifest['materials']:
                        self.assertEqual(material['dimensions'], [64 * scale, 64 * scale])
                data = json.loads((ultra/'pack.json').read_text())
                data['recipe']['host_scale'] = 2
                (ultra/'pack.json').write_text(json.dumps(data))
                with self.assertRaises(PortError): validate_texture_pack(ultra)
                self.assertEqual(process.call_count, 2)


if __name__ == '__main__': unittest.main()
