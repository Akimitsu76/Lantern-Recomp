import json
import os
import subprocess
import threading
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from fixtures import xex


@unittest.skipUnless(os.environ.get('DISPLAY'), 'Sem DISPLAY; execute com xvfb-run para testar GUI.')
class LauncherTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f'Display inacessível: {e}; execute xvfb-run')
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = Path(self.tmp.name)
        project_patch = patch('native_port.launcher.PROJECT', self.project)
        project_patch.start()
        self.addCleanup(project_patch.stop)
        from native_port.launcher import Launcher
        self.app = Launcher(self.root)
        self.addCleanup(self.app.close)

    def wait_task(self):
        deadline = time.monotonic() + 5
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(.01)
        self.assertFalse(self.app.busy)

    def test_reviewed_hd_pack_is_used_only_for_higher_texture_presets(self):
        self.app.source.set(str(self.project / 'dump'))
        self.app.hd_texture_pack.set(str(self.project / 'reviewed-pack'))
        self.app.choose_preset('high')
        high = self.app.play_command()
        self.assertEqual(high[high.index('--hd-texture-pack') + 1], str(self.project / 'reviewed-pack'))
        self.app.choose_preset('low')
        self.assertNotIn('--hd-texture-pack', self.app.play_command())
        self.assertEqual(self.app.config()['hd_texture_pack'], str(self.project / 'reviewed-pack'))

    @patch('native_port.launcher.messagebox.askyesno', return_value=True)
    def test_batch_hd_prepare_progress_and_selection_are_per_user(self, confirm):
        import sys
        import types
        catalog = self.project / 'reviewed.json'
        catalog.write_text('{}')
        pack = self.project / 'prepared-pack'
        pack.mkdir()
        (pack / 'pack.json').write_text(json.dumps({'entries': [{}, {}]}))
        self.app.hd_texture_catalog.set(str(catalog))
        started, release = threading.Event(), threading.Event()
        main_thread = threading.get_ident()
        def prepare(catalog_arg, root, work, **kwargs):
            self.assertNotEqual(threading.get_ident(), main_thread)
            self.assertEqual(catalog_arg, catalog)
            self.assertTrue(kwargs['allow_download'])
            kwargs['emit']({'completed': 1, 'total': 2, 'message': '1 de 2 materiais'})
            started.set()
            release.wait(3)
            return pack
        module = types.SimpleNamespace(prepare_texture_pack=prepare, validate_texture_pack=lambda _, **kwargs: pack)
        with patch.dict(sys.modules, {'native_port.texture_pack': module}):
            self.app.prepare_hd_pack()
            self.assertTrue(started.wait(2))
            self.root.update()
            time.sleep(.06)
            self.root.update()
            self.assertEqual(float(self.app.hd_progress['value']), 50)
            self.assertIn('1 de 2', self.app.hd_status.get())
            self.assertEqual(str(self.app.hd_prepare_button['state']), 'disabled')
            self.assertEqual(str(self.app.compile_button['state']), 'disabled')
            self.assertEqual(str(self.app.hd_cancel_button['state']), 'normal')
            release.set()
            self.wait_task()
        self.assertEqual(self.app.hd_texture_pack.get(), str(pack))
        self.assertEqual(float(self.app.hd_progress['value']), 100)
        self.app.choose_preset('high')
        self.assertIn('2 materiais preparados', self.app.hd_status.get())
        self.assertIn('habilitado', self.app.hd_status.get())
        for target in ('30', '60'):
            self.app.choose_target(target)
            cfg = self.app.config()
            self.assertEqual(cfg['hd_texture_pack'], str(pack))
            self.assertEqual(cfg['hd_texture_catalog'], str(catalog))
        self.assertFalse((self.project / '.aster/runtime').exists())

    @patch('native_port.launcher.filedialog.askdirectory')
    def test_hd_selection_validates_in_worker_and_can_be_cancelled(self, choose):
        import sys
        import types
        choose.return_value = str(self.project / 'new-pack')
        self.app.hd_texture_pack.set('previous-pack')
        started = threading.Event()
        main_thread = threading.get_ident()
        def validate(directory, cancel=None):
            self.assertNotEqual(threading.get_ident(), main_thread)
            started.set()
            while True:
                cancel.check()
                cancel.event.wait(.01)
        with patch.dict(sys.modules, {'native_port.texture_pack': types.SimpleNamespace(validate_texture_pack=validate)}):
            self.app.select_hd_pack()
            self.assertTrue(started.wait(2))
            self.assertTrue(self.app.busy)
            self.assertEqual(str(self.app.hd_cancel_button['state']), 'normal')
            self.root.update()
            self.app.hd_cancel_button.invoke()
            self.wait_task()
        self.assertEqual(self.app.hd_texture_pack.get(), 'previous-pack')
        self.assertIn('CANCELLED', self.app.status.get())

    @patch('native_port.launcher.filedialog.askdirectory')
    def test_hd_selection_commits_only_validated_result(self, choose):
        import sys
        import types
        pack = self.project / 'verified-pack'
        pack.mkdir()
        (pack / 'pack.json').write_text(json.dumps({'entries': [{}]}))
        choose.return_value = str(pack)
        validate = Mock(return_value=pack)
        with patch.dict(sys.modules, {'native_port.texture_pack': types.SimpleNamespace(validate_texture_pack=validate)}):
            self.app.select_hd_pack()
            self.wait_task()
        self.assertEqual(self.app.hd_texture_pack.get(), str(pack))
        self.assertEqual(self.app.hd_material_count, 1)
        self.assertIn('verificado', self.app.status.get())
        self.assertIsNotNone(validate.call_args.kwargs['cancel'])

    @patch('native_port.launcher.messagebox.askyesno', return_value=True)
    def test_batch_hd_cancel_preserves_previous_pack(self, _):
        import sys
        import types
        self.app.hd_texture_catalog.set(str(self.project / 'reviewed.json'))
        self.app.hd_texture_pack.set('previous-pack')
        def prepare(*args, cancel, **kwargs):
            while True:
                cancel.check()
                cancel.event.wait(.01)
        module = types.SimpleNamespace(prepare_texture_pack=prepare, validate_texture_pack=Mock())
        with patch.dict(sys.modules, {'native_port.texture_pack': module}):
            self.app.prepare_hd_pack()
            self.app.hd_cancel_button.invoke()
            self.wait_task()
        self.assertEqual(self.app.hd_texture_pack.get(), 'previous-pack')
        self.assertIn('CANCELLED', self.app.status.get())
        self.assertEqual(str(self.app.hd_cancel_button['state']), 'disabled')
        module.validate_texture_pack.assert_not_called()

    @patch('native_port.launcher.messagebox.askyesno', return_value=False)
    def test_batch_hd_does_not_download_after_declining(self, confirm):
        self.app.hd_texture_catalog.set('reviewed.json')
        with patch.object(self.app, 'start') as start:
            self.app.prepare_hd_pack()
        start.assert_not_called()
        self.assertFalse(self.app.busy)

    def test_launch_disabled_and_invalid_source(self):
        self.assertEqual(str(self.app.launch_button['state']), 'disabled')
        self.app.source.set('/nonexistent/source.iso')
        self.app.inspect()
        self.wait_task()
        self.assertIn('SOURCE_PATH', self.app.status.get())
        self.assertEqual(str(self.app.launch_button['state']), 'disabled')

    def test_inspect_synthetic_xex(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'fixture.xex'
            p.write_bytes(xex())
            self.app.source.set(str(p))
            self.app.inspect()
            self.wait_task()
        self.assertIn('575207E9', self.app.summary.get('1.0', 'end'))
        self.assertEqual(str(self.app.launch_button['state']), 'disabled')

    @patch('native_port.diagnostics.local_tool', return_value=None)
    @patch('native_port.diagnostics.shutil.which', return_value=None)
    def test_missing_dependencies_visible(self, _, __):
        self.app.doctor()
        self.wait_task()
        self.assertIn('cmake: não encontrado', self.app.environment.get('1.0', 'end'))
        self.assertEqual(str(self.app.launch_button['state']), 'disabled')

    def test_desktop_layout_snapshot(self):
        try:
            from PIL import ImageGrab
        except ImportError:
            self.skipTest('Pillow opcional ausente; snapshot não executado.')
        from native_port.workspace import Workspace
        PROJECT = Path(__file__).resolve().parents[1]
        self.root.update()
        x, y = self.root.winfo_rootx(), self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if self.root.winfo_screenwidth() < w or self.root.winfo_screenheight() < h:
            self.skipTest('Xvfb menor que a janela; use -screen 0 1440x900x24 para o snapshot.')
        for button in (self.app.inspect_button, self.app.prepare_button, self.app.launch_button,
                       self.app.experimental_button, self.app.stop_experimental_button,
                       self.app.folder_button, self.app.select_button):
            self.assertTrue(button.winfo_ismapped(), str(button))
            self.assertGreater(button.winfo_width(), 10)
            self.assertGreater(button.winfo_height(), 10)
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), x + w)
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), y + h)
            parent = button.master
            self.assertLessEqual(button.winfo_y() + button.winfo_height(), parent.winfo_height())
        self.app.tabs.select(self.app.graphics_tab)
        self.root.update()
        for button in list(self.app.preset_buttons.values()) + list(self.app.target_buttons.values()):
            self.assertTrue(button.winfo_ismapped(), str(button))
            self.assertLessEqual(button.winfo_rootx() + button.winfo_width(), x + w)
            self.assertLessEqual(button.winfo_rooty() + button.winfo_height(), y + h)
        self.app.tabs.select(self.app.play_tab)
        self.root.update()
        path = Workspace(PROJECT / '.aster', PROJECT).path('reports/launcher.png')
        path.parent.mkdir(parents=True, exist_ok=True)
        capture_options = {'window': self.root.winfo_id()} if os.name == 'nt' else {
            'bbox': (x, y, x+w, y+h), 'xdisplay': os.environ['DISPLAY']}
        ImageGrab.grab(**capture_options).save(path)

    @patch('native_port.launcher.filedialog.askdirectory')
    def test_select_extracted_folder_and_persist(self, choose):
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        (folder / 'assets.dat').write_bytes(b'synthetic')
        choose.return_value = str(folder)
        self.app.select_folder()
        self.wait_task()
        self.assertEqual(self.app.source.get(), str(folder))
        self.assertIn('2 arquivos', self.app.summary.get('1.0', 'end'))
        from native_port.settings import load
        self.assertEqual(load(self.project)['source'], str(folder))
        self.assertEqual(str(self.app.launch_button['state']), 'normal')
        self.assertIn('GERAR PORT', str(self.app.launch_button['text']))

    def test_layout_at_minimum_size(self):
        self.root.geometry('1088x696')
        self.root.update()
        x, y = self.app.play_tab.winfo_rootx(), self.app.play_tab.winfo_rooty()
        for button in (self.app.inspect_button, self.app.prepare_button, self.app.launch_button,
                       self.app.folder_button, self.app.select_button, self.app.experimental_button,
                       self.app.stop_experimental_button, self.app.open_profile_button):
            self.assertTrue(button.winfo_ismapped(), str(button))
            self.assertGreater(button.winfo_width(), 10)
            self.assertGreater(button.winfo_height(), 10)
            self.assertLessEqual(button.winfo_rootx()+button.winfo_width(), x+self.app.play_tab.winfo_width())
            self.assertLessEqual(button.winfo_rooty()+button.winfo_height(), y+self.app.play_tab.winfo_height())
            parent = button.master
            self.assertLessEqual(button.winfo_y() + button.winfo_height(), parent.winfo_height())

    def test_generation_controls_fit_and_full_hd_reaches_play_command(self):
        self.root.geometry('1088x720')
        self.app.tabs.select(self.app.build_tab)
        self.root.update()
        bottom = self.app.build_tab.winfo_rooty() + self.app.build_tab.winfo_height()
        for widget in [self.app.progress, self.app.build_start_button, self.app.build_cancel_button]:
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreaterEqual(widget.winfo_height(), 5 if widget == self.app.progress else 24)
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)
        self.app.output_resolution.set('1920x1080')
        command = self.app.play_command('/tmp/synthetic-dump')
        self.assertEqual(command[command.index('--output-resolution') + 1], '1920x1080')
        self.app.choose_target('60')
        self.assertIn('save compartilhado', self.app.quick_profile.get())

    def test_graphics_and_advanced_texture_tools_are_separate_flows(self):
        self.root.geometry('1088x720')
        self.assertNotIn(str(self.app.hd_tab), self.app.tabs.tabs())
        self.assertNotIn('Texturas HD', [button['text'] for button in self.app.nav_buttons.values()])
        self.app.tabs.select(self.app.graphics_tab)
        self.app.choose_preset('high')
        self.root.update()
        self.app.graphics_canvas.yview_moveto(1)
        self.root.update()
        bottom = self.app.graphics_tab.winfo_rooty() + self.app.graphics_tab.winfo_height()
        right = self.app.graphics_tab.winfo_rootx() + self.app.graphics_tab.winfo_width()
        for widget in (self.app.hd_auto_button, self.app.hd_cancel_button, self.app.hd_progress):
            self.assertTrue(widget.winfo_ismapped())
            self.assertGreater(widget.winfo_height(), 5)
            self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(), bottom)
            self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(), right)
        self.assertTrue(self.app.render_scale_spin.winfo_ismapped())
        self.assertFalse(self.app.msaa_check.winfo_ismapped())
        self.app.show_texture_tools()
        self.root.update()
        self.assertTrue(self.app.hd_select_button.winfo_ismapped())
        self.app.hd_tab.withdraw()

    def test_preset_preparation_uses_dump_without_manual_catalog_selection(self):
        import sys
        import types
        from native_port.workspace import Workspace
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        pack = self.project / 'pack'
        pack.mkdir()
        self.app.source.set(str(folder))
        self.app.choose_preset('high')
        main_thread = threading.get_ident()
        def ensure(source, data, root, work, **kwargs):
            self.assertNotEqual(threading.get_ident(), main_thread)
            self.assertEqual(source, folder)
            self.assertEqual(data['texture_quality'], 'high')
            self.assertEqual(root, self.project)
            self.assertIsInstance(work, Workspace)
            self.assertTrue(kwargs['allow_download'])
            kwargs['emit']({'completed': 1, 'total': 1, 'message': 'Preparado'})
            return {'pack': str(pack), 'material_count': 2, 'state': 'prepared'}
        with patch.dict(sys.modules, {'native_port.texture_pipeline': types.SimpleNamespace(ensure_graphics_textures=ensure)}), \
                patch('native_port.launcher.filedialog.askopenfilename') as choose:
            self.app.prepare_graphics_textures()
            self.wait_task()
        choose.assert_not_called()
        self.assertEqual(self.app.hd_texture_catalog.get(), '')
        self.assertEqual(self.app.hd_texture_pack.get(), str(pack))
        self.assertIn('2 materiais preparados', self.app.hd_status.get())
        self.assertEqual(self.app.tabs.select(), str(self.app.graphics_tab))

    def test_lower_presets_never_prepare_or_download_hd(self):
        for preset in ('low', 'default'):
            self.app.choose_preset(preset)
            with patch.object(self.app, 'start') as start:
                self.app.prepare_graphics_textures()
            start.assert_not_called()
            self.assertIn('originais', self.app.hd_status.get())

    def test_fullscreen_and_sharpness_reach_command_and_settings(self):
        self.app.choose_preset('high')
        self.app.fullscreen.set(True)
        self.app.fsr_sharpness.set(90)
        command = self.app.play_command('/tmp/synthetic-dump')
        self.assertEqual(command[command.index('--fullscreen') + 1], 'on')
        self.assertEqual(command[command.index('--fsr-sharpness') + 1], '90')
        self.assertTrue(self.app.config()['graphics']['fullscreen'])
        self.assertEqual(self.app.config()['graphics']['fsr_sharpness'], 90)
        self.app.choose_preset('low')
        self.assertEqual(str(self.app.sharpness_spin['state']), 'disabled')
        self.assertEqual(str(self.app.hd_auto_button['state']), 'disabled')

    def test_export_diagnostic_stays_in_workspace(self):
        self.app.export_report()
        path = Path(self.app.report_path.get())
        self.assertTrue(path.is_relative_to(self.project / '.aster/reports'))
        self.assertTrue(path.is_file())

    def test_build_progress_uses_real_counts_and_preserves_cancelled_state(self):
        def work():
            while True:
                self.app.cancel.check()
                self.app.cancel.event.wait(.01)
        self.app.start(work, 'Gerar port')
        self.app.queue.put(('event', '', {'stage': 'dump', 'state': 'completed'}))
        self.app.queue.put(('event', '', {'stage': 'compile', 'state': 'running',
                                        'completed': 4, 'total': 10, 'unit': 'targets'}))
        self.root.update()
        time.sleep(.06)
        self.root.update()
        self.assertEqual(float(self.app.progress['value']), 40)
        self.assertIn('4 de 10', self.app.build_measure.get())
        self.assertEqual(self.app.build_count.get(), '1 de 6 etapas concluídas')
        self.assertEqual(str(self.app.build_cancel_button['state']), 'normal')
        self.app.build_cancel_button.invoke()
        self.wait_task()
        self.assertEqual(self.app.stage_states['compile'], 'cancelled')
        self.assertEqual(self.app.build_heading.get(), 'Geração cancelada')
        self.assertNotEqual(float(self.app.progress['value']), 100)

    def test_build_without_total_indicates_activity_and_success_stays_visible(self):
        self.app.build_running = True
        self.app._build_event({'stage': 'codegen', 'state': 'running'})
        self.assertEqual(str(self.app.progress['mode']), 'indeterminate')
        self.assertNotIn('%', self.app.build_measure.get())
        self.app.build_running = False
        self.app.start(lambda: {'state': 'built', 'binary': 'synthetic'}, 'Gerar port')
        self.wait_task()
        self.assertEqual(float(self.app.progress['value']), 100)
        self.assertEqual(self.app.build_count.get(), '6 de 6 etapas concluídas')
        self.assertEqual(self.app.tabs.select(), str(self.app.build_tab))

    @patch('native_port.pipeline.diagnostics', return_value={'tools': {}})
    def test_prepare_folder_records_blocker(self, _):
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        (folder / 'assets').write_bytes(b'synthetic')
        self.app.source.set(str(folder))
        self.app.prepare()
        self.wait_task()
        import json
        report = json.loads((self.project / '.aster/reports/latest.json').read_text())
        self.assertEqual(report['state'], 'blocked')
        self.assertFalse(report['ready'])
        self.assertIn('compilação bloqueada', self.app.status.get())
        self.assertEqual(str(self.app.launch_button['state']), 'normal')
        self.assertEqual(str(self.app.launch_button['text']), 'GERAR PORT NATIVO')

    def test_cancel_worker_is_visible(self):
        def action():
            while True:
                self.app.cancel.check()
                self.app.cancel.event.wait(.01)
        self.app.start(action, 'Cancelamento de teste')
        self.assertEqual(str(self.app.cancel_button['state']), 'normal')
        self.app.cancel_button.invoke()
        self.wait_task()
        self.assertEqual(str(self.app.cancel_button['state']), 'disabled')
        self.assertIn('CANCELLED', self.app.status.get())
        self.assertEqual(self.app.task_tree.item('Cancelamento de teste')['values'][0], 'cancelled')

    def experimental_folder(self):
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        from native_port.launcher import MODE_FILES
        for binary, report in MODE_FILES.values():
            binary_path = self.project / binary
            binary_path.parent.mkdir(parents=True, exist_ok=True)
            binary_path.write_bytes(b'synthetic executable')
            report_path = self.project / report
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text('{}')
        self.app.source.set(str(folder))
        self.app._refresh_engine_status()
        return folder

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_validates_in_worker_and_restores_play(self, validate, spawn):
        folder = self.experimental_folder()
        threads = []
        def validation(*args, **kwargs):
            threads.append(threading.current_thread())
            return subprocess.CompletedProcess(args[0], 0, stdout='Validado', stderr='')
        validate.side_effect = validation
        spawn.return_value = Mock(pid=123, wait=Mock(return_value=0))
        self.app.play_experimental()
        self.wait_task()
        self.assertNotEqual(threads[0], threading.main_thread())
        self.assertEqual(validate.call_args.args[0][-1], '--dry-run')
        self.assertEqual(spawn.call_args.args[0][-1], str(folder))
        self.assertEqual(spawn.call_args.args[0][2:6], ['--shader-mode', 'async', '--vsync', 'on'])
        self.assertFalse(self.app.last_result['ready'])
        self.assertEqual(str(self.app.launch_button['state']), 'normal')
        self.assertEqual(str(self.app.compile_button['state']), 'normal')
        self.assertEqual(str(self.app.experimental_button['state']), 'normal')
        self.assertIsNone(self.app.experimental_process)

    @patch('native_port.launcher.messagebox.askyesno', return_value=True)
    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_60fps_forwards_flag_and_isolated_mode(self, validate, spawn, confirm):
        folder = self.experimental_folder()
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        spawn.return_value = Mock(pid=123, wait=Mock(return_value=0))
        self.app.play_experimental_60fps()
        self.wait_task()
        confirm.assert_called_once()
        command = spawn.call_args.args[0]
        self.assertEqual(command[2:6], ['--shader-mode', 'async', '--vsync', 'on'])
        self.assertIn('--fps-target', command)
        self.assertEqual(command[command.index('--fps-target') + 1], '60')
        self.assertEqual(command[-1], str(folder))
        self.assertIn('--fps-target', validate.call_args.args[0])
        self.assertEqual(validate.call_args.args[0][-1], '--dry-run')
        self.assertEqual(self.app.last_result['fps_target'], '60')
        self.assertIn('Sessão 60 fps encerrada', self.app.status.get())
        self.assertEqual(self.app.task_tree.item('Jogar 60 fps experimental')['values'][0], 'completed')

    @patch('native_port.launcher.messagebox.askyesno', return_value=False)
    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_60fps_warning_cancel_does_not_spawn(self, validate, spawn, confirm):
        self.experimental_folder()
        self.app.play_experimental_60fps()
        confirm.assert_called_once()
        validate.assert_not_called()
        spawn.assert_not_called()
        self.assertIn('cancelado', self.app.status.get())

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_forwards_selected_next_session_options(self, validate, spawn):
        self.experimental_folder()
        self.app.shader_mode.set('blocking')
        self.app.vsync.set(False)
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        spawn.return_value = Mock(pid=123, wait=Mock(return_value=0))
        self.app.play_experimental()
        self.wait_task()
        self.assertEqual(spawn.call_args.args[0][2:6], ['--shader-mode', 'blocking', '--vsync', 'off'])
        self.assertEqual(validate.call_args.args[0][:-1], spawn.call_args.args[0])
        self.assertEqual(str(self.app.shader_combo['state']), 'readonly')

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_validation_failure_does_not_spawn(self, validate, spawn):
        self.experimental_folder()
        validate.return_value = subprocess.CompletedProcess([], 2, stdout='', stderr='Hash divergente')
        self.app.play_experimental()
        self.wait_task()
        spawn.assert_not_called()
        self.assertIn('Hash divergente', self.app.status.get())

    @patch('native_port.launcher.subprocess.Popen', side_effect=OSError('Execução recusada'))
    @patch('native_port.launcher.subprocess.run')
    def test_experimental_spawn_error_recovers_controls(self, validate, spawn):
        self.experimental_folder()
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        self.app.play_experimental()
        self.wait_task()
        self.assertIn('Execução recusada', self.app.status.get())
        self.assertEqual(str(self.app.experimental_button['state']), 'normal')
        self.assertIsNone(self.app.experimental_process)

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_high_prepares_before_dry_run_and_spawn_and_persists_selection(self, validate, spawn):
        folder = self.experimental_folder()
        self.app.choose_preset('high')
        self.app.hd_texture_pack.set('previous-manual-pack')
        prepared_pack = str(self.project / 'automatic-high-pack')
        order = []
        main_thread = threading.get_ident()
        def prepare(source, data, root, work, **kwargs):
            self.assertNotEqual(threading.get_ident(), main_thread)
            self.assertEqual(source, folder)
            self.assertEqual(data['texture_quality'], 'high')
            self.assertTrue(kwargs['allow_download'])
            order.append('prepare')
            kwargs['emit']({'completed': 1, 'total': 2, 'message': 'Material preparado'})
            return {'pack': prepared_pack, 'material_count': 2, 'state': 'prepared', 'host_scale': 2}
        def checked(command, **kwargs):
            order.append('validate')
            self.assertEqual(order, ['prepare', 'validate'])
            self.assertEqual(command[-1], '--dry-run')
            self.assertEqual(command.count('--hd-texture-pack'), 1)
            self.assertEqual(command[command.index('--hd-texture-pack') + 1], prepared_pack)
            self.assertNotIn('previous-manual-pack', command)
            return subprocess.CompletedProcess(command, 0, stdout='verified', stderr='')
        def spawned(command, **kwargs):
            order.append('spawn')
            self.assertEqual(order, ['prepare', 'validate', 'spawn'])
            self.assertEqual(command[command.index('--hd-texture-pack') + 1], prepared_pack)
            return Mock(pid=123, wait=Mock(return_value=0))
        validate.side_effect = checked
        spawn.side_effect = spawned
        with patch('native_port.texture_pipeline.ensure_graphics_textures', side_effect=prepare), \
                patch('native_port.launcher.filedialog.askopenfilename') as choose:
            self.app.play()
            self.wait_task()
        choose.assert_not_called()
        self.assertEqual(order, ['prepare', 'validate', 'spawn'])
        self.assertEqual(self.app.hd_texture_pack.get(), prepared_pack)
        self.assertEqual(self.app.hd_material_count, 2)
        self.assertIn('2 materiais preparados', self.app.hd_status.get())
        saved = json.loads((self.project / '.aster/config/settings.json').read_text())
        self.assertEqual(saved['hd_texture_pack'], prepared_pack)
        self.assertEqual(saved['hd_texture_catalog'], '')
        self.assertEqual(saved['graphics']['preset'], 'high')

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_ultra_requests_ultra_texture_policy_before_start(self, validate, spawn):
        self.experimental_folder()
        self.app.choose_preset('ultra')
        result = {'pack': str(self.project / 'automatic-ultra-pack'), 'material_count': 3,
                  'state': 'prepared', 'host_scale': 4}
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='verified', stderr='')
        spawn.return_value = Mock(pid=123, wait=Mock(return_value=0))
        with patch('native_port.texture_pipeline.ensure_graphics_textures', return_value=result) as prepare:
            self.app.play()
            self.wait_task()
        self.assertEqual(prepare.call_args.args[1]['texture_quality'], 'ultra')
        self.assertEqual(prepare.call_args.args[1]['preset'], 'ultra')
        self.assertEqual(self.app.hd_material_count, 3)
        self.assertEqual(self.app.hd_texture_pack.get(), result['pack'])
        command = spawn.call_args.args[0]
        self.assertEqual(command[command.index('--hd-texture-pack') + 1], result['pack'])

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_cancel_during_auto_texture_preparation_never_validates_or_spawns(self, validate, spawn):
        self.experimental_folder()
        self.app.choose_preset('high')
        self.app.hd_texture_pack.set('previous-pack')
        started = threading.Event()
        def prepare(*args, cancel, **kwargs):
            started.set()
            cancel.event.wait(3)
            cancel.check()
            self.fail('Preparation was expected to be cancelled')
        with patch('native_port.texture_pipeline.ensure_graphics_textures', side_effect=prepare):
            self.app.play()
            self.assertTrue(started.wait(1))
            self.assertEqual(str(self.app.cancel_button['state']), 'normal')
            self.app.cancel_button.invoke()
            self.wait_task()
        validate.assert_not_called()
        spawn.assert_not_called()
        self.assertEqual(self.app.hd_texture_pack.get(), 'previous-pack')
        self.assertIn('CANCELLED', self.app.status.get())
        self.assertFalse(self.app.busy)

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_auto_texture_failure_preserves_selection_and_blocks_game(self, validate, spawn):
        from native_port.errors import PortError
        self.experimental_folder()
        self.app.choose_preset('high')
        self.app.hd_texture_pack.set('previous-pack')
        with patch('native_port.texture_pipeline.ensure_graphics_textures',
                   side_effect=PortError('HD_SOURCE_CHANGED', 'Origem revisada divergente')):
            self.app.play()
            self.wait_task()
        validate.assert_not_called()
        spawn.assert_not_called()
        self.assertEqual(self.app.hd_texture_pack.get(), 'previous-pack')
        self.assertIn('HD_SOURCE_CHANGED', self.app.status.get())
        self.assertIn('Origem revisada divergente', self.app.status.get())

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_low_uses_originals_without_tools_model_or_hd_argument(self, validate, spawn):
        self.experimental_folder()
        self.app.choose_preset('low')
        self.app.hd_texture_pack.set('previous-high-pack')
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='verified', stderr='')
        spawn.return_value = Mock(pid=123, wait=Mock(return_value=0))
        with patch('native_port.texture_tools.ensure_texture_tools') as helpers, \
                patch('native_port.texture_pipeline.prepare_texture_pack') as enhance:
            self.app.play()
            self.wait_task()
        helpers.assert_not_called()
        enhance.assert_not_called()
        self.assertNotIn('--hd-texture-pack', spawn.call_args.args[0])
        self.assertEqual(self.app.hd_texture_pack.get(), '')
        self.assertEqual(self.app.hd_material_count, 0)
        saved = json.loads((self.project / '.aster/config/settings.json').read_text())
        self.assertEqual(saved['hd_texture_pack'], '')

    def test_graphics_controls_switch_preset_and_experimental_target(self):
        self.app.choose_preset('ultra')
        self.assertEqual(self.app.graphics_preset.get(), 'ultra')
        self.assertIn('3840x2160', self.app.graphics_summary.get())
        self.assertEqual(self.app.preset_buttons['ultra']['style'], 'PresetOn.TButton')
        self.app.choose_target('unlimited')
        self.root.update()
        self.assertEqual(self.app.fps_target.get(), 'unlimited')
        self.assertFalse(self.app.vsync.get())
        self.assertTrue(self.app.warning_frame.winfo_ismapped())
        self.assertIn('ILIMITADO', self.app.warning_text.get())
        self.assertEqual(self.app.target_buttons['unlimited']['style'], 'PresetOn.TButton')
        self.app.choose_target('30')
        self.root.update()
        self.assertTrue(self.app.vsync.get())
        self.assertFalse(self.app.warning_frame.winfo_ismapped())

    def test_play_command_forwards_selected_preset_without_custom_overrides(self):
        folder = self.experimental_folder()
        self.app.choose_preset('high')
        command = self.app.play_command(folder)
        self.assertEqual(command[2:6], ['--shader-mode', 'async', '--vsync', 'on'])
        self.assertEqual(command[command.index('--fps-target') + 1], '30')
        self.assertEqual(command[command.index('--graphics-preset') + 1], 'high')
        self.assertNotIn('--render-scale', command)
        self.assertNotIn('--present-mode', command)

    def test_custom_graphics_command_forwards_every_override(self):
        folder = self.experimental_folder()
        self.app.choose_preset('custom')
        self.app.custom_render_scale.set(2)
        self.app.custom_msaa.set(False)
        self.app.custom_aniso.set('8x')
        self.app.custom_texture.set('Alta')
        self.app.custom_dither.set(True)
        command = self.app.play_command(folder)
        self.assertEqual(command[command.index('--render-scale') + 1], '2')
        self.assertNotIn('--msaa', command)
        self.assertEqual(str(self.app.msaa_check['state']), 'disabled')
        self.assertEqual(command[command.index('--anisotropic') + 1], '4')
        self.assertEqual(command[command.index('--texture-quality') + 1], 'high')
        self.assertEqual(command[command.index('--dither') + 1], 'on')

    def test_full_hd_with_ultra_textures_keeps_independent_custom_choices(self):
        from native_port import settings
        folder = self.experimental_folder()
        self.app.choose_preset('high')
        self.app.output_resolution.set('1920x1080')
        self.app.custom_render_scale.set(1)
        self.app.custom_texture.set('Ultra')
        self.app.custom_aniso.set('16x')
        self.app.choose_target('60')
        self.assertEqual(self.app.graphics_preset.get(), 'custom')
        self.assertTrue(self.app.save_settings(quiet=True))
        saved = settings.load(self.project)['graphics']
        self.assertEqual(saved['output_resolution'], '1920x1080')
        self.assertEqual(saved['render_scale'], 1)
        self.assertEqual(saved['texture_quality'], 'ultra')
        self.assertEqual(saved['anisotropic'], 5)
        self.assertEqual(saved['fps_target'], '60')
        command = self.app.play_command(folder)
        for option, value in [('--graphics-preset','custom'), ('--output-resolution','1920x1080'),
                              ('--render-scale','1'), ('--texture-quality','ultra'),
                              ('--anisotropic','5'), ('--fps-target','60')]:
            self.assertEqual(command[command.index(option)+1], value)
        # Higher internal resolution must also survive saving and reopening.
        self.app.custom_render_scale.set(3)
        self.assertTrue(self.app.save_settings(quiet=True))
        self.assertEqual(settings.load(self.project)['graphics']['render_scale'], 3)

    def test_antialiasing_selection_reaches_game_command_and_preset_reset(self):
        folder = self.experimental_folder()
        self.app.choose_preset('high')
        self.assertEqual(self.app.antialiasing.get(), 'FXAA')
        self.app.antialiasing.set('FXAA intenso')
        self.app._on_custom_changed()
        command = self.app.play_command(folder)
        self.assertEqual(command[command.index('--antialiasing') + 1], 'fxaa_extreme')
        self.assertEqual(command[command.index('--graphics-preset') + 1], 'custom')
        self.app.choose_preset('low')
        self.assertEqual(self.app.antialiasing.get(), 'Desligado')

    def test_unlimited_command_forces_vsync_off_and_immediate_mode(self):
        folder = self.experimental_folder()
        self.app.choose_target('unlimited')
        command = self.app.play_command(folder)
        self.assertEqual(command[command.index('--fps-target') + 1], 'unlimited')
        self.assertEqual(command[command.index('--vsync') + 1], 'off')
        self.assertEqual(command[command.index('--present-mode') + 1], 'immediate')
        self.assertFalse((self.project / '.aster/runtime').exists())

    def test_save_writes_schema_two_preferences_only(self):
        folder = self.experimental_folder()
        self.app.choose_preset('high')
        self.app.choose_target('60')
        with patch('native_port.launcher.messagebox.showerror') as showerror:
            self.assertTrue(self.app.save_settings())
        showerror.assert_not_called()
        path = self.project / '.aster/config/settings.json'
        data = json.loads(path.read_text())
        self.assertEqual(data['schema'], 2)
        self.assertEqual(data['source'], str(folder))
        self.assertEqual(data['graphics']['preset'], 'high')
        self.assertEqual(data['graphics']['fps_target'], '60')
        self.assertFalse((self.project / '.aster/runtime').exists())

    def test_play_missing_build_routes_to_generation_without_launching_game(self):
        folder = self.project / 'dump'
        folder.mkdir()
        (folder / 'default.xex').write_bytes(xex())
        self.app.source.set(str(folder))
        with patch.object(self.app, 'generate_native') as build, \
                patch('native_port.launcher.subprocess.run') as validate:
            self.app.play()
        validate.assert_not_called()
        build.assert_called_once()

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_close_during_validation_never_spawns_after_destroy(self, validate, spawn):
        self.experimental_folder()
        started, release = threading.Event(), threading.Event()
        def validation(*args, **kwargs):
            started.set()
            release.wait(2)
            return subprocess.CompletedProcess([], 0, stdout='', stderr='')
        validate.side_effect = validation
        self.app.play_experimental()
        self.assertTrue(started.wait(1))
        self.app.close()
        release.set()
        deadline = time.monotonic() + 2
        while self.app.queue.empty() and time.monotonic() < deadline:
            time.sleep(.01)
        spawn.assert_not_called()
        self.assertTrue(self.app.closed)

    @patch('native_port.launcher.subprocess.Popen')
    @patch('native_port.launcher.subprocess.run')
    def test_stop_only_terminates_own_experimental_child(self, validate, spawn):
        self.experimental_folder()
        started, stopped = threading.Event(), threading.Event()
        def wait(timeout=None):
            started.set()
            stopped.wait(2)
            return -15
        child = Mock(pid=123, wait=Mock(side_effect=wait), terminate=Mock(side_effect=stopped.set))
        spawn.return_value = child
        validate.return_value = subprocess.CompletedProcess([], 0, stdout='', stderr='')
        self.app.play_experimental()
        self.assertTrue(started.wait(1))
        self.assertEqual(str(self.app.experimental_button['state']), 'disabled')
        self.app.play_experimental()
        self.assertEqual(spawn.call_count, 1)
        self.app.stop_experimental()
        self.wait_task()
        child.terminate.assert_called_once()
        self.assertIn('CANCELLED', self.app.status.get())

    @patch('native_port.launcher.threading.Thread')
    def test_close_sends_terminate_before_starting_non_daemon_cleanup(self, thread):
        child = Mock()
        child.wait.side_effect = [subprocess.TimeoutExpired('owned child', 3), -9]
        self.app.experimental_process = child
        def create_thread(*args, **kwargs):
            child.terminate.assert_called_once()
            self.assertFalse(kwargs['daemon'])
            cleanup = Mock()
            cleanup.start.side_effect = kwargs['target']
            return cleanup
        thread.side_effect = create_thread
        self.app.close()
        child.wait.assert_any_call(timeout=3)
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)
        self.assertTrue(self.app.closed)

    @patch('native_port.launcher.threading.Thread')
    def test_close_tolerates_child_already_gone(self, thread):
        child = Mock(terminate=Mock(side_effect=ProcessLookupError))
        self.app.experimental_process = child
        self.app.close()
        thread.assert_not_called()
        self.assertTrue(self.app.closed)
