/* CPU shared-SRAM access cost probe.  Compiled against the unmodified wbank2 RTL
 * model; the probe runs before load_words(), so the performance window is
 * unaffected and outer_cycles differences are the exact probe cost. */
#include "qingyu_accel.h"
#ifndef QINGYU_TEST_LAYER
#define QINGYU_TEST_LAYER 1
#endif
#ifndef PROBE_MODE
#define PROBE_MODE 0
#endif
#ifndef PROBE_WORDS
#define PROBE_WORDS 512
#endif

static uint64_t read_cycles(void *unused)
{
    uint32_t hi, lo, again;
    (void)unused;
    do {
        __asm__ volatile ("csrr %0,mcycleh" : "=r"(hi));
        __asm__ volatile ("csrr %0,mcycle" : "=r"(lo));
        __asm__ volatile ("csrr %0,mcycleh" : "=r"(again));
    } while (hi != again);
    return ((uint64_t)hi << 32) | lo;
}

static void load_words(uint32_t offset, uint32_t words)
{
#ifdef QINGYU_BLOCK_COPY
    volatile uint32_t *cmd=(volatile uint32_t *)(uintptr_t)0xf0000038u;
    uint32_t i=0;
    for (; i+256<=words; i+=256)
        *(volatile uint32_t *)(uintptr_t)0xf0000084u=0xa0000000u+offset+4*i;
    for (; i<words; i+=16) *cmd=0xa0000000u+offset+4*i;
#else
    volatile uint32_t *dst = (volatile uint32_t *)(uintptr_t)(0xa0000000u + offset);
    volatile const uint32_t *src = (volatile const uint32_t *)(uintptr_t)(0xa0040000u + offset);
    for (uint32_t i = 0; i < words; ++i) dst[i] = src[i];
#endif
}

static uint32_t probe(void)
{
    volatile uint32_t *scratch = (volatile uint32_t *)(uintptr_t)0xa0038000u;
    volatile const uint32_t *src = (volatile const uint32_t *)(uintptr_t)0xa000c000u;
    volatile const uint8_t *shift = (volatile const uint8_t *)(uintptr_t)0xa000c800u;
    volatile uint32_t sink = 0;
    (void)src; (void)shift; (void)sink;
    uint64_t t0 = read_cycles(NULL);
#if PROBE_MODE == 1
    for (uint32_t i = 0; i < PROBE_WORDS; ++i) scratch[i] = i * 2654435761u;
#elif PROBE_MODE == 2
    for (uint32_t i = 0; i < PROBE_WORDS; ++i) sink += src[i];
#elif PROBE_MODE == 3
    for (uint32_t i = 0; i < PROBE_WORDS / 2; ++i) {
        uint32_t lo = src[2*i], hi = src[2*i+1];
        scratch[2*i] = lo;
        scratch[2*i+1] = (hi & 0xffffu) | ((uint32_t)shift[i] << 16);
    }
#elif PROBE_MODE == 4
    for (uint32_t i = 0; i < PROBE_WORDS / 2; ++i) {
        scratch[2*i] = src[2*i];
        scratch[2*i+1] = (src[2*i+1] & 0xffffu) | ((uint32_t)shift[i] << 16);
    }
#elif PROBE_MODE == 5
    for (uint32_t i = 0; i < PROBE_WORDS / 4; ++i) {
        uint32_t w = shift[i];
        for (uint32_t b = 0; b < 4; ++b) if (((w >> (8*b)) & 0xffu) > 47u) sink = 1;
    }
#elif PROBE_MODE == 6
    for (uint32_t i = 0; i < PROBE_WORDS; i += 2) {
        uint32_t lo = src[i], hi = src[i+1];
        if ((hi + 0x8000u) >= 0x10000u && sink != 0xdeadbeefu) sink = 2;
        sink += lo;
    }
#elif PROBE_MODE == 7
    for (uint32_t i = 0; i < PROBE_WORDS; i += 2) {
        uint32_t lo = src[i], hi = src[i+1];
        if ((int32_t)hi < -32768 || (int32_t)hi > 32767) sink = 2;
        (void)lo;
    }
#elif PROBE_MODE == 8
    /* 32 accel meta MMIO writes, the baseline per-tile pattern (lane 0..15 x 2). */
    for (uint32_t lane = 0; lane < 16; ++lane) {
        *(volatile uint32_t *)(uintptr_t)(0xf0006000u + lane*8u) = 0x12345678u;
        *(volatile uint32_t *)(uintptr_t)(0xf0006000u + lane*8u + 4u) = 0x00010000u;
    }
#endif
    uint64_t t1 = read_cycles(NULL);
    if (PROBE_MODE == 1 || PROBE_MODE == 3 || PROBE_MODE == 4) scratch[PROBE_WORDS] = sink;
    else *(volatile uint32_t *)(uintptr_t)0xa0030000u = sink;
    return (uint32_t)(t1 - t0);
}

int main(void)
{
    qingyu_device device;
    qingyu_job job;
    qingyu_result result;
    qingyu_init(&device, (uintptr_t)0xf0000000u, 1000000u);
    device.read_ticks = read_cycles;
    job.input = (const int16_t *)(uintptr_t)0xa0000000u;
    job.weights = (const int16_t *)(uintptr_t)0xa0004000u;
    job.bias = (const int64_t *)(uintptr_t)0xa000c000u;
    job.shift = (const uint8_t *)(uintptr_t)0xa000c800u;
    job.output = (int32_t *)(uintptr_t)0xa0010000u;
    job.rows = QINGYU_ROWS; job.k = QINGYU_K; job.cols = QINGYU_COLS;
    job.layer_id = QINGYU_TEST_LAYER;
    uint32_t probe_cycles = probe();
    uint64_t start = read_cycles(NULL);
    load_words(0, 99u * 64u / 2u);
    load_words(0x4000u, 64u * 256u / 2u);
    load_words(0xc000u, 256u * 2u);
    load_words(0xc800u, 256u / 4u);
    __asm__ volatile ("fence iorw,iorw" ::: "memory");
    int rc = qingyu_run(&device, &job, &result);
    uint64_t elapsed = read_cycles(NULL) - start;
    volatile uint32_t *mailbox = (volatile uint32_t *)(uintptr_t)0xa0030000u;
    mailbox[0] = (uint32_t)result.elapsed_ticks;
    mailbox[1] = (uint32_t)(result.elapsed_ticks >> 32);
    mailbox[2] = (uint32_t)elapsed;
    mailbox[3] = (uint32_t)(elapsed >> 32);
    mailbox[4] = probe_cycles;
    __asm__ volatile ("fence iorw,iorw" ::: "memory");
    *(volatile uint32_t *)(uintptr_t)0xf0010000u =
        rc == QINGYU_OK ? 1u : 0xe0000000u | (uint32_t)(-rc);
    return rc;
}
