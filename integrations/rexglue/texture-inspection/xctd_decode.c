/* Bounded research helper for BE16-length-framed regular LZX payloads.
 * Auto mode supports only the corroborated single-segment XCTD flags=0x62
 * layout. Other layouts require explicit research parameters, never guesses.
 * Links against public libmspack (LGPL-2.1); no proprietary decoder is used.
 */
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <mspack.h>
#include <lzx.h>
#ifdef _WIN32
#include <io.h>
#include <wchar.h>
/* Preserve UTF-16 paths from the Windows command line, independent of ACP. */
typedef wchar_t path_char;
#define path_literal(value) L##value
#define path_compare wcscmp
#define path_strtoul wcstoul
#define path_open _wfopen
#define path_remove _wremove
#define program_entry wmain
#define file_close _close
#define file_fdopen _fdopen
#else
#include <unistd.h>
typedef char path_char;
#define path_literal(value) value
#define path_compare strcmp
#define path_strtoul strtoul
#define path_open fopen
#define path_remove remove
#define program_entry main
#define file_close close
#define file_fdopen fdopen
#endif

#define INPUT_LIMIT (64u * 1024u * 1024u)
#define OUTPUT_LIMIT (256u * 1024u * 1024u)

struct bounded_file {
    struct mspack_file base;
    unsigned char *data;
    size_t size, position;
};
static int read_memory(struct mspack_file *file, void *buffer, int count) {
    struct bounded_file *f = (struct bounded_file *)file;
    size_t n;
    if (count < 0 || f->position > f->size) return -1;
    n = (size_t)count;
    if (n > f->size - f->position) n = f->size - f->position;
    if (n) memcpy(buffer, f->data + f->position, n);
    f->position += n;
    return (int)n;
}
static int write_memory(struct mspack_file *file, void *buffer, int count) {
    struct bounded_file *f = (struct bounded_file *)file;
    if (count < 0 || f->position > f->size ||
        (size_t)count > f->size - f->position) return -1;
    if (count) memcpy(f->data + f->position, buffer, (size_t)count);
    f->position += (size_t)count;
    return count;
}
static void *allocate_memory(struct mspack_system *sys, size_t size) {
    (void)sys;
    return calloc(1, size);
}
static void free_memory(void *p) { free(p); }
static void copy_memory(void *source, void *destination, size_t n) {
    memcpy(destination, source, n);
}
static int parse_number(const path_char *text, size_t limit, size_t *value) {
    path_char *end;
    unsigned long n;
    if (!text[0] || text[0] == '-' || text[0] == '+' ||
        text[0] < '0' || text[0] > '9') return 0;
    errno = 0;
    n = path_strtoul(text, &end, 10);
    if (errno || *end || n > limit) return 0;
    *value = (size_t)n;
    return 1;
}
static FILE *create_exclusive(const path_char *path) {
    int fd;
    FILE *file;
#ifdef _WIN32
    fd = _wopen(path, _O_WRONLY | _O_CREAT | _O_EXCL | _O_BINARY,
               _S_IREAD | _S_IWRITE);
#else
    int flags = O_WRONLY | O_CREAT | O_EXCL;
#ifdef O_NOFOLLOW
    flags |= O_NOFOLLOW;
#endif
#ifdef O_CLOEXEC
    flags |= O_CLOEXEC;
#endif
    fd = open(path, flags, 0600);
#endif
    if (fd < 0) return NULL;
    file = file_fdopen(fd, "wb");
    if (!file) {
        file_close(fd);
        /* We own this newly created path; never remove a pre-existing file. */
        path_remove(path);
    }
    return file;
}
static int fail(const char *message) {
    fprintf(stderr, "aster_xctd_decode: %s\n", message);
    return 1;
}
int program_entry(int argc, path_char **argv) {
    FILE *input = NULL, *output = NULL;
    unsigned char *bytes = NULL, *joined = NULL, *decoded = NULL;
    size_t payload_offset = 0, output_size = 0, window_bits = 0, input_size;
    const char *profile = "explicit-be16-framed-lzx";
    int auto_header = argc == 3;
    size_t cursor, compressed_size = 0, chunks = 0;
    long measured;
    int result = 1, decode_result;
    struct mspack_system sys;
    struct bounded_file src, dst;
    struct lzxd_stream *decoder = NULL;
    if (!auto_header && (argc != 9 || path_compare(argv[3], path_literal("--payload-offset")) ||
        path_compare(argv[5], path_literal("--uncompressed-size")) || path_compare(argv[7], path_literal("--window-bits")))) {
        fprintf(stderr, "Usage: aster_xctd_decode INPUT OUTPUT [--payload-offset N "
                "--uncompressed-size N --window-bits N]\n"
                "Auto mode accepts only XCTD v1 single-segment flags 0x62.\n"
                "Other layouts require explicit research parameters.\n"
                "Limits: input 64 MiB; output 256 MiB; window bits 15..21.\n");
        return 2;
    }
    if (!auto_header && (!parse_number(argv[4], INPUT_LIMIT, &payload_offset) ||
        !parse_number(argv[6], OUTPUT_LIMIT, &output_size) || !output_size ||
        !parse_number(argv[8], 21, &window_bits) || window_bits < 15))
        return fail("invalid bounded numeric parameter");
    input = path_open(argv[1], path_literal("rb"));
    if (!input) return fail("cannot open input");
    if (fseek(input, 0, SEEK_END) || (measured = ftell(input)) < 0 ||
        (unsigned long)measured > INPUT_LIMIT || fseek(input, 0, SEEK_SET)) {
        fclose(input);
        return fail("input must be a seekable file within 64 MiB");
    }
    input_size = (size_t)measured;
    if (auto_header) {
        unsigned char header[20];
        static const unsigned char prefix[8] = {0x0f, 0xf5, 0x12, 0xed, 1, 0, 0, 0};
        uint32_t size_word;
        if (input_size < sizeof(header) || fread(header, 1, sizeof(header), input) != sizeof(header) ||
            memcmp(header, prefix, sizeof(prefix)) || header[12] || header[13] ||
            header[14] || header[15] != 0x62) {
            fclose(input);
            return fail("unsupported XCTD header (requires v1, one segment, flags 0x62)");
        }
        size_word = ((uint32_t)header[16] << 24) | ((uint32_t)header[17] << 16) |
                    ((uint32_t)header[18] << 8) | header[19];
        if ((size_word & 0xfff) || !(size_word >> 12) || fseek(input, 0, SEEK_SET)) {
            fclose(input);
            return fail("invalid single-segment size field or nonzero size-table padding");
        }
        payload_offset = 20; output_size = size_word >> 12; window_bits = 17;
        profile = "xctd-v1-single-segment-flags-0x62";
        /* Bytes 8..11 are preserved in the input, but their checksum is not verified. */
    }
    if (payload_offset >= input_size) {
        fclose(input);
        return fail("payload offset outside input");
    }
    bytes = (unsigned char *)malloc(input_size);
    joined = (unsigned char *)malloc(input_size - payload_offset);
    decoded = (unsigned char *)malloc(output_size);
    if (!bytes || !joined || !decoded) { fail("allocation failed"); goto done; }
    if (fread(bytes, 1, input_size, input) != input_size || fgetc(input) != EOF || ferror(input)) {
        fail("input read failed or file changed size"); goto done;
    }
    fclose(input); input = NULL;
    cursor = payload_offset;
    while (cursor < input_size) {
        size_t size;
        if (input_size - cursor < 2) { fail("truncated BE16 chunk length"); goto done; }
        size = ((size_t)bytes[cursor] << 8) | bytes[cursor + 1];
        cursor += 2;
        if (!size || size > input_size - cursor) {
            fail("empty or truncated framed chunk"); goto done;
        }
        memcpy(joined + compressed_size, bytes + cursor, size);
        cursor += size; compressed_size += size; ++chunks;
    }
    memset(&sys, 0, sizeof(sys));
    sys.read = read_memory; sys.write = write_memory;
    sys.alloc = allocate_memory; sys.free = free_memory; sys.copy = copy_memory;
    memset(&src, 0, sizeof(src)); memset(&dst, 0, sizeof(dst));
    src.data = joined; src.size = compressed_size;
    dst.data = decoded; dst.size = output_size;
    decoder = lzxd_init(&sys, &src.base, &dst.base, (int)window_bits, 0,
                        32768, (off_t)output_size, 0);
    if (!decoder) { fail("libmspack decoder initialization failed"); goto done; }
    decode_result = lzxd_decompress(decoder, (off_t)output_size);
    if (decode_result != MSPACK_ERR_OK || dst.position != output_size || decoder->block_remaining) {
        fprintf(stderr, "aster_xctd_decode: LZX result=%d produced=%lu expected=%lu\n",
                decode_result, (unsigned long)dst.position, (unsigned long)output_size);
        goto done;
    }
    /* Publish only after complete decoding. Existing files/symlinks are refused. */
    output = create_exclusive(argv[2]);
    if (!output) { fail("output already exists or cannot be exclusively created"); goto done; }
    if (fwrite(decoded, 1, output_size, output) != output_size || fflush(output)) {
        fail("output write failed"); fclose(output); output = NULL; path_remove(argv[2]); goto done;
    }
    if (fclose(output)) { output = NULL; path_remove(argv[2]); fail("output close failed"); goto done; }
    output = NULL;
    printf("{\"profile\":\"%s\",\"container_checksum_verified\":false,\"input_bytes\":%lu,"
           "\"payload_offset\":%lu,\"chunks\":%lu,\"compressed_bytes\":%lu,"
           "\"output_bytes\":%lu,\"window_bits\":%lu,\"reset_interval\":0}\n",
           profile, (unsigned long)input_size, (unsigned long)payload_offset, (unsigned long)chunks,
           (unsigned long)compressed_size, (unsigned long)output_size, (unsigned long)window_bits);
    result = 0;
done:
    if (decoder) lzxd_free(decoder);
    if (input) fclose(input);
    free(bytes); free(joined); free(decoded);
    return result;
}
