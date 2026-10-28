"""CPU contracts for optional sampling diagnostics and conservative log parsing."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from native_port.effects_diagnostics import ATLAS_XXH3, parse_effects_metadata

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'integrations/rexglue/patches/0018-effects-sampling-diagnostics.patch'


def fixture():
    sampler = dict.fromkeys(('host_value', 'instruction_mag', 'instruction_min', 'instruction_mip',
        'instruction_aniso', 'aniso', 'mip_min_level', 'mip_base_map', 'clamp_x', 'clamp_y',
        'clamp_z', 'border', 'mag_linear', 'min_linear', 'mip_linear'), 0)
    sampler.update(stage=1, fetch=0)
    registers = dict.fromkeys(('RB_COLORCONTROL', 'RB_ALPHA_REF', 'RB_SURFACE_INFO',
        'RB_BLENDCONTROL0', 'RB_BLENDCONTROL1', 'RB_BLENDCONTROL2', 'RB_BLENDCONTROL3',
        'PA_CL_VPORT_XSCALE', 'PA_CL_VPORT_YSCALE', 'PA_SC_WINDOW_SCISSOR_TL',
        'PA_SC_WINDOW_SCISSOR_BR'), 0)
    registers['RB_COLORCONTROL'] = 0x18
    registers['RB_SURFACE_INFO'] = (2 << 16) | 1280
    return {'schema': 1, 'source_raw_xxh3_128': ATLAS_XXH3, 'snapshot_bytes': 2162688,
        'gpu_written_pages': False, 'actual_rt_size': None, 'actual_sampled_lod': None,
        'draw_completion': 'unknown', 'state': {'backend': 'vulkan', 'vs_hash': 123,
            'ps_hash': 456, 'fetch': 0, 'base_page': 50554, 'host_resource_id': 1,
            'scale_x': 1, 'scale_y': 1, 'samplers': [sampler], 'fetch_raw': [0]*6,
            'guest_registers_raw': registers, 'alpha_test_enable': 1, 'alpha_func': 0,
            'alpha_to_mask_enable': 1, 'guest_msaa_samples_enum': 2, 'guest_surface_pitch': 1280}}


def line(record):
    return '[gpu] ASTER_EFFECTS_META ' + json.dumps(record)


class EffectsParserTests(unittest.TestCase):
    def test_preserves_uncertainty_and_decodes_a2c(self):
        records = parse_effects_metadata(['unrelated line', line(fixture())])
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]['actual_rt_size'])
        self.assertEqual(records[0]['state']['alpha_to_mask_enable'], 1)
        # Pitch cannot establish render-target extent.
        self.assertEqual(records[0]['state']['guest_surface_pitch'], 1280)

    def test_unrelated_or_gpu_written_source_and_claimed_gpu_result_rejected(self):
        for field, value in (('source_raw_xxh3_128', '0'*32), ('gpu_written_pages', True),
                             ('actual_rt_size', [1280, 720]), ('actual_sampled_lod', 0),
                             ('draw_completion', 'complete'), ('snapshot_bytes', 1024)):
            record = fixture(); record[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                parse_effects_metadata([line(record)])

    def test_contradictory_alpha_bits_or_unrelated_sampler_rejected(self):
        record = fixture(); record['state']['alpha_to_mask_enable'] = 0
        with self.assertRaises(ValueError): parse_effects_metadata([line(record)])
        record = fixture(); record['state']['samplers'][0]['fetch'] = 1
        with self.assertRaises(ValueError): parse_effects_metadata([line(record)])

    def test_duplicate_records_do_not_consume_budget_but_unique_33_rejected(self):
        self.assertEqual(len(parse_effects_metadata([line(fixture())]*1000)), 1)
        records=[]
        for i in range(33):
            record=fixture(); record['state']['ps_hash']=i; records.append(line(record))
        self.assertEqual(len(parse_effects_metadata(records[:32])), 32)
        with self.assertRaises(ValueError): parse_effects_metadata(records)

    def test_optional_pixel_constant_bits_preserve_nonfinite_values_and_old_logs(self):
        record = fixture()
        bits = [0x7fc00001, 0xff800000, 0x3f000000, 0x80000000]
        record['state']['pixel_float_constant_255_raw'] = bits
        self.assertEqual(parse_effects_metadata([line(record)])[0]['state']['pixel_float_constant_255_raw'], bits)
        self.assertEqual(len(parse_effects_metadata([line(fixture())])), 1)
        for value in (None, [], [0]*3, [0]*5, [0, 0, True, 0], [0, -1, 0, 0], [0, 1 << 32, 0, 0]):
            record['state']['pixel_float_constant_255_raw'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_effects_metadata([line(record)])

    def test_partial_and_oversize_json_rejected(self):
        for payload in ('{', '[]', 'x'*65537):
            with self.subTest(size=len(payload)), self.assertRaises(ValueError):
                parse_effects_metadata(['ASTER_EFFECTS_META '+payload])


class EffectsBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('c++')
        if not compiler: raise unittest.SkipTest('C++ compiler unavailable')
        text=PATCH.read_text()
        header=text.split('+++ b/include/rex/graphics/pipeline/texture/effects_diagnostics.h\n',1)[1].split('--- a/',1)[0]
        added='\n'.join(row[1:] for row in header.splitlines() if row.startswith('+'))+'\n'
        cls.temp=tempfile.TemporaryDirectory(prefix='aster-effects-contract-')
        cls.addClassCleanup(cls.temp.cleanup)
        folder=Path(cls.temp.name); (folder/'effects.h').write_text(added)
        (folder/'contract.cpp').write_text(r'''
#include "effects.h"
#include <atomic>
#include <thread>
#include <vector>
using namespace rex::graphics::effects_diagnostics;
int main() {
  for (const char* v : {static_cast<const char*>(nullptr),"","0","true","01","1 ","11","-1"})
    if (IsEnabledValue(v)) return 1;
  if (!IsEnabledValue("1")) return 2;
  StateBudget duplicate;
  if (!duplicate.Reserve("same")) return 3;
  for (int n=0;n<10000;++n) if (duplicate.Reserve("same")) return 4;
  if (duplicate.Full()) return 5;
  StateBudget budget;
  std::atomic<unsigned> snapshots{0};
  std::vector<std::thread> threads;
  for (unsigned t=0;t<8;++t) threads.emplace_back([&,t] {
    for (unsigned n=0;n<1000;++n)
      if (budget.Reserve(std::to_string(t)+":"+std::to_string(n))) ++snapshots;
  });
  for (auto& t:threads) t.join();
  if (!budget.Full() || snapshots != 32 || budget.Reserve("extra")) return 6;
  return 0;
}
''')
        cls.binary=folder/'contract'
        result=subprocess.run([compiler,'-std=c++17','-pthread',str(folder/'contract.cpp'),'-o',str(cls.binary)],
            capture_output=True,text=True,timeout=60)
        if result.returncode: raise AssertionError(result.stderr)

    def test_exact_env_opt_in_duplicates_failed_attempt_budget_and_concurrent_cap(self):
        result=subprocess.run([str(self.binary)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
