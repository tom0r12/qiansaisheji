/* Independent API/error-code oracle plus comparison against unmodified opt14. */
#include "qingyu_accel.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#if defined(__unix__)
#include <sys/mman.h>
#include <unistd.h>
#endif

int baseline_validate(const qingyu_device *, const qingyu_job *);

_Alignas(64) static int16_t inputs[99 * 64];
_Alignas(64) static int16_t weights[64 * 256];
_Alignas(64) static int64_t biases[256];
_Alignas(64) static uint8_t shifts[260];
_Alignas(64) static qingyu_out_t outputs[99 * 256];
static unsigned long checks;
static unsigned io_calls;
static uint32_t random_state = UINT32_C(20261111);

static uint32_t random32(void)
{
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
}

static uint32_t forbidden_read(void *context, uintptr_t address)
{
    (void)context; (void)address; ++io_calls; return 0;
}

static void forbidden_write(void *context, uintptr_t address, uint32_t value)
{
    (void)context; (void)address; (void)value; ++io_calls;
}

static qingyu_device device(void)
{
    qingyu_device d;
    qingyu_init(&d, UINT32_C(0xf0000000), 1000000);
    return d;
}

static qingyu_job job(unsigned alignment)
{
    qingyu_job j = {inputs, weights, biases, shifts + alignment, outputs,
                   99, 64, 256, 0};
    return j;
}

static void clean(void)
{
    memset(biases, 0, sizeof(biases));
    memset(shifts, 47, sizeof(shifts));
}

static void expect(const char *label, const qingyu_device *d,
                   const qingyu_job *j, int expected)
{
    int old_rc = baseline_validate(d, j);
    int new_rc = qingyu_validate(d, j);
    ++checks;
    if (old_rc != expected || new_rc != expected || io_calls) {
        fprintf(stderr, "FAIL %s check=%lu expected=%d baseline=%d candidate=%d io=%u\n",
                label, checks, expected, old_rc, new_rc, io_calls);
        exit(1);
    }
}

static void scan_tests(void)
{
    qingyu_device d = device();
    /* Every possible byte in every column, for all four pointer alignments.
     * Neighbor bytes are 47, exercising carry boundaries in packed checks. */
    for (unsigned alignment = 0; alignment < 4; ++alignment) {
        clean();
        qingyu_job j = job(alignment);
        uint8_t *s = shifts + alignment;
        for (unsigned column = 0; column < 256; ++column) {
            for (unsigned value = 0; value < 256; ++value) {
                s[column] = (uint8_t)value;
                expect("exhaustive shift", &d, &j,
                       value <= 47 ? QINGYU_OK : QINGYU_ERR_FORMAT);
            }
            s[column] = 47;
        }
    }
    static const int64_t limits[] = {
        -INT64_C(140737488355329), -INT64_C(140737488355328),
        -INT64_C(140737488355327), -1, 0, 1,
        INT64_C(140737488355326), INT64_C(140737488355327),
        INT64_C(140737488355328), INT64_MIN, INT64_MAX
    };
    for (unsigned alignment = 0; alignment < 4; ++alignment) {
        clean();
        qingyu_job j = job(alignment);
        for (unsigned column = 0; column < 256; ++column) {
            for (unsigned k = 0; k < sizeof(limits) / sizeof(limits[0]); ++k) {
                biases[column] = limits[k];
                int invalid = limits[k] < -INT64_C(140737488355328)
                           || limits[k] > INT64_C(140737488355327);
                expect("bias boundary", &d, &j, invalid ? QINGYU_ERR_FORMAT : QINGYU_OK);
            }
            biases[column] = 0;
        }
    }
    /* Mixed packed bytes, including several failures in different lanes. */
    for (unsigned sample = 0; sample < 10000; ++sample) {
        clean();
        qingyu_job j = job(sample % 4);
        uint8_t *s = shifts + sample % 4;
        int invalid = 0;
        for (unsigned k = 0; k < 256; ++k) {
            s[k] = (uint8_t)(random32() % ((sample & 1) ? 48 : 256));
            invalid |= s[k] > 47;
            uint64_t magnitude = (((uint64_t)random32() << 32) | random32())
                               & UINT64_C(0x7fffffffffff);
            biases[k] = (int64_t)magnitude * ((random32() & 1) ? 1 : -1);
        }
        if (sample % 7 == 0) {
            biases[random32() % 256] = INT64_C(140737488355328);
            invalid = 1;
        }
        expect("mixed scan", &d, &j, invalid ? QINGYU_ERR_FORMAT : QINGYU_OK);
    }
}

