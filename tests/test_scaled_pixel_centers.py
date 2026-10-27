"""Run exact patched SDK scale blocks against a pixel-copy round-trip oracle.

The lightweight assembler records arithmetic emitted by each real backend block;
it does not replace the block with a Python formula. This catches the one-host-
pixel shift that overwrote correct prepass depth at internal 2x/3x.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'integrations/rexglue/patches/0024-scaled-pixel-parameter-centers.patch'
FIXTURE = ROOT / 'tests/fixtures/scaled_pixel_centers_pinned.inc'


def patched_fixture():
    source = FIXTURE.read_text()
    chunks = re.split(r'^@@[^\n]*\n', PATCH.read_text(), flags=re.MULTILINE)[1:]
    if len(chunks) != 3:
        raise AssertionError('Expected X, Y and DXBC complete hunks')
    for chunk in chunks:
        lines = []
        for line in chunk.splitlines(keepends=True):
            if line.startswith(('--- ', '+++ ')):
                break
            lines.append(line)
        old = ''.join(line[1:] for line in lines if line[:1] in (' ', '-'))
        new = ''.join(line[1:] for line in lines if line[:1] in (' ', '+'))
        if source.count(old) != 1:
            raise AssertionError('Full hunk must match exact pinned source once')
        source = source.replace(old, new, 1)
    return source


HARNESS = r'''
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>
namespace spv { enum {OpFMul, OpFAdd}; }
struct Builder {
  float makeFloatConstant(float f) {return f;}
  float createNoContractionBinOp(int op, int, float a, float b) {
    return op == spv::OpFMul ? a*b : a+b;
  }
};
std::array<float,2> spirv(float x, float y, unsigned sx, unsigned sy) {
  unsigned draw_resolution_scale_x_=sx, draw_resolution_scale_y_=sy;
  float param_gen_x=std::floor(x), param_gen_y=std::floor(y);
  Builder b; auto* builder_=&b; int type_float_=0;
  SPIRV_X
  SPIRV_Y
  return {param_gen_x,param_gen_y};
}
namespace dxbc {
struct Dest {unsigned mask; static Dest R(unsigned, unsigned m) {return {m};}};
struct Src {
  bool reg; std::array<float,4> v;
  static Src R(unsigned) {return {true,{}};}
  static Src LF(float x,float y,float z,float w) {return {false,{x,y,z,w}};}
};
}
struct Assembler {
 std::array<float,4> reg;
 void OpMul(dxbc::Dest d,dxbc::Src,dxbc::Src s) {
  for(unsigned i=0;i<4;++i)if(d.mask&(1u<<i))reg[i]*=s.v[i];
 }
 void OpAdd(dxbc::Dest d,dxbc::Src,dxbc::Src s) {
  for(unsigned i=0;i<4;++i)if(d.mask&(1u<<i))reg[i]+=s.v[i];
 }
};
std::array<float,2> dxbc_position(float x,float y,unsigned sx,unsigned sy) {
 unsigned draw_resolution_scale_x_=sx,draw_resolution_scale_y_=sy,param_gen_temp=0;
 Assembler a_{{std::floor(x),std::floor(y),17,29}};
 DXBC
 if(a_.reg[2]!=17 || a_.reg[3]!=29)throw std::runtime_error("ZW changed");
 return {a_.reg[0],a_.reg[1]};
}
int main() {
 for(unsigned sx: {1,2,3})for(unsigned sy: {1,2,3})
 for(unsigned x: {0,1,2,3,78,79,80,81,1278,1279,2559})
 for(unsigned y: {0,1,2,3,899,900,901,1439})
 for(float sample: {0.125f,0.5f,0.875f}) {
  auto a=spirv(x+sample,y+sample,sx,sy);
  auto b=dxbc_position(x+sample,y+sample,sx,sy);
  unsigned p[2]={x,y},scale[2]={sx,sy};
  for(unsigned i=0;i<2;++i) {
   if(std::abs(a[i]-b[i])>0.0001f)throw std::runtime_error("backend mismatch");
   // The game's +0.5 then normalized texture fetch must return this host
   // pixel center, not its neighbour. Check before sign-bit packing/FAbs.
   float copied=(a[i]+0.5f)*scale[i];
   float expected=PATCHED ? p[i]+0.5f : p[i]+0.5f*scale[i];
   if(std::abs(copied-expected)>0.0005f)throw std::runtime_error("pixel center shifted");
   if(scale[i]==1 && a[i]!=float(p[i]))throw std::runtime_error("1x changed");
  }
 }
}
'''


def block(source, index, start, stop):
    hunk = source.split('// BEGIN HUNK'+str(index)+'\n', 1)[1].split('// END HUNK', 1)[0]
    return hunk[hunk.index(start):hunk.index(stop, hunk.index(start))]


class ScaledPixelCenterTests(unittest.TestCase):
    def test_actual_spirv_and_dxbc_blocks_preserve_copy_pixel_centers(self):
        compiler = shutil.which('c++') or shutil.which('clang++')
        if not compiler:
            self.skipTest('C++ compiler required for actual SDK emitter-block regression')
        for label, source in [('original', FIXTURE.read_text()), ('patched', patched_fixture())]:
            cpp = HARNESS
            for index, axis in enumerate('xy'):
                cpp = cpp.replace('SPIRV_'+axis.upper(), block(source, index,
                    '    if (draw_resolution_scale_'+axis+'_ > 1)',
                    '    param_gen_'+axis+' = builder_->createUnaryBuiltinCall'))
            cpp = cpp.replace('DXBC', block(source, 2, '    uint32_t resolution_scaled_axes =',
                                             '    if (shader_modification.pixel.param_gen_point)'))
            cpp = cpp.replace('PATCHED', 'true' if label == 'patched' else 'false')
            with self.subTest(variant=label), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary)
                (path/'test.cpp').write_text(cpp)
                built = subprocess.run([compiler, '-std=c++17', str(path/'test.cpp'), '-o', str(path/'test')],
                                       capture_output=True, text=True, timeout=30)
                self.assertEqual(built.returncode, 0, built.stderr)
                run = subprocess.run([str(path/'test')], capture_output=True, text=True, timeout=10)
                self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
