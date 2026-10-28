import hashlib
import io
import json
import os
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from native_port import launcher_update as update
from native_port.errors import PortError
from native_port.tasks import Cancellation


def binary(seed=b'new'):
    if os.name == 'nt':
        header=bytearray(512);header[:2]=b'MZ';struct.pack_into('<I',header,60,128)
        header[128:132]=b'PE\0\0';struct.pack_into('<H',header,132,0x8664)
        struct.pack_into('<H',header,150,2);struct.pack_into('<H',header,152,0x20b)
    else:
        header=bytearray(64);header[:6]=b'\x7fELF\x02\x01';header[8:11]=b'AI\x02'
        struct.pack_into('<H',header,18,62)
    return bytes(header)+seed*40


def release(tag='v0.1.5', platform=None, **extra):
    name = update.asset_name(platform)
    base = 'https://github.com/Akimitsu76/Lantern-Recomp/releases/'
    data = {'tag_name': tag, 'html_url': base + 'tag/' + tag,
        'prerelease': False, 'draft': False, 'body': 'Notas da versão',
        'assets': [{'name': name, 'state': 'uploaded', 'size': len(binary()),
                    'browser_download_url': base + 'download/' + tag + '/' + name},
                   {'name': 'SHA256SUMS', 'browser_download_url': base + 'download/' + tag + '/SHA256SUMS'}]}
    data.update(extra)
    return data


class LauncherUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.new = binary()
        self.sha = hashlib.sha256(self.new).hexdigest()
        self.release = update.select_release([release()], current='0.1.4-rc.3')

    def test_semver_prereleases_are_ordered_numerically_and_below_final(self):
        values = ['0.1.4-alpha.1', '0.1.4-beta.2', '0.1.4-rc.2', '0.1.4-rc.10', '0.1.4', '0.1.5-rc.1']
        self.assertEqual(sorted(values, key=update.version_key), values)
        for bad in ['latest', '../release', '0.1', 'v1.2.3;echo x']:
            with self.assertRaises(ValueError):update.version_key(bad)

    def test_release_selects_platform_and_preserves_renamed_repo_identity(self):
        found = update.select_release([release(platform='linux'), release('v0.1.6', platform='win32')],
                                      current='0.1.4', platform='linux')
        self.assertEqual(found['tag'], 'v0.1.5')
        self.assertEqual(update.REPOSITORY_ID, 1431033413)

    def test_no_downgrade_or_same_version_even_when_release_date_is_newer(self):
        self.assertIsNone(update.select_release([release('v0.1.3'), release('v0.1.4-rc.3')]))

    def test_drafts_and_incomplete_uploads_are_ignored(self):
        draft = release('v0.9.0', draft=True)
        incomplete = release('v0.8.0');incomplete['assets'].pop()
        self.assertIsNone(update.select_release([draft, incomplete]))

    def test_prerelease_channel_can_be_disabled_even_if_github_marks_rc_stable(self):
        found = update.select_release([release('v0.2.0-rc.1'), release('v0.1.5')], include_prerelease=False)
        self.assertEqual(found['tag'], 'v0.1.5')

    def test_asset_urls_cannot_switch_repo_host_or_tag(self):
        for bad in ['http://github.com/Akimitsu76/Lantern-Recomp/releases/download/v0.1.5/x',
                    'https://evil.example/download',
                    'https://github.com/other/Lantern-Recomp/releases/download/v0.1.5/x']:
            row = release();row['assets'][0]['browser_download_url'] = bad
            self.assertIsNone(update.select_release([row]))
        handler = update._Redirects()
        with self.assertRaises(PortError):
            handler.redirect_request(None, None, 302, '', {}, 'https://evil.example/payload')

    def test_duplicate_platform_assets_and_checksums_are_ignored(self):
        for index in (0, 1):
            row = release();row['assets'].append(dict(row['assets'][index]))
            self.assertIsNone(update.select_release([row]))

    def test_checksum_must_match_exact_name_once(self):
        name = update.asset_name()
        self.assertEqual(update.checksum_for(f'{self.sha}  {name}\n'.encode(), name), self.sha)
        for raw in [f'{self.sha}  ../{name}', f'{self.sha}  {name}\n{self.sha}  {name}', 'invalid']:
            with self.assertRaises(PortError):update.checksum_for(raw.encode(), name)

    def responses(self, checksum=None, payload=None):
        checksum = self.sha if checksum is None else checksum
        return [io.BytesIO(f'{checksum}  {update.asset_name()}\n'.encode()),
                io.BytesIO(self.new if payload is None else payload)]

    def test_download_verifies_hash_size_and_binary_and_reports_progress(self):
        events = []
        with patch.object(update, '_open', side_effect=self.responses()):
            downloaded = update.download_release(self.release, Cancellation(), events.append, directory=self.root)
        self.assertEqual(Path(downloaded['path']).read_bytes(), self.new)
        self.assertEqual(downloaded['sha256'], self.sha)
        self.assertEqual(events[-1]['completed'], len(self.new))
        self.assertFalse(list(self.root.rglob('*.part')))

    def test_corrupted_or_truncated_download_is_removed_without_touching_profile(self):
        profile = self.root/'save';profile.write_bytes(b'keep')
        for payload in (b'incomplete', self.new[:-1] + b'?'):
            with patch.object(update, '_open', side_effect=self.responses(payload=payload)):
                with self.assertRaises(PortError):update.download_release(self.release, Cancellation(), directory=self.root)
            self.assertEqual(profile.read_bytes(), b'keep')
            self.assertEqual(list(self.root.iterdir()), [profile])

    def test_api_digest_must_agree_with_checksum_file(self):
        self.release['digest'] = 'sha256:' + '0'*64
        with patch.object(update, '_open', side_effect=self.responses()):
            with self.assertRaises(PortError):update.download_release(self.release, Cancellation(), directory=self.root)
        self.assertFalse(list(self.root.iterdir()))

    def test_cancelled_download_leaves_no_installable_file(self):
        cancel = Cancellation()
        def emit(_):cancel.cancel()
        with patch.object(update, '_open', side_effect=self.responses()):
            with self.assertRaises(PortError):update.download_release(self.release, cancel, emit, directory=self.root)
        self.assertFalse(list(self.root.iterdir()))

    def plan(self):
        target = self.root/update.asset_name();target.write_bytes(binary(b'old'))
        source = self.root/'download'/update.asset_name();source.parent.mkdir();source.write_bytes(self.new)
        return {'schema':1, 'target':str(target), 'source':str(source), 'sha256':self.sha,
                'old_sha256':update.file_hash(target), 'asset':update.asset_name(),
                'version':'v0.1.5', 'parent_pid':12345, 'nonce':'a'*48}

    def test_atomic_install_keeps_old_launcher_as_backup_and_never_moves_user_data(self):
        plan = self.plan()
        save = self.root/'user/save';save.parent.mkdir();save.write_bytes(b'campaign')
        backup = update.commit_install(plan)
        self.assertEqual(Path(plan['target']).read_bytes(), self.new)
        self.assertEqual(backup.read_bytes(), binary(b'old'))
        self.assertEqual(save.read_bytes(), b'campaign')

    def test_changed_target_or_bad_download_never_replaces_current_file(self):
        plan = self.plan();target = Path(plan['target']);target.write_bytes(b'new user file')
        with self.assertRaises(PortError):update.commit_install(plan)
        self.assertEqual(target.read_bytes(), b'new user file')
        self.assertFalse(list(self.root.glob('*.previous-*')))

    def test_staging_copies_helper_and_never_downloads_or_executes_remote_commands(self):
        plan = self.plan()
        data = {'path':plan['source'],'sha256':self.sha,'asset':update.asset_name(),'version':'v0.1.5'}
        with patch.object(update.subprocess, 'Popen') as spawn:
            path, _ = update.stage_install(data, Path(plan['target']), parent_pid=12345)
        args, kwargs = spawn.call_args
        self.assertNotIn('shell', kwargs)
        self.assertIn('--aster-apply-update', args[0])
        self.assertEqual(Path(args[0][0]).read_bytes(), binary(b'old'))
        self.assertEqual(json.loads(path.read_text())['parent_pid'],12345)
        self.assertEqual(Path(plan['target']).read_bytes(),binary(b'old'))

    def test_failed_restart_restores_backup_and_records_failure(self):
        plan = self.plan();path = Path(plan['source']).parent/'install.json';path.write_text(json.dumps(plan))
        failed = Mock();failed.poll.return_value = 1
        with patch.object(update,'_wait_parent'), patch.object(update.subprocess,'Popen',return_value=failed) as spawn:
            self.assertEqual(update.apply_update(path),1)
        self.assertEqual(Path(plan['target']).read_bytes(),binary(b'old'))
        result = json.loads((self.root/'last-result.json').read_text())
        self.assertFalse(result['success']);self.assertEqual(spawn.call_count,2)

    def test_restart_health_requires_exact_version_and_nonce(self):
        plan = self.plan();path = Path(plan['source']).parent/'install.json';path.write_text(json.dumps(plan))
        def spawn(*args,**kwargs):
            health=Path(kwargs['env']['ASTER_UPDATE_HEALTH_FILE'])
            health.write_text(json.dumps({'nonce':plan['nonce'],'version':'0.1.5'}))
            return Mock()
        with patch.object(update,'_wait_parent'), patch.object(update.subprocess,'Popen',side_effect=spawn):
            self.assertEqual(update.apply_update(path),0)
        self.assertEqual(Path(plan['target']).read_bytes(),self.new)

    def test_source_checkout_cannot_be_self_replaced(self):
        with patch.object(update.sys,'frozen',False,create=True):
            self.assertIsNone(update.installed_executable())

    def test_cleanup_only_removes_successful_owned_staging_and_keeps_backup(self):
        folder = self.root/'download-owned';folder.mkdir()
        plan = {'nonce':'b'*48,'source':str(folder/update.asset_name())}
        (folder/'install.json').write_text(json.dumps(plan))
        marker=folder/'finished.json';marker.write_text(json.dumps({'nonce':'b'*48,'success':True}))
        os.utime(marker,(0,0))
        backup=self.root/'launcher.previous-hash';backup.write_bytes(b'old')
        active=self.root/'download-active';active.mkdir();(active/'file.part').write_bytes(b'partial')
        update.cleanup_downloads(self.root)
        self.assertFalse(folder.exists())
        self.assertEqual(backup.read_bytes(),b'old')
        self.assertEqual((active/'file.part').read_bytes(),b'partial')

    def test_rejects_dos_or_wrong_architecture_before_install(self):
        path=self.root/update.asset_name()
        for raw in [b'MZ'+b'\0'*62, b'\x7fELF'+b'\0'*60]:
            path.write_bytes(raw)
            with self.assertRaises(PortError):
                update.verify_binary(path,hashlib.sha256(raw).hexdigest(),update.asset_name())
