"""CPU-only tests of patched HD loader retention; no SDK build or game assets."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from native_port.native_cache import apply_patch_exact
from native_port.spatial_sdk import normalized_patch

ROOT = Path(__file__).resolve().parents[1]
HEADER = 'include/rex/graphics/pipeline/texture/hd_override.h'


def reconstructed_header(folder):
    """Reconstruct the actual reviewed header solely from public patch inputs."""
    names = ('0006-reviewed-hd-texture-override.patch', '0009-multi-material-hd-pack.patch',
             '0011-hd-texture-scales.patch', '0012-campaign-texture-library.patch',
             '0013-windows-hd-library-path.patch', '0016-reviewed-ui-alpha-atlas.patch',
             '0030-ui-uncompressed-coverage.patch', '0034-bounded-hd-source-cache.patch')
    for name in names:
        section = normalized_patch((ROOT / 'integrations/rexglue/patches' / name).read_text())[HEADER]
        apply_patch_exact(folder, '\n'.join(section) + '\n')
    return (folder / HEADER).read_text()


class HDSourceCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            raise unittest.SkipTest('C++ compiler unavailable; source-retention contract not executed')
        cls.temp = tempfile.TemporaryDirectory(prefix='aster-hd-cpu-cache-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder = Path(cls.temp.name)
        header = reconstructed_header(cls.folder)
        # Execute the real loader, validation, pack lookup and new cache bodies.
        # Only SDK hash plumbing is substituted with a deterministic local hash;
        # the production hash comparison and rejection control flow is unchanged.
        body = header[header.index('struct HDTextureReplacement {'):header.index('inline uint64_t HDExpectedDDSSize')]
        source = cls.folder / 'contract.cpp'
        source.write_text(r'''
#include <algorithm>
#include <cstdlib>
#include <new>
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <list>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>
static unsigned fail_allocation = 0;
void* operator new(std::size_t n) {
  if (fail_allocation && !--fail_allocation) throw std::bad_alloc();
  if (void* p = std::malloc(n ? n : 1)) return p;
  throw std::bad_alloc();
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
namespace rex {
std::string hash_bytes(std::string_view text) {
  uint64_t h=14695981039346656037ull;
  for (unsigned char c : text) { h^=c; h*=1099511628211ull; }
  std::ostringstream out;out<<std::hex<<std::setfill('0')<<std::setw(16)<<h<<std::setw(16)<<h;
  return out.str();
}
}
''' + body + r'''
using Image = std::shared_ptr<const HDTextureReplacement>;
std::shared_ptr<HDTextureReplacement> image(size_t bytes) {
  auto x=std::make_shared<HDTextureReplacement>();x->bytes.resize(bytes);return x;
}
void word(std::string& d,size_t p,uint32_t n) {
  for (int i=0;i<4;++i) d[p+i]=char(n>>(8*i));
}
struct Fixture {std::filesystem::path path;std::string fp, hash;size_t size;};
Fixture fixture(const std::filesystem::path& root,char label) {
  Fixture f{root/std::string(1,label),std::string(32,label),{},0};
  std::filesystem::create_directories(f.path);
  uint32_t width=128,height=128,count=0;size_t size=128;
  do {size+=((width+3)/4)*((height+3)/4)*8;++count;
    if(width==1&&height==1) break;
    width=std::max(1u,width>>1);height=std::max(1u,height>>1);
  } while(true);
  std::string dds(size,'\0');word(dds,0,0x20534444);word(dds,4,124);
  word(dds,12,128);word(dds,16,128);word(dds,28,count);word(dds,76,32);
  word(dds,80,4);word(dds,84,0x31545844);
  f.hash=rex::hash_bytes(dds);f.size=size;
  std::ofstream(f.path/"texture.dds",std::ios::binary).write(dds.data(),dds.size());
  std::ofstream(f.path/"texture.index")<<"ASTERHD1 18 64 64 "<<f.fp<<" "<<f.hash<<" reviewed-color-opaque\n";
  return f;
}
void add(HDTexturePack& pack,const Fixture& f) {
  HDTexturePack::LibraryEntry e;e.directory=f.path;e.source_format=18;
  e.source_width=64;e.source_height=64;e.dds_hash=f.hash;e.dds_size=f.size;
  pack.library_entries.emplace(f.fp,std::move(e));
}
int main(int argc,char** argv) {
  assert(argc==3);std::string mode=argv[1];const auto root=std::filesystem::absolute(argv[2]);
  if(mode=="lru") {
    HDSourceCache cache(20);auto a=image(10),b=image(10),c=image(10);
    std::weak_ptr<const HDTextureReplacement> wa=a,wb=b,wc=c;
    cache.Remember("a",a);cache.Remember("b",b);a.reset();b.reset();
    assert(!wa.expired()&&!wb.expired());cache.Remember("a",wa.lock());
    cache.Remember("c",c);c.reset();assert(wb.expired()&&!wa.expired()&&!wc.expired());
    assert(cache.RetainedBytes()==20&&cache.RetainedCount()==2);return 0;
  }
  if(mode=="limits") {
    HDSourceCache cache(20);auto a=image(10),large=image(21),empty=image(0),reserved=image(1);
    reserved->bytes.reserve(30);std::weak_ptr<const HDTextureReplacement> w=a;
    cache.Remember("a",a);cache.Remember("oversize",large);cache.Remember("empty",empty);
    cache.Remember("reserved",reserved);cache.Remember("null",{});a.reset();
    assert(!w.expired()&&cache.RetainedCount()==1&&cache.RetainedBytes()==10);
    auto m=image(1);m->mips.resize(1);cache.Remember("mips",m);
    assert(cache.RetainedCount()==1&&cache.RetainedBytes()<=cache.BudgetBytes());return 0;
  }
  if(mode=="allocation") {
    // Fail both the LRU-node allocation and the index-node allocation. A good
    // image must remain usable and the two cache containers stay consistent.
    auto a=image(10);
    for(unsigned fail : {1u,2u}) {
      HDSourceCache cache(20);fail_allocation=fail;cache.Remember("a",a);fail_allocation=0;
      assert(a->bytes.size()==10&&cache.RetainedBytes()==0&&cache.RetainedCount()==0);
      cache.Remember("a",a);assert(cache.RetainedBytes()==10&&cache.RetainedCount()==1);
    }
    return 0;
  }
  auto a=fixture(root,'a');
  if(mode=="retention" || mode=="threads") {
    HDTexturePack pack;add(pack,a);auto first=pack.Find(a.fp,18,64,64);assert(first);
    std::weak_ptr<const HDTextureReplacement> weak=first;first.reset();
    // A second draw must reuse validated immutable bytes after GPU-side owners
    // disappear, even when no file can be read again during this process.
    std::filesystem::remove(a.path/"texture.dds");assert(!weak.expired());
    if(mode=="threads") {
      std::vector<std::thread> ts;for(int i=0;i<8;++i) ts.emplace_back([&]{
        for(int j=0;j<100;++j) assert(pack.Find(a.fp,18,64,64)==weak.lock());});
      for(auto& t:ts)t.join();
    } else assert(pack.Find(a.fp,18,64,64)==weak.lock());
    assert(pack.source_cache.RetainedBytes()<=HDSourceCache::kDefaultBudget);return 0;
  }
  if(mode=="disabled") {
    HDTexturePack pack(0);add(pack,a);auto p=pack.Find(a.fp,18,64,64);assert(p);
    std::weak_ptr<const HDTextureReplacement> w=p;p.reset();assert(w.expired());
    std::filesystem::remove(a.path/"texture.dds");assert(!pack.Find(a.fp,18,64,64));
    assert(pack.source_cache.RetainedBytes()==0);return 0;
  }
  if(mode=="corruption") {
    HDTexturePack pack;add(pack,a);
    {std::fstream file(a.path/"texture.dds",std::ios::binary|std::ios::in|std::ios::out);
      file.seekp(128);file.put('X');}
    assert(!pack.Find(a.fp,18,64,64));assert(pack.library_entries.at(a.fp).failed);
    assert(pack.source_cache.RetainedBytes()==0);fixture(root,'a');
    assert(!pack.Find(a.fp,18,64,64));return 0; // Failed entry stays quarantined.
  }
  if(mode=="geometry") {
    HDTexturePack pack;add(pack,a);assert(!pack.Find(a.fp,20,64,64));
    assert(!pack.Find(a.fp,18,128,64));assert(!pack.Find(std::string(32,'f'),18,64,64));
    assert(!pack.library_entries.at(a.fp).failed&&pack.source_cache.RetainedCount()==0);
    assert(pack.Find(a.fp,18,64,64));return 0;
  }
  if(mode=="eviction") {
    HDTexturePack measure;add(measure,a);auto p=measure.Find(a.fp,18,64,64);assert(p);
    const size_t cost=p->bytes.capacity()+p->mips.capacity()*sizeof(HDTextureReplacement::Mip);
    auto b=fixture(root,'b');HDTexturePack pack(cost);add(pack,a);add(pack,b);
    auto pa=pack.Find(a.fp,18,64,64);assert(pa);std::weak_ptr<const HDTextureReplacement> wa=pa;
    auto pb=pack.Find(b.fp,18,64,64);assert(pb&&pack.source_cache.RetainedCount()==1);
    // Eviction relinquishes only the source cache's ownership; live GPU owners
    // remain valid. Once those disappear, the normal verified loader is used.
    assert(!wa.expired());pa.reset();assert(wa.expired());
    std::filesystem::remove(a.path/"texture.dds");assert(!pack.Find(a.fp,18,64,64));
    assert(pack.Find(b.fp,18,64,64)==pb&&pack.source_cache.RetainedBytes()==cost);return 0;
  }
  return 99;
}
''')
        cls.binary = cls.folder / ('contract.exe' if os.name == 'nt' else 'contract')
        built = subprocess.run([compiler, '-std=c++20', '-pthread', str(source), '-o', str(cls.binary)],
                               capture_output=True, text=True, timeout=30)
        if built.returncode:
            raise AssertionError(built.stderr)

    def run_contract(self, mode):
        with tempfile.TemporaryDirectory(dir=self.folder) as fixture:
            run = subprocess.run([str(self.binary), mode, fixture], capture_output=True, text=True, timeout=10)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_strong_retention_uses_lru_without_reading_again(self): self.run_contract('lru')
    def test_capacity_mips_and_oversize_respect_explicit_budget(self): self.run_contract('limits')
    def test_allocation_failure_does_not_reject_valid_image_or_break_index(self): self.run_contract('allocation')
    def test_verified_dds_survives_loss_of_gpu_owner(self): self.run_contract('retention')
    def test_concurrent_consumers_share_one_verified_image(self): self.run_contract('threads')
    def test_zero_budget_keeps_original_reload_and_fallback(self): self.run_contract('disabled')
    def test_changed_dds_is_rejected_before_it_can_enter_cache(self): self.run_contract('corruption')
    def test_wrong_geometry_and_unknown_fingerprint_do_not_enter_cache(self): self.run_contract('geometry')
    def test_eviction_preserves_live_owners_then_falls_back_to_verified_load(self): self.run_contract('eviction')


if __name__ == '__main__':
    unittest.main()
