import tkinter as tk
import unittest
from native_port import controls
from native_port.controls_ui import ControlsPanel
from native_port.errors import PortError


class ControlsPanelTests(unittest.TestCase):
    def setUp(self):
        try:self.root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        self.root.withdraw()

    def tearDown(self):
        if hasattr(self,'root'):self.root.destroy()

    def test_ui_roundtrips_separate_keyboard_and_pad_choices(self):
        panel=ControlsPanel(self.root)
        self.assertEqual(panel.get_settings(),controls.defaults())
        panel.keyboard['a'].set('Ctrl+q,Space')
        panel.gamepad['a'].set(controls.PAD_LABELS['b']);panel.gamepad['b'].set(controls.PAD_LABELS['a'])
        panel.layout.set('PlayStation');panel.axes['swap_sticks'].set(True);panel.deadzone.set(12)
        value=panel.get_settings()
        self.assertEqual(value['keyboard']['a'],'Ctrl+Q,Space')
        self.assertEqual(value['gamepad']['bindings']['a'],'b')
        self.assertTrue(value['gamepad']['swap_sticks'])
        self.assertEqual(value['layout'],'playstation')
        panel.set_settings(controls.defaults());self.assertEqual(panel.get_settings(),controls.defaults())
        panel.destroy()

    def test_invalid_numeric_field_surfaces_validation_error(self):
        panel=ControlsPanel(self.root)
        panel.mouse_sensitivity.set('invalid')
        with self.assertRaises(PortError):panel.get_settings()
        panel.destroy()

if __name__=='__main__':unittest.main()
