cmake_minimum_required(VERSION 3.25)
project(AsterTextureInspection LANGUAGES C CXX)
find_package(rexglue 0.10.0 EXACT CONFIG REQUIRED)
add_executable(aster_untile_capture untile_capture.cpp)
target_compile_features(aster_untile_capture PRIVATE cxx_std_23)
target_link_libraries(aster_untile_capture PRIVATE rex::runtime)

# libmspack's internal LZX header is not exported by the SDK installation.
# The Python builder verifies these source headers against the pinned gitlink.
set(ASTER_MSPACK_SOURCE "" CACHE PATH "Pinned libmspack mspack/ header directory")
if(NOT IS_ABSOLUTE "${ASTER_MSPACK_SOURCE}" OR
   NOT EXISTS "${ASTER_MSPACK_SOURCE}/mspack.h" OR
   NOT EXISTS "${ASTER_MSPACK_SOURCE}/lzx.h")
  message(FATAL_ERROR "ASTER_MSPACK_SOURCE must name the verified absolute libmspack header directory")
endif()
add_executable(aster_xctd_decode xctd_decode.c)
target_include_directories(aster_xctd_decode PRIVATE "${ASTER_MSPACK_SOURCE}")
target_link_libraries(aster_xctd_decode PRIVATE rex::mspack)
