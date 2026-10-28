from copy import deepcopy
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import xxhash

from native_port.errors import PortError
from native_port import shader_prepare as prepare
from native_port.locking import lock_session
from native_port.workspace import Workspace

ROOT = Path(__file__).resolve().parents[1]


def synthetic():
    # A made-up vertex-fetch instruction; no data from the game.
    bank = struct.pack('>III', 1 << 19, 0, 0)
    modified = struct.pack('>III', 1 << 19, 38 << 16, 6)
    digest = xxhash.xxh3_64_hexdigest(modified)
    profile = {'decoded_size': 12, 'decoded_sha256': hashlib.sha256(bank).hexdigest(),
               'shaders': [{'source_offset': 0, 'byte_count': 12, 'stage': 0,
                            'source_sha256': hashlib.sha256(bank).hexdigest(), 'hash': digest,
                            'vertex_layout': [{'instruction_byte_offset': 0,
                                               'fields': {'format': 38, 'stride': 6}}]}]}
    return bank, profile


class ShaderPreparationTests(unittest.TestCase):
    def test_preparation_holds_the_game_lock_and_uses_the_existing_decoded_bank(self):
        bank, profile = synthetic()
        pixel = b'fake pixel!!'
        profile['shaders'].append({'source_offset': len(bank), 'byte_count': len(pixel),
            'stage': 1, 'source_sha256': hashlib.sha256(pixel).hexdigest(),
            'hash': xxhash.xxh3_64_hexdigest(pixel), 'vertex_layout': []})
        bank += pixel
        profile.update(decoded_size=len(bank), decoded_sha256=hashlib.sha256(bank).hexdigest(),
            sdk_revision='fixture-sdk', source_relative='shaders.pak',
            source_xex_sha256=hashlib.sha256(b'fake xex').hexdigest(),
            source_sha256=hashlib.sha256(b'fake container').hexdigest(), scope='Synthetic fixture')
        pipeline = deepcopy(prepare.load_profile(ROOT)['pipelines'][0])
        pipeline.update(vertex_shader=profile['shaders'][0]['hash'], pixel_shader=profile['shaders'][1]['hash'])
        profile['pipelines'] = [pipeline]
        for renderer in ('vulkan-fsi', 'd3d12-rov'):
            with self.subTest(renderer=renderer), tempfile.TemporaryDirectory() as temp:
                temp = Path(temp)
                dump = temp / 'dump'; dump.mkdir()
                (dump / 'default.xex').write_bytes(b'fake xex')
                (dump / 'shaders.pak').write_bytes(b'fake container')
                runtime = temp / 'runtime'; runtime.mkdir()
                work = Workspace(temp / 'work', temp)
                decoded = work.path('shaders/decoded/' + profile['decoded_sha256'] + '.bin')
                decoded.parent.mkdir(parents=True); decoded.write_bytes(bank)
                installation = {'renderer': renderer, 'recipe': {'sdk_spatial': {'revision': 'fixture-sdk'}}}
                with patch.object(prepare, 'load_profile', return_value=profile), \
                        patch('native_port.texture_tools.ensure_texture_tools') as tools:
                    lock = lock_session(runtime / 'play.lock')
                    try:
                        with self.assertRaises(PortError):
                            prepare.prepare_game_shaders(dump, runtime, ROOT, work, installation)
                        self.assertFalse((runtime / 'cache').exists())
                    finally:
                        os.close(lock)
                    result = prepare.prepare_game_shaders(dump, runtime, ROOT, work, installation)
                    self.assertEqual(result['pipelines_added'], 1 if renderer == 'vulkan-fsi' else 2)
                    again = prepare.prepare_game_shaders(dump, runtime, ROOT, work, installation)
                    self.assertEqual(again['shader_bytes_added'], 0)
                    self.assertEqual(again['pipelines_added'], 0)
                    tools.assert_not_called()
                    self.assertEqual((dump / 'default.xex').read_bytes(), b'fake xex')
                    self.assertEqual((dump / 'shaders.pak').read_bytes(), b'fake container')

    def test_reconstruction_is_bound_to_original_and_result_and_only_edits_fetch_operands(self):
        bank, profile = synthetic()
        records = prepare.reconstruct_shaders(bank, profile)
        self.assertEqual(len(records), 1)
        self.assertEqual(next(iter(records.values()))[12:], struct.pack('>III', 1 << 19, 38 << 16, 6))
        for mutate in ('source', 'output', 'opcode', 'range', 'pixel', 'offset'):
            data = deepcopy(profile)
            shader = data['shaders'][0]
            if mutate == 'source': data['decoded_sha256'] = '0' * 64
            elif mutate == 'output': shader['hash'] = '0' * 16
            elif mutate == 'opcode': shader['vertex_layout'][0]['fields']['opcode'] = 1
            elif mutate == 'range': shader['vertex_layout'][0]['fields']['stride'] = 256
            elif mutate == 'pixel': shader['stage'] = 1
            elif mutate == 'offset': shader['vertex_layout'][0]['instruction_byte_offset'] = 12
            with self.subTest(mutate=mutate), self.assertRaises(PortError):
                prepare.reconstruct_shaders(bank, data)

    def test_merge_is_additive_idempotent_and_preserves_unknown_entries_and_backup(self):
        bank, profile = synthetic()
        shaders = prepare.reconstruct_shaders(bank, profile)
        unknown = b'unknown synthetic shader'
        h = xxhash.xxh3_64_intdigest(unknown)
        old = prepare.SHADER_HEADER + struct.pack('<QI', h, len(unknown) // 4) + unknown
        profile = prepare.load_profile(ROOT)
        for renderer in ('vulkan-fsi', 'd3d12-rov'):
            with self.subTest(renderer=renderer), tempfile.TemporaryDirectory() as temp:
                temp = Path(temp)
                target = temp / '575207E9.xsh'
                target.write_bytes(old)
                pipelines = prepare.pipeline_records(profile, renderer)
                first = prepare.merge_cache(temp, shaders, pipelines, renderer)
                self.assertEqual(first['pipelines_added'], 2 if renderer == 'vulkan-fsi' else 4)
                self.assertTrue(target.read_bytes().startswith(old))
                backup = target.with_name(target.name + '.before-prewarm-' + hashlib.sha256(old).hexdigest())
                self.assertEqual(backup.read_bytes(), old)
                identities = {p.name: (p.stat().st_ino, p.read_bytes()) for p in temp.iterdir()}
                second = prepare.merge_cache(temp, shaders, pipelines, renderer)
                self.assertEqual(second, {'shader_bytes_added': 0, 'pipelines_added': 0})
                self.assertEqual(identities, {p.name: (p.stat().st_ino, p.read_bytes()) for p in temp.iterdir()})

    def test_invalid_pipeline_cache_does_not_partially_publish_shaders(self):
        bank, profile = synthetic()
        shaders = prepare.reconstruct_shaders(bank, profile)
        for invalid in (b'old version', prepare.VK_HEADER + bytes(66), prepare.VK_HEADER + b'partial'):
            with tempfile.TemporaryDirectory() as temp:
                temp = Path(temp)
                pipeline = temp / '575207E9.fsi.vk.xpso'
                pipeline.write_bytes(invalid)
                with self.assertRaises(PortError):
                    prepare.merge_cache(temp, shaders, {}, 'vulkan-fsi')
                self.assertEqual(pipeline.read_bytes(), invalid)
                self.assertFalse((temp / '575207E9.xsh').exists())

    @unittest.skipIf(os.name == 'nt', 'Native symlink creation may require administrator privileges')
    def test_cache_link_is_rejected_without_touching_target(self):
        bank, profile = synthetic()
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            target = temp / 'other'; target.write_bytes(b'unchanged')
            (temp / '575207E9.xsh').symlink_to(target)
            with self.assertRaises(PortError):
                prepare.merge_cache(temp, prepare.reconstruct_shaders(bank, profile), {}, 'vulkan-fsi')
            self.assertEqual(target.read_bytes(), b'unchanged')

    def test_pipeline_serialization_matches_pinned_native_cpp_types(self):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        fixture = (ROOT / 'tests/fixtures/shader_prewarm_layout_pinned.inc').read_text()
        stub = r'''
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <algorithm>
#define _REXPACKEDSCOPE(body) _Pragma("pack(push, 1)") body; _Pragma("pack(pop)")
#define REXPACKEDSTRUCT(name,value) _REXPACKEDSCOPE(struct name value)
#define static_assert_size(type,size) static_assert(sizeof(type)==size)
uint64_t XXH3_64bits(const void*,size_t){return 0;}
namespace xenos {
enum class BlendOp:uint32_t{};enum class CompareFunction:uint32_t{};
enum class StencilOp:uint32_t{};enum class TessellationMode:uint32_t{};
enum class MsaaSamples:uint32_t{};enum class DepthRenderTargetFormat:uint32_t{};
enum class ColorRenderTargetFormat:uint32_t{};
constexpr uint32_t kMaxColorRenderTargets=4,kMaxInterpolators=16;
}
struct VulkanRenderTargetCache{struct RenderPassKey{uint32_t key=0;};};
struct Shader {enum class HostVertexShaderType:uint32_t{};
static constexpr uint32_t kHostVertexShaderTypeBitCount=4;};
'''
        main = r'''
int main(){
 uint64_t vs[2]={0x3d5a82b5b890b037ull,0x9a62e744807f7a19ull};
 uint64_t ps[2]={0x887f179dac6428ddull,0x36c31299f9995cedull};
 for(int i=0;i<2;++i){
  SpirvShaderTranslator::Modification vm,pm;vm.vertex.interpolator_mask=i?511:1;
  pm.pixel.interpolator_mask=i?511:1;
  pm.pixel.param_gen_enable=i;pm.pixel.param_gen_interpolator=i?9:0;
  VK::PipelineDescription v;v.vertex_shader_hash=vs[i];v.pixel_shader_hash=ps[i];
  v.vertex_shader_modification=vm.value;v.pixel_shader_modification=pm.value;
  v.primitive_topology=static_cast<VK::PipelinePrimitiveTopology>(i?3:4);
#ifndef _WIN32
  fwrite(&v,1,sizeof(v),stdout);
#endif
  DxbcShaderTranslator::Modification dvm,dpm;dvm.vertex.interpolator_mask=i?511:1;
  dpm.pixel.interpolator_mask=i?511:1;
  dpm.pixel.param_gen_enable=i;dpm.pixel.param_gen_interpolator=i?9:0;
  for(uint32_t samples:{0u,2u}){
   DX::PipelineDescription d{};d.vertex_shader_hash=vs[i];d.pixel_shader_hash=ps[i];
   d.vertex_shader_modification=dvm.value;d.pixel_shader_modification=dpm.value;
   d.primitive_topology_type_or_tessellation_mode=2;
   d.front_counter_clockwise=1;d.depth_clip=1;
   d.host_msaa_samples=static_cast<xenos::MsaaSamples>(samples);
   fwrite(&d,1,sizeof(d),stdout);
  }
 }
}
'''
        profile = prepare.load_profile(ROOT)
        vk = list(prepare.pipeline_records(profile, 'vulkan-fsi').values())
        dx = list(prepare.pipeline_records(profile, 'd3d12-rov').values())
        expected = b''.join((vk[i][8:] if os.name != 'nt' else b'') +
                            dx[2*i][8:] + dx[2*i+1][8:] for i in range(2))
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            source, binary = temp / 'layout.cpp', temp / 'layout.exe'
            source.write_text(stub + fixture + main)
            result = subprocess.run([compiler, '-std=c++17', str(source), '-o', str(binary)],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            result = subprocess.run([str(binary)], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            self.assertEqual(result.stdout, expected)
