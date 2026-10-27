from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from native_port import prerequisites as deps
from native_port.errors import PortError
from native_port.tasks import Cancellation
from native_port.workspace import Workspace


class PrerequisiteTests(unittest.TestCase):
    def test_supported_families_and_no_guessed_installer_for_unknown_os(self):
        for release, expected in [({'ID':'cachyos','ID_LIKE':'arch'},'arch'),
                                  ({'ID':'ubuntu','VERSION_ID':'24.04'},'apt'),
                                  ({'ID':'debian','VERSION_ID':'13'},'apt'),
                                  ({'ID':'fedora','VERSION_ID':'43'},'fedora')]:
            self.assertEqual(deps.distro_family(release), expected)
        for release in [{'ID':'unknown'}, {'ID':'debian','VERSION_ID':'12'},
                        {'ID':'ubuntu','VERSION_ID':'22.04'}]:
            with self.assertRaises(PortError):
                deps.distro_family(release)

    def test_linux_install_plan_is_allowlisted_and_does_not_upgrade_the_os(self):
        which = lambda name: '/usr/bin/'+name
        packages = deps.package_plan(['compiler','git','x11'], 'arch')
        command = deps.linux_install_command(packages, 'arch', which=which)
        self.assertEqual(command[:5], ['/usr/bin/pkexec','/usr/bin/pacman','-S','--needed','--noconfirm'])
        self.assertIn('clang', command)
        self.assertNotIn('-Syu', command)
        self.assertNotIn('sh', command)
        debian = deps.package_plan(['compiler'], 'apt', {'ID':'debian'})
        self.assertIn('clang-19', debian)
        self.assertNotIn('clang-18', debian)
        self.assertNotIn('/usr/bin/pkexec', deps.linux_install_command(['git'], 'arch', which=which, elevated=True))
        for malicious in [['git; rm -rf /'], ['--overwrite'], ['../../script']]:
            with self.assertRaises(PortError):
                deps.linux_install_command(malicious, 'arch', which=which)
        with self.assertRaises(PortError):
            deps.package_plan(['untrusted-game-requirement'], 'arch')

    def test_windows_uses_exact_official_ids_and_real_cpp_components(self):
        commands = deps.windows_install_commands(['compiler','git','runtime'], which=lambda _: 'winget.exe')
        self.assertEqual(len(commands),3)
        self.assertTrue(all('--exact' in c and c[c.index('--source')+1]=='winget' for c in commands))
        compiler = next(c for c in commands if 'Microsoft.VisualStudio.2022.BuildTools' in c)
        overrides = compiler[compiler.index('--override')+1]
        self.assertIn('--wait', overrides)
        for component in deps.VS_COMPONENTS:
            self.assertIn('--add '+component, overrides)
        self.assertTrue(any('Microsoft.VCRedist.2015+.x64' in c for c in commands))
        with self.assertRaises(PortError):
            deps.windows_install_commands(['compiler'], which=lambda _: None)
        with self.assertRaises(PortError):
            deps.windows_install_commands(['arbitrary package'], which=lambda _: 'winget.exe')

    def test_ready_environment_never_runs_an_installer(self):
        with patch.object(deps, 'inspect_build_dependencies', return_value={'ready':True}), \
                patch.object(deps, 'run_process') as execute:
            deps.ensure_build_dependencies(Path('.'), Mock(), Cancellation(), lambda _:None, allowed=True)
        execute.assert_not_called()

    def test_missing_dependencies_cannot_install_without_explicit_enable(self):
        with patch.object(deps, 'inspect_build_dependencies', return_value={'ready':False,'missing':['git']}), \
                patch.object(deps, 'run_process') as execute, self.assertRaises(PortError) as error:
            deps.ensure_build_dependencies(Path('.'), Mock(), Cancellation(), lambda _:None)
        self.assertEqual(error.exception.code,'DEPENDENCIES_NEEDED')
        execute.assert_not_called()

    def test_installer_is_rechecked_and_completed_transaction_keeps_its_log(self):
        initial={'ready':False,'missing':['git'],'family':'windows'}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); work=Workspace(root/'.aster',root); cancel=Cancellation()
            with patch.object(deps, 'inspect_build_dependencies', side_effect=[initial,{'ready':True}]) as inspect, \
                    patch.object(deps, 'windows_install_commands', return_value=[['winget.exe','fixed-test-command']]), \
                    patch.object(deps, 'run_process', return_value={'returncode':0,'stdout':'installed','stderr':''}) as execute:
                self.assertTrue(deps.ensure_build_dependencies(root,work,cancel,lambda _:None,allowed=True)['ready'])
            self.assertEqual(inspect.call_count,2)
            self.assertIsNot(execute.call_args.args[2],cancel, 'Do not kill an elevated installer mid-transaction')
            self.assertEqual(len(list((root/'.aster/reports/dependencies').glob('*/step-0.json'))),1)

    def test_installer_success_does_not_claim_readiness_when_requirements_still_missing(self):
        initial={'ready':False,'missing':['git'],'family':'windows'}
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.object(deps,'inspect_build_dependencies',return_value=initial), \
                    patch.object(deps,'windows_install_commands',return_value=[['winget.exe','fixed-test-command']]), \
                    patch.object(deps,'run_process',return_value={'returncode':0,'stdout':'','stderr':''}), \
                    self.assertRaises(PortError) as error:
                deps.ensure_build_dependencies(root,Workspace(root/'.aster',root),Cancellation(),lambda _:None,allowed=True)
            self.assertEqual(error.exception.code,'DEPENDENCIES_RECHECK')


if __name__=='__main__':
    unittest.main()
