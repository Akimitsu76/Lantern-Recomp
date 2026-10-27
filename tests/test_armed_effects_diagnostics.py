"""Contracts for same-session local source arming in optional SDK patch0019."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from native_port.effects_diagnostics import (EffectsSource, format_effects_source_index,
    parse_effects_metadata, parse_effects_source_index)
from native_port.native_cache import apply_patch_exact
from tests.test_effects_diagnostics import fixture, line

ROOT=Path(__file__).resolve().parents[1]
PATCH18=ROOT/'integrations/rexglue/patches/0018-effects-sampling-diagnostics.patch'
PATCH19=ROOT/'integrations/rexglue/patches/0019-armed-effects-source-index.patch'
SOURCE=EffectsSource('2452e9bd136e14b0b0298a6d0befde85',1568,1568,52,2768896)


def fixture2():
    record=fixture()
    record.update(schema=2,source_raw_xxh3_128=SOURCE.fingerprint,snapshot_bytes=SOURCE.extent,
        source_geometry={'width':SOURCE.width,'height':SOURCE.height,'pitch':SOURCE.pitch,
            'extent':SOURCE.extent,'format':20,'endian':1,'tiled':True,'mip_max_level':0})
    return record


class ArmedEffectsParserTests(unittest.TestCase):
    def test_schema2_requires_explicit_reviewed_sources(self):
        record=fixture2()
        with self.assertRaises(ValueError): parse_effects_metadata([line(record)])
        parsed=parse_effects_metadata([line(record)],reviewed_sources=[SOURCE])
        self.assertEqual(parsed[0]['source_geometry']['width'],1568)
        self.assertIsNone(parsed[0]['actual_rt_size'])

    def test_outside_reviewed_sources_and_modified_geometry_rejected(self):
        for field,value in (('width',1440),('height',1400),('pitch',51),('extent',1024),
                            ('format',18),('endian',0),('tiled',False),('mip_max_level',1)):
            record=fixture2();record['source_geometry'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                parse_effects_metadata([line(record)],reviewed_sources=[SOURCE])
        record=fixture2();record['source_raw_xxh3_128']='1'*32
        with self.assertRaises(ValueError): parse_effects_metadata([line(record)],reviewed_sources=[SOURCE])
        with self.assertRaises(ValueError): parse_effects_metadata([line(fixture())],reviewed_sources=[SOURCE])

    def test_index_roundtrip_limits_and_complete_validation(self):
        text=format_effects_source_index([SOURCE])
        self.assertEqual(parse_effects_source_index(text),(SOURCE,))
        self.assertEqual(parse_effects_source_index(text.replace('\n','\r\n')),(SOURCE,))
        invalid=('ASTERFX1\n',text+'\n',text+text.split('\n')[1]+'\n',
                 text.replace(' 1568 ',' +1568 ',1),text.replace(' 1568 ',' -1568 ',1),
                 text.replace(' 1568 ',' 00000001568 ',1),text.replace('ASTERFX1','ASTERFX2'),
                 text.replace(' 52 ',' 48 '),text.replace(' 52 ',' 65 '),
                 text.replace(' 1568 ',' 2049 ',1),text.replace(str(SOURCE.extent),'4194305'),
                 text.replace(SOURCE.fingerprint,SOURCE.fingerprint.upper()),
                 text+'ignored trailing line\n','x'*16385,
                 text.replace(' 1568 ','\u00a01568 ',1))
        for entry in invalid:
            with self.subTest(entry=entry[:80]),self.assertRaises(ValueError): parse_effects_source_index(entry)
        eight=[EffectsSource(f'{i:032x}',64,64,2,4096) for i in range(8)]
        self.assertEqual(len(parse_effects_source_index(format_effects_source_index(eight))),8)
        with self.assertRaises(ValueError): format_effects_source_index(eight+[EffectsSource('f'*32,64,64,2,4096)])


class SourceIndexRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('c++') or shutil.which('clang++')
        if not compiler: raise unittest.SkipTest('C++ compiler unavailable')
        cls.temp=tempfile.TemporaryDirectory(prefix='aster-source-index-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.folder=Path(cls.temp.name)
        text=PATCH18.read_text()
        header=text.split('+++ b/include/rex/graphics/pipeline/texture/effects_diagnostics.h\n',1)[1].split('--- a/',1)[0]
        added='\n'.join(row[1:] for row in header.splitlines() if row.startswith('+'))+'\n'
        path=cls.folder/'include/rex/graphics/pipeline/texture/effects_diagnostics.h'
        path.parent.mkdir(parents=True);path.write_text(added)
        apply_patch_exact(cls.folder,PATCH19.read_text().split('--- a/src/',1)[0])
        (cls.folder/'contract.cpp').write_text(r'''
#include "include/rex/graphics/pipeline/texture/effects_diagnostics.h"
#include <atomic>
#include <thread>
#include <iostream>
using namespace rex::graphics::effects_diagnostics;
const std::string valid="ASTERFX1\n2452e9bd136e14b0b0298a6d0befde85 1568 1568 52 2768896\n";
void write(const std::filesystem::path& path,const std::string& text) {
  std::ofstream file(path,std::ios::binary);file<<text;
}
int main(int argc,char** argv) {
  if(argc!=2) return 1;
  const std::string mode=argv[1];
  const auto environment=SourceIndexEnvironment();
  if(mode=="parse") {
    SourceIndex index(environment.second);auto sources=index.Poll(0);
    std::cout<<(sources?sources->size():0);return 0;
  }
  if(mode=="env") {
    auto sources=Selection().Get();
    return sources && sources->size()==1 && (*sources)[0].width==1568 ? 0:2;
  }
  if(mode=="fallback") {
    auto sources=Selection().Get();
    return !Selection().local && sources && (*sources)[0].width==1440 ? 0:3;
  }
  if(mode=="empty") return Selection().local && !Selection().Get() ? 0:4;
  if(mode!="arming") return 5;
  const auto path=environment.second;
  std::filesystem::remove(path);
  SourceIndex index(path);StateBudget budget;unsigned snapshots=0;
  auto observe=[&](uint64_t now) {
    auto sources=index.Poll(now);
    if(sources && budget.Reserve("first")) ++snapshots;
    return bool(sources);
  };
  if(observe(0)||snapshots) return 6;
  write(path,"invalid");
  if(observe(1000)||snapshots) return 7;
  write(path,valid);
  if(observe(1500)||snapshots) return 8; // Not yet one second since last file read.
  if(!observe(2000)||snapshots!=1) return 9;
  auto original=index.Poll(2001);
  write(path,"invalid and changed");
  if(index.Poll(3000)!=original || !observe(3000)||snapshots!=1) return 10;
  StateBudget cap;std::atomic<unsigned> calls{0};std::vector<std::thread> threads;
  for(unsigned t=0;t<8;++t) threads.emplace_back([&,t] {
    for(unsigned n=0;n<1000;++n)
      if(cap.Reserve(std::to_string(t)+":"+std::to_string(n))) ++calls;
  });
  for(auto& thread:threads) thread.join();
  return calls==32 && cap.Full() && !cap.Reserve("extra") ? 0:11;
}
''')
        cls.binary=cls.folder/'contract'
        result=subprocess.run([compiler,'-std=c++17','-pthread',str(cls.folder/'contract.cpp'),'-o',str(cls.binary)],
            capture_output=True,text=True,timeout=60)
        if result.returncode: raise AssertionError(result.stderr)

    def run_mode(self,mode,text=None,empty=False,unset=False):
        path=self.folder/'fontes-ação-粒子.index'
        if text is not None: path.write_text(text)
        env=dict(os.environ)
        env.pop('ASTER_EFFECTS_SOURCE_INDEX',None)
        if not unset: env['ASTER_EFFECTS_SOURCE_INDEX']='' if empty else str(path)
        result=subprocess.run([str(self.binary),mode],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr or f'{mode}: {result.returncode}')
        return result.stdout

    def test_late_creation_rate_limit_immutable_cache_and_global_cap(self):
        self.run_mode('arming')

    def test_environment_unicode_path_empty_reject_and_omitted_fallback(self):
        self.run_mode('env',format_effects_source_index([SOURCE]))
        self.run_mode('fallback',unset=True)
        self.run_mode('empty',empty=True)

    def test_exact_cpp_index_parser_rejects_invalid_and_accepts_max_eight(self):
        valid=format_effects_source_index([SOURCE])
        for text in ('',valid,valid.replace('\n','\r\n'),'ASTERFX1\n',valid+'\n',
                     valid+valid.split('\n')[1]+'\n',valid.replace(' 1568 ',' +1568 ',1),
                     valid.replace(' 52 ',' 65 '),valid.replace(str(SOURCE.extent),'4194305'),
                     valid.replace(' 1568 ',' 00000001568 ',1),'x'*16385):
            try: expected=len(parse_effects_source_index(text))
            except ValueError: expected=0
            with self.subTest(text=text[:70]): self.assertEqual(self.run_mode('parse',text),str(expected))
        eight=[EffectsSource(f'{i:032x}',64,64,2,4096) for i in range(8)]
        self.assertEqual(self.run_mode('parse',format_effects_source_index(eight)),'8')
        self.assertEqual(self.run_mode('parse',format_effects_source_index(eight)+'f'*32+' 64 64 2 4096\n'),'0')
