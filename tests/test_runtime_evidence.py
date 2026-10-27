from pathlib import Path
import tempfile
import unittest

from native_port.runtime_evidence import read_runtime_logs, summarize_runtime_log


class RuntimeEvidenceTests(unittest.TestCase):
    def test_presentation_and_clean_exit_do_not_certify_gameplay(self):
        result = summarize_runtime_log('XELOG_GPU PRESENT\nExecution complete\n')
        self.assertFalse(result['ready'])
        self.assertFalse(result['gameplay_verified'])
        self.assertEqual(result['present_calls_observed'], 1)

    def test_access_violations_are_failures_even_with_clean_shutdown(self):
        line = 'Unhandled guest access violation: read of guest 0x70250000'
        result = summarize_runtime_log('[error] ' + line + '\n' + line + '\nExecution complete\n')
        self.assertEqual(result['fatal_messages'], [line])
        self.assertTrue(result['execution_complete_logged'])
        self.assertFalse(result['gameplay_verified'])

    def test_rotated_logs_preserve_old_failures_and_chronology(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            (path / 'runtime.10.log').write_text('[FATAL] old failure\n')
            (path / 'runtime.2.log').write_text('XELOG_GPU PRESENT\n')
            (path / 'runtime.1.log').write_text('XELOG_GPU PRESENT\n')
            (path / 'runtime.log').write_text('Execution complete\n')
            (path / 'runtime.debug.log').write_text('unrelated\n')
            text, files = read_runtime_logs(path)
            self.assertEqual(files, ['runtime.10.log', 'runtime.2.log', 'runtime.1.log', 'runtime.log'])
            result = summarize_runtime_log(text)
            self.assertEqual(result['fatal_messages'], ['[FATAL] old failure'])
            self.assertEqual(result['present_calls_observed'], 2)

    def test_clean_exit_and_presents_do_not_hide_renderer_failures(self):
        lines = [
            '[error] [gpu] vkCreateGraphicsPipelines failed (result=-2)',
            '[error] [gpu] Failed to translate queued pixel shader',
            '[error] [gpu] Failed to create graphics pipeline with VS AABB, PS CCDD',
            '[error] [gpu] D3D12 device removed: DEVICE_REMOVED',
        ]
        result = summarize_runtime_log('\n'.join(lines + lines + ['XELOG_GPU PRESENT', 'Execution complete']))
        self.assertEqual(len(result['rendering_errors']), 4)
        self.assertEqual(result['fatal_messages'], [])
        self.assertTrue(result['execution_complete_logged'])
        self.assertFalse(result['ready'])
        self.assertFalse(result['gameplay_verified'])

    def test_recoverable_cache_warnings_and_optional_file_api_are_not_render_failures(self):
        text = ('[warning] VulkanPipelineCache: Ignoring invalid/incompatible driver cache\n'
                '[warning] Failed to initialize D3D12 resolve-downscale readback pipeline\n'
                '[error] [krnl] NtQueryInformationFile(XFileXctdCompressionInformation) unimplemented\n')
        self.assertEqual(summarize_runtime_log(text)['rendering_errors'], [])


if __name__ == '__main__':
    unittest.main()
