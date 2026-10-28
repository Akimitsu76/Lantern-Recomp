"""Campaign library dispatch and launch capability checks; no runtime is started."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from native_port.errors import PortError
from native_port.tasks import Cancellation
from native_port.texture_pack import validate_texture_pack

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/play_green_lantern.py'
spec = importlib.util.spec_from_file_location('campaign_play_green_lantern', SOURCE)
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class CampaignLibraryDispatchTests(unittest.TestCase):
    def test_validate_texture_pack_dispatches_library_with_identity_and_cancellation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'library.json').write_text('{}')
            token=Cancellation();expected='f'*64
            with patch('native_port.texture_library.validate_texture_library',return_value=root) as library, \
                 patch('native_port.texture_pack.validate_prepared_pack') as legacy:
                self.assertEqual(validate_texture_pack(root,expected,token),root)
                library.assert_called_once_with(root,expected,token)
                legacy.assert_not_called()

    def test_cancelled_validation_never_dispatches_or_hashes(self):
        token=Cancellation();token.cancel()
        with patch('native_port.texture_library.validate_texture_library') as library:
            with self.assertRaises(PortError) as error: validate_texture_pack('/not-read',cancel=token)
            self.assertEqual(error.exception.code,'CANCELLED')
            library.assert_not_called()

    def test_library_root_symlink_rejected_before_dispatch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);actual=root/'actual';actual.mkdir()
            (actual/'library.json').write_text('{}');linked=root/'linked'
            try: linked.symlink_to(actual,target_is_directory=True)
            except OSError: self.skipTest('Host does not support symlink creation')
            with patch('native_port.texture_library.validate_texture_library') as library:
                with self.assertRaises(PortError): validate_texture_pack(linked)
                library.assert_not_called()


class CampaignLaunchTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.root=Path(self.directory.name);self.library=self.root/'campaign-library';self.library.mkdir()
        (self.library/'library.json').write_text('{}')
        self.child=self.library/'material';self.child.mkdir()
        (self.child/'manifest.json').write_text(json.dumps({'recipe':{'host_scale':2}}))
        self.environment={'KEEP':'original','ASTER_HD_TEXTURE_PACK_DIR':'inherited-stale-selection'}

    def installation(self,*patches):
        return {'recipe':{'sdk_spatial':{'patches':{name:'fixed-digest'for name in patches}}}}

    def call(self,installation):
        parser=argparse.ArgumentParser(prog='campaign-test')
        return launcher.hd_texture_environment(str(self.library),installation,self.environment,parser)

    def test_library_requires_0012_before_validation(self):
        installation=self.installation('0006-reviewed-hd-texture-override.patch',
            '0009-multi-material-hd-pack.patch','0011-hd-texture-scales.patch')
        error=io.StringIO()
        with patch('native_port.texture_pack.validate_texture_pack_cached') as validate, \
             contextlib.redirect_stderr(error),self.assertRaises(SystemExit) as stopped:
            self.call(installation)
        self.assertEqual(stopped.exception.code,2)
        self.assertIn('Bibliotecas da campanha',error.getvalue())
        validate.assert_not_called()
        self.assertEqual(self.environment['ASTER_HD_TEXTURE_PACK_DIR'],'inherited-stale-selection')

    def test_validated_library_is_forwarded_with_0012(self):
        installation=self.installation('0006-reviewed-hd-texture-override.patch','0012-campaign-texture-library.patch')
        with patch('native_port.texture_pack.validate_texture_pack_cached',return_value=self.library) as validate:
            result=self.call(installation)
        validate.assert_called_once_with(str(self.library),
            Path(launcher.__file__).resolve().parent.parent / '.aster/cache/texture-validation')
        self.assertEqual(result['ASTER_HD_TEXTURE_PACK_DIR'],str(self.library))
        self.assertEqual(result['KEEP'],'original')
        self.assertEqual(self.environment['ASTER_HD_TEXTURE_PACK_DIR'],'inherited-stale-selection')

    def test_library_ultra_requires_0011_scale_capability(self):
        (self.child/'manifest.json').write_text(json.dumps({'recipe':{'host_scale':4}}))
        installation=self.installation('0006-reviewed-hd-texture-override.patch','0012-campaign-texture-library.patch')
        error=io.StringIO()
        with patch('native_port.texture_pack.validate_texture_pack_cached',return_value=self.library), \
             contextlib.redirect_stderr(error),self.assertRaises(SystemExit):
            self.call(installation)
        self.assertIn('Ultra 4x',error.getvalue())

    def test_ultra_library_with_both_capabilities_is_forwarded(self):
        (self.child/'manifest.json').write_text(json.dumps({'recipe':{'host_scale':4}}))
        installation=self.installation('0006-reviewed-hd-texture-override.patch',
            '0012-campaign-texture-library.patch','0011-hd-texture-scales.patch')
        with patch('native_port.texture_pack.validate_texture_pack_cached',return_value=self.library):
            result=self.call(installation)
        self.assertEqual(result['ASTER_HD_TEXTURE_PACK_DIR'],str(self.library))

    def test_corrupt_library_prevents_launch_environment(self):
        installation=self.installation('0006-reviewed-hd-texture-override.patch','0012-campaign-texture-library.patch')
        error=io.StringIO()
        with patch('native_port.texture_pack.validate_texture_pack_cached',side_effect=PortError('HD_LIBRARY','corrupt library')), \
             contextlib.redirect_stderr(error),self.assertRaises(SystemExit):
            self.call(installation)
        self.assertIn('corrupt library',error.getvalue())

    def test_no_selection_removes_inherited_override(self):
        parser=argparse.ArgumentParser()
        result=launcher.hd_texture_environment(None,None,self.environment,parser)
        self.assertNotIn('ASTER_HD_TEXTURE_PACK_DIR',result)
        self.assertEqual(result['KEEP'],'original')
        self.assertIn('ASTER_HD_TEXTURE_PACK_DIR',self.environment)

    def test_legacy_single_material_does_not_require_campaign_capability(self):
        (self.library/'library.json').unlink()
        (self.library/'manifest.json').write_text(json.dumps({'recipe':{'host_scale':2}}))
        installation=self.installation('0006-reviewed-hd-texture-override.patch')
        with patch('native_port.texture_pack.validate_texture_pack_cached',return_value=self.library):
            result=self.call(installation)
        self.assertEqual(result['ASTER_HD_TEXTURE_PACK_DIR'],str(self.library))


if __name__ == '__main__':
    unittest.main()