static void structure_tests(void)
{
    clean();
    qingyu_device d = device();
    qingyu_job j = job(0), bad;
    qingyu_device wrong;
    expect("valid", &d, &j, QINGYU_OK);
    expect("null device", NULL, &j, QINGYU_ERR_ARGUMENT);
    expect("null job", &d, NULL, QINGYU_ERR_ARGUMENT);
    wrong = d; wrong.poll_limit = 0;
    expect("zero polling", &wrong, &j, QINGYU_ERR_ARGUMENT);
    wrong = d; wrong.read32 = forbidden_read;
    expect("callback mismatch", &wrong, &j, QINGYU_ERR_ARGUMENT);
    wrong.write32 = forbidden_write;
    expect("callback pair does no IO", &wrong, &j, QINGYU_OK);
    wrong = d; wrong.base += 1;
    expect("base alignment", &wrong, &j, QINGYU_ERR_ALIGNMENT);
    wrong = d; wrong.base = UINTPTR_MAX & ~(uintptr_t)3;
    expect("base overflow", &wrong, &j, QINGYU_ERR_ARGUMENT);

    /* Combine each structural error with invalid parameter data. The old
     * precedence must win before any scan, even on the aligned fast path. */
    shifts[0] = 255; biases[255] = INT64_MAX;
    bad = j; bad.input = NULL;
    expect("null input priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.weights = NULL;
    expect("null weights priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.bias = NULL;
    expect("null bias priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.shift = NULL;
    expect("null shift priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.output = NULL;
    expect("null output priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.rows = 98;
    expect("rows priority", &d, &bad, QINGYU_ERR_DIMENSIONS);
    bad = j; bad.k = 63;
    expect("k priority", &d, &bad, QINGYU_ERR_DIMENSIONS);
    bad = j; bad.cols = 255;
    expect("cols priority", &d, &bad, QINGYU_ERR_DIMENSIONS);
    bad = j; bad.layer_id = 12;
    expect("layer priority", &d, &bad, QINGYU_ERR_DIMENSIONS);
    bad = j; bad.input = (const int16_t *)((uintptr_t)inputs + 1);
    expect("input alignment priority", &d, &bad, QINGYU_ERR_ALIGNMENT);
    bad = j; bad.weights = (const int16_t *)((uintptr_t)weights + 1);
    expect("weight alignment priority", &d, &bad, QINGYU_ERR_ALIGNMENT);
    bad = j; bad.bias = (const int64_t *)((uintptr_t)biases + 4);
    expect("bias alignment priority", &d, &bad, QINGYU_ERR_ALIGNMENT);
    bad = j; bad.output = (qingyu_out_t *)((uintptr_t)outputs + 2);
    expect("output alignment priority", &d, &bad, QINGYU_ERR_ALIGNMENT);
    bad = j; bad.input = (const int16_t *)(UINTPTR_MAX & ~(uintptr_t)1);
    expect("input span priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.weights = (const int16_t *)(UINTPTR_MAX & ~(uintptr_t)1);
    expect("weight span priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.bias = (const int64_t *)(UINTPTR_MAX & ~(uintptr_t)7);
    expect("bias span priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.shift = (const uint8_t *)(UINTPTR_MAX - 3);
    expect("shift span priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.output = (qingyu_out_t *)(UINTPTR_MAX & ~(uintptr_t)3);
    expect("output span priority", &d, &bad, QINGYU_ERR_ARGUMENT);
    bad = j; bad.output = (qingyu_out_t *)inputs;
    expect("input overlap priority", &d, &bad, QINGYU_ERR_BUFFER_OVERLAP);
    bad = j; bad.output = (qingyu_out_t *)weights;
    expect("weight overlap priority", &d, &bad, QINGYU_ERR_BUFFER_OVERLAP);
    bad = j; bad.output = (qingyu_out_t *)biases;
    expect("bias overlap priority", &d, &bad, QINGYU_ERR_BUFFER_OVERLAP);
    bad = j; bad.output = (qingyu_out_t *)shifts;
    expect("shift overlap priority", &d, &bad, QINGYU_ERR_BUFFER_OVERLAP);
    /* Format-only collisions preserve their shared error code. */
    expect("shift and bias both invalid", &d, &j, QINGYU_ERR_FORMAT);
    clean(); j.layer_id = 11;
    expect("last layer accepted", &d, &j, QINGYU_OK);
}

static void guard_page_tests(void)
{
#if defined(__unix__)
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    if (page < 2048) exit(2);
    unsigned char *s = mmap(NULL, 2 * page, PROT_READ | PROT_WRITE,
                           MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    unsigned char *b = mmap(NULL, 2 * page, PROT_READ | PROT_WRITE,
                           MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (s == MAP_FAILED || b == MAP_FAILED ||
        mprotect(s + page, page, PROT_NONE) || mprotect(b + page, page, PROT_NONE)) exit(2);
    qingyu_device d = device();
    qingyu_job j = job(0);
    uint8_t *guard_shifts = s + page - 256;
    int64_t *guard_bias = (int64_t *)(b + page - 2048);
    memset(guard_shifts, 47, 256); memset(guard_bias, 0, 2048);
    j.shift = guard_shifts; j.bias = guard_bias;
    expect("aligned end-of-buffer guard", &d, &j, QINGYU_OK);
    guard_shifts[255] = 48;
    expect("last shift guard", &d, &j, QINGYU_ERR_FORMAT);
    guard_shifts[255] = 47; guard_bias[255] = INT64_C(140737488355328);
    expect("last bias guard", &d, &j, QINGYU_ERR_FORMAT);
    guard_bias[255] = 0;
    for (unsigned offset = 1; offset <= 3; ++offset) {
        j.shift = guard_shifts - offset;
        memset((void *)j.shift, 47, 256);
        expect("unaligned near guard", &d, &j, QINGYU_OK);
    }
    munmap(s, 2 * page); munmap(b, 2 * page);
#endif
}

int main(void)
{
    scan_tests(); structure_tests(); guard_page_tests();
    printf("PASS validate4 checks=%lu baseline_equivalent=1 io_calls=%u\n", checks, io_calls);
    return 0;
}
