/* Real E203 executes this driver; expected output is checked independently in TB.
 * Fixed addresses belong to this project's integration map, not a claimed
 * organizer-prescribed map. Test data are preloaded through the TB harness.
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

volatile qingyu_result qingyu_last_result;
int main(void)
{
    qingyu_device device;
    qingyu_job job;
    qingyu_result result;
    int rc;
    qingyu_init(&device, (uintptr_t)UINT32_C(0xf0000000), 1000000u);
    device.read_ticks = read_cycles;
    job.input = (const int16_t *)(uintptr_t)UINT32_C(0xa0000000);
    job.weights = (const int16_t *)(uintptr_t)UINT32_C(0xa0004000);
    job.bias = (const int64_t *)(uintptr_t)UINT32_C(0xa000c000);
    job.shift = (const uint8_t *)(uintptr_t)UINT32_C(0xa000c800);
    job.output = (int32_t *)(uintptr_t)UINT32_C(0xa0010000);
    job.rows = QINGYU_ROWS;
    job.k = QINGYU_K;
    job.cols = QINGYU_COLS;
    job.layer_id = QINGYU_TEST_LAYER;
    rc = qingyu_run(&device, &job, &result);
    qingyu_last_result = result;
    *(volatile uint32_t *)(uintptr_t)UINT32_C(0xa0030000) = (uint32_t)result.elapsed_ticks;
    *(volatile uint32_t *)(uintptr_t)UINT32_C(0xa0030004) = (uint32_t)(result.elapsed_ticks >> 32);
    __asm__ volatile ("fence iorw,iorw" ::: "memory");
    *(volatile uint32_t *)(uintptr_t)UINT32_C(0xf0010000) =
        rc == QINGYU_OK ? 1u : UINT32_C(0xe0000000) | (uint32_t)(-rc);
    return rc;
}
