/* Engineering performance harness: source data reside in the upper shared
 * SRAM staging region. E203 performs EVERY copy over ICB after reset; no task
 * data are preloaded into the accelerator or its live shared-memory buffers.
 * This models CPU-mediated loading, not an organizer-specified external link.
 */
#include "qingyu_accel.h"
#ifndef QINGYU_TEST_LAYER
#define QINGYU_TEST_LAYER 0
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
    mailbox[4] = (uint32_t)result.compute_cycles_sum;
    __asm__ volatile ("fence iorw,iorw" ::: "memory");
    *(volatile uint32_t *)(uintptr_t)0xf0010000u =
        rc == QINGYU_OK ? 1u : 0xe0000000u | (uint32_t)(-rc);
    return rc;
}
