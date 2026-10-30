#include "../../runtime_save_slots.cpp"
#include <cstdlib>
#include <iostream>
static unsigned menu_calls=0, callback_calls=0, apply_calls=0;
static bool io_success=true;
static void Check(bool value) { if (!value) std::abort(); }
static void Put(uint8_t* p, uint32_t value) {
  if constexpr (std::endian::native == std::endian::little) value=std::byteswap(value);
  std::memcpy(p,&value,4);
}
extern "C" void __imp__sub_823809C0(PPCContext& ctx,uint8_t*) { ++menu_calls; ctx.r3.u64=77; }
extern "C" void __imp__sub_8252E010(PPCContext&,uint8_t*) { ++callback_calls; }
extern "C" void __imp__sub_823764F8(PPCContext&,uint8_t*) {}
extern "C" void __imp__sub_823817C0(PPCContext&,uint8_t*) {}
extern "C" void __imp__sub_823D7310(PPCContext&,uint8_t*) {}
extern "C" void __imp__sub_822AE450(PPCContext& ctx,uint8_t*) { ctx.r3.u64=1; }
extern "C" void sub_822AE460(PPCContext& ctx,uint8_t*) { ++apply_calls; ctx.r30.u64=0; }
extern "C" void sub_822AE280(PPCContext& ctx,uint8_t* base) {
  Check(ctx.r4.u32==0x8252E010 && ctx.r5.u32==kReadCookie && ctx.r6.u32==0);
  std::memset(base+ctx.r3.u32+0x530,io_success?0xBB:0xCC,0x448);
  PPCContext callback{};callback.r3.u64=io_success?1:0;callback.r4.u64=ctx.r5.u64;
  sub_8252E010(callback,base);ctx.r3.u64=1;ctx.r30.u64=0;
}
int main() {
  std::array<uint8_t,4096> bytes{};auto base=bytes.data();PPCContext ctx{};
  ctx.lr=0xBAD;ctx.r3.u64=0xffffffff;ctx.r4.u64=0xffffffff;
  sub_823809C0(ctx,nullptr);Check(menu_calls==1 && ctx.r3.u32==77);
  const uint32_t owner=0x40,item=0x80,page=0xC0,child=0x100;
  auto menu=[&](uint32_t page_id,uint32_t child_id,uint32_t flags){
    ctx.lr=0x82381E9C;ctx.r3.u64=owner;ctx.r4.u64=item;
    Put(base+owner+32,page);Put(base+item+152,child);Put(base+page+8,page_id);
    Put(base+child+8,child_id);Put(base+child+16,flags);
    const auto before=menu_calls;sub_823809C0(ctx,base);Check(menu_calls==before+1);
  };
  menu(14,0x91,3); // Game Over Continue must retain original behavior.
  menu(1,3,3); // Other main-menu entries retain original behavior.
  menu(1,1,4); // Disabled entries cannot open a picker.
  read_pending.store(true);read_result.store(-1);ctx.r4.u64=0;ctx.r3.u64=1;
  sub_8252E010(ctx,base);Check(callback_calls==1 && read_result.load()==-1);
  ctx.r4.u64=kReadCookie;sub_8252E010(ctx,base);Check(read_result.load()==1);
  new_game_selection={true,true,false,owner,1};ctx.r3.u64=0;
  sub_822AE450(ctx,base);Check(ctx.r3.u32==0);
  new_game_selection.empty=false;sub_822AE450(ctx,base);Check(ctx.r3.u32==1);
  const uint32_t manager=0x400;Put(base+manager,0x82006B50);Put(base+manager+0xe4,6);
  ctx.r3.u64=manager;ctx.r4.u64=17;ctx.r30.u64=0x12345678;ctx.lr=0x87654321;
  Check(Reload(ctx,base,manager) && apply_calls==1);
  Check(ctx.r30.u32==0x12345678 && ctx.r4.u32==17 && ctx.lr==0x87654321);
  Check(base[manager+0x530]==0xBB && base[manager+0x977]==0xBB);
  io_success=false;Check(!Reload(ctx,base,manager) && apply_calls==1);
  Check(base[manager+0x530]==0xBB && base[manager+0x977]==0xBB); // failed read restored
  new_game_selection.pending=true;Put(base+manager+0xe4,2);ctx.r3.u64=manager;
  sub_823D7310(ctx,base);Check(!new_game_selection.pending);
  std::cout << "NATIVE_SAVE_SLOT_CONTRACT_OK\n";
}
