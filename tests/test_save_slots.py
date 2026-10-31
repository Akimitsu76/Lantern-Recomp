from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class SaveSlotTests(unittest.TestCase):
    def test_actual_store_keeps_users_slots_cancel_and_backups_separate(self):
        cc = shutil.which('clang++') or shutil.which('g++')
        if not cc:
            self.skipTest('C++23 compiler required')
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'check.cpp'
            source.write_text(r'''
#include "integrations/rexglue/save-slots/save_slots.h"
#include <cassert>
using namespace rex::system::xam::green_lantern;
namespace fs=std::filesystem;
static void put(const fs::path& p,const char* value){fs::create_directories(p.parent_path());std::ofstream(p,std::ios::binary)<<value;}
static std::string read(const fs::path&p){std::ifstream f(p);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char**argv){
 SaveSlotStore s(argv[1]);const uint64_t a=0xB13EBABEBABEBABE,b=0x123;
 assert(s.Active(a)==1 && !fs::exists(argv[1]));
 auto legacy=s.SlotPackage(a,1)/"GL_10";auto header=s.SlotHeader(a,1);
 put(legacy,"human-progress");put(header,"human-header");
 assert(legacy==fs::path(argv[1])/"B13EBABEBABEBABE/575207E9/00000001/GL_10/GL_10");
 assert(s.List(a)[0].existing && !s.List(a)[1].existing);
 const auto now=std::chrono::duration_cast<std::chrono::seconds>(
     std::chrono::system_clock::now().time_since_epoch()).count();
 assert(s.List(a)[0].modified >= now-60 && s.List(a)[0].modified <= now+60);
 assert(s.Select(a,{})==SelectResult::kCancelled && !fs::exists(s.SelectionPath(a)));
 assert(s.Select(a,0)==SelectResult::kInvalidSlot && s.Select(a,7)==SelectResult::kInvalidSlot);
 assert(s.Select(a,2,true)==SelectResult::kOpenContent && !fs::exists(s.SelectionPath(a)));
 assert(s.Select(a,2)==SelectResult::kSuccess && s.Active(a)==2);
 assert(s.Active(b)==1 && !s.List(b)[0].existing);
 assert(s.PackageRoot(a,kTitleId,1)==s.SlotBase(a,2)/"00000001");
 assert(s.PackageRoot(a,kTitleId,2)==s.TitleRoot(a)/"00000002");
 assert(s.PackageRoot(a,0x9999,1)==s.TitleRoot(a,0x9999)/"00000001");
 put(s.SlotPackage(a,2)/"GL_10","second-progress");put(s.SlotHeader(a,2),"second-header");
 assert(s.Select(a,1)==SelectResult::kSuccess && s.Active(a)==1);
 assert(s.Select(a,2)==SelectResult::kSuccess && s.Active(a)==2); // atomic replacement
 assert(read(legacy)=="human-progress" && read(header)=="human-header");
 auto backup=s.Backup(a,2);assert(backup && fs::exists(*backup/"complete"));
 assert(read(*backup/"GL_10"/"GL_10")=="second-progress");
 assert(read(*backup/"GL_10.header")=="second-header");
 put(s.SlotPackage(a,2)/"GL_10","new-campaign");
 assert(read(*backup/"GL_10"/"GL_10")=="second-progress" && read(legacy)=="human-progress");
 put(s.SelectionPath(a),"6garbage");assert(s.Active(a)==1);
 put(s.SelectionPath(a),"3\r\n");assert(s.Active(a)==3);
 fs::create_directory_symlink(s.TitleRoot(a),s.SlotBase(a,4));
 assert(s.Select(a,4)==SelectResult::kIoError && !s.Backup(a,4));
 assert(s.OwnsPackage(a,s.SlotPackage(a,2)) && !s.OwnsPackage(a,s.SlotPackage(b,2)));
}
''')
            binary = root / 'check'
            build = subprocess.run([cc, '-std=c++23', '-Wall', '-Wextra', '-I', str(project),
                                    str(source), '-o', str(binary)], capture_output=True, text=True, timeout=90)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary), str(root / 'user')], capture_output=True, text=True, timeout=20)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_sdk_ships_the_reviewed_store_verbatim(self):
        from native_port.spatial_sdk import normalized_patch
        root = Path(__file__).resolve().parents[1]
        patch = root / 'integrations/rexglue/patches/0037-native-save-slots.patch'
        sections = normalized_patch(patch.read_text())
        lines = sections['include/rex/system/xam/green_lantern_save_slots.h']
        added = '\n'.join(line[1:] for line in lines if line.startswith('+') and not line.startswith('+++'))+'\n'
        self.assertEqual(added, (root / 'integrations/rexglue/save-slots/save_slots.h').read_text())


if __name__ == '__main__':
    unittest.main()
