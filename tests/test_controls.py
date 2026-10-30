from pathlib import Path
import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from native_port import controls
from native_port.errors import PortError
from native_port.native_cache import apply_patch_exact


class ControlsTests(unittest.TestCase):
    def test_defaults_emit_real_sdk_keybinds_and_identity_pad(self):
        config = controls.defaults()
        self.assertEqual(config, controls.validate(config))
        args = controls.cvar_arguments(config)
        self.assertIn('--keybind_a=Semicolon,Space', args)
        self.assertIn('--keybind_back=Z,Tab', args)
        self.assertIn('--aster_pad_map=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15', args)
        self.assertIn('--aster_controller_layout=auto', args)
        self.assertEqual(len(args), len(set(x.split('=')[0] for x in args)))
        self.assertEqual(controls.validate(json.loads(json.dumps(config))), config)

    def test_keybinds_validate_sdk_names_and_preserve_alternatives(self):
        self.assertEqual(controls.normalize_keybind('Ctrl+Shift+l,Space,Space'), 'Shift+Ctrl+L,Space')
        for value in ['Shift', 'Ctrl', 'Shift++Q', 'Shift+Shift+Q', 'Space,', 'x;rm', 'É', 'Enter', 'Ctrl+Bogus']:
            with self.subTest(value=value), self.assertRaises(PortError): controls.normalize_keybind(value)
        self.assertEqual(controls.normalize_keybind('Control+q'), 'Ctrl+Q')
        self.assertEqual(controls.normalize_keybind('LMB'), 'LMB')

    def test_configs_reject_type_errors_unknown_actions_and_missing_navigation(self):
        for field,value in [('schema',2),('layout',[]),('layout','ps5'),('mouse_look',1),('mouse_sensitivity',True),('mouse_sensitivity',float('nan')),('mouse_sensitivity',10**1000),('keyboard',{})]:
            config=controls.defaults();config[field]=value
            with self.subTest(field=field,value=str(value)[:40]), self.assertRaises(PortError): controls.validate(config)
        for kind in ['keyboard','gamepad']:
            for action in ['a','b','back','start']:
                config=controls.defaults()
                if kind=='keyboard':config['keyboard'][action]=''
                else:config['gamepad']['bindings'][action]='none'
                with self.subTest(kind=kind,action=action), self.assertRaises(PortError):controls.validate(config)

    def test_pad_swaps_are_simultaneous_and_never_change_keyboard_mapping(self):
        config=controls.defaults();config['gamepad']['bindings'].update(a='b',b='a')
        config['layout']='playstation';config['gamepad'].update(swap_sticks=True,invert_ry=True,deadzone=15)
        args=controls.cvar_arguments(config)
        self.assertIn('--aster_pad_map=1,0,2,3,4,5,6,7,8,9,10,11,12,13,14,15',args)
        self.assertIn('--keybind_a=Semicolon,Space',args)
        self.assertIn('--aster_pad_axes=1,0,0,0,1',args)
        self.assertIn('--aster_pad_deadzone=15',args)
        config['gamepad']['bindings']['b']='b'
        with self.assertRaises(PortError):controls.validate(config)

    def test_cpp_shipped_map_preserves_identity_and_remaps_state_and_keystrokes(self):
        compiler=shutil.which('clang++') or shutil.which('g++')
        if not compiler:self.skipTest('C++ compiler unavailable')
        root=Path(__file__).resolve().parents[1]
        patch=(root/'integrations/rexglue/patches/0035-configurable-controls.patch').read_text()
        blocks=patch.split('--- ')
        wanted=''.join('--- '+block for block in blocks[1:] if block.startswith('a/include/rex/input/device.h\n') or block.startswith('/dev/null\n+++ b/include/rex/input/controller_remap.h\n'))
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);header=folder/'include/rex/input/device.h';header.parent.mkdir(parents=True)
            header.write_bytes((root/'tests/fixtures/controller_device_pinned.h').read_bytes())
            apply_patch_exact(folder,wanted)
            source=folder/'test.cpp';source.write_text(r'''
#include <rex/input/controller_remap.h>
#include <cassert>
#include <cstring>
using namespace rex::input::controller_remap;
int main() {
 Config config;
 State state{0xffff,17,201,-32768,32767,412,-510};
 auto same=Apply(state,config);
 assert(same.buttons==state.buttons && same.lt==17 && same.rt==201);
 assert(same.lx==-32768 && same.ly==32767 && same.rx==412 && same.ry==-510);
 for(auto key:kKeys) assert(RemapKeystroke(key,config)==key);
 assert(RemapKeystroke(0x1234,config)==0x1234);
 config.map[0]=1;config.map[1]=0;
 state={0x1000,0,0,0,0,0,0};auto swapped=Apply(state,config);
 assert(swapped.buttons==0x2000 && state.buttons==0x1000);
 assert(RemapKeystroke(0x5800,config)==0x5801 && RemapKeystroke(0x5801,config)==0x5800);
 config=Config{};config.map[2]=kNone;
 state.buttons=0x4000;assert(Apply(state,config).buttons==0);assert(RemapKeystroke(0x5802,config)==0);
 config=Config{};config.map[0]=6;config.map[6]=0;
 state={0x1000,30,0,0,0,0,0};auto trigger=Apply(state,config);
 assert(trigger.buttons==0 && trigger.lt==255);
 state.lt=31;assert(Apply(state,config).buttons==0x1000);
 state.lt=0;state.buttons=0;assert(Apply(state,config).lt==0);
 config=Config{};config.map[6]=7;config.map[7]=6;
 state.lt=17;state.rt=201;trigger=Apply(state,config);assert(trigger.lt==201 && trigger.rt==17);
 config=Config{};config.axes={true,true,false,false,true};
 state={0,0,0,-32768,12,42,-510};auto axes=Apply(state,config);
 assert(axes.lx==-42 && axes.ly==-510 && axes.rx==-32768 && axes.ry==-12);
 assert(RemapKeystroke(0x5820,config)==0x5831); // left-up -> right-down
 assert(RemapKeystroke(0x5832,config)==0x5823); // right-right -> left-left
 assert(Axis(-32768,true,0)==32767);
 assert(Axis(2000,false,10)==0 && Axis(32767,false,30)==32767);
 Config parsed;assert(Parse("1,0,2,3,4,5,6,7,8,9,10,11,12,13,14,15","1,0,0,1,0",15,parsed));
 assert(parsed.map[0]==1 && parsed.axes[0] && parsed.axes[3] && parsed.deadzone==15);
 for(auto bad:{"0,0,2,3,4,5,6,7,8,9,10,11,12,13,14,15","16,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15","0,1","0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,","-1,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15"})
   assert(!Parse(bad,"0,0,0,0,0",0,parsed));
 assert(!Parse("0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15","0,0,2,0,0",0,parsed));
}
''')
            binary=folder/'test.exe'
            result=subprocess.run([compiler,'-std=c++20','-Wall','-Wextra','-I',str(folder/'include'),str(source),'-o',str(binary)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
