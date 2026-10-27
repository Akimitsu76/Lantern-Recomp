// Pure policy checks: no SDK runtime, game, renderer or global input required.
#include <rex/graphics/pipeline/texture/capture_policy.h>
#include <cstdio>
#include <fstream>
int main(int argc, char** argv) {
 using rex::graphics::TextureCapturePolicy;
 if (TextureCapturePolicy::Bounded("256",16,256)!=256 ||
     TextureCapturePolicy::Bounded("257",16,256)!=16 ||
     TextureCapturePolicy::Bounded("-1",16,256)!=16 ||
     TextureCapturePolicy::Bounded("32junk",16,256)!=16 ||
     TextureCapturePolicy::Bounded("0",16,256)!=16 ||
     TextureCapturePolicy::Bounded(nullptr,16,256)!=16) return 1;
 if (argc == 2) {
   // Caller sets arm path to a new, private file; absence must block capture.
   if (TextureCapturePolicy::IsArmed()) return 2;
   { std::ofstream file(argv[1]); file << "armed\n"; }
   if (!TextureCapturePolicy::IsArmed()) return 3;
 }
 std::puts("bounded capture policy and opt-in arming passed");
}
