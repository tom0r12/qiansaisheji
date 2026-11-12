#ifndef QINGYU_ACCEL_H
#define QINGYU_ACCEL_H

#include <stddef.h>
#include <stdint.h>

/* opt22 interface v1: explicit commands copy the configured staging source
 * (live + 0x40000) to live SRAM and then commit X/W privately after write ACK.
 * This candidate's harness must retain the real source-to-live load window. */
#ifndef QINGYU_FUSED_LOAD
#ifdef QINGYU_OUT16
#define QINGYU_FUSED_LOAD 1
#else
#define QINGYU_FUSED_LOAD 0
#endif
#endif
#define QINGYU_FUSED_CAP_OFFSET UINT32_C(0xd0)
#define QINGYU_FUSED_X_OFFSET UINT32_C(0xd4)
#define QINGYU_FUSED_W_OFFSET UINT32_C(0xd8)
#define QINGYU_FUSED_STATUS_OFFSET UINT32_C(0xdc)
#define QINGYU_FUSED_INTERFACE_ID UINT32_C(0x51462201)

#ifdef __cplusplus
extern "C" {
#endif

/* opt4: interleave the staging copy of W tile pairs with computation.
 * Pair p (tiles 2p,2p+1) is one 16-word chunk per K row. Pair p+1 is staged
 * while tiles 2p and 2p+1 compute; IL_EVEN_CHUNKS of the 64 rows during the
 * even tile, the rest during the odd tile (whose W prefetch then follows). */
/* v1 (CPU-issued 16-word chunks) measured slower: 86,879 vs 79,377 cycles on
 * layer01 (block engine shared with write-back). Kept for reference, off. */
#ifndef QINGYU_INTERLEAVE_STAGE
#define QINGYU_INTERLEAVE_STAGE 0
#endif
/* v2: one command starts the FIO background staging engine (0xf00000b0),
 * which copies W pairs 0..7 in idle bus cycles; weight commands are held by
 * hardware until their pair is staged. */
#ifndef QINGYU_AUTO_WB
/* INT16 build: the FIO writes every output batch back by itself (0xc0/0xc4). */
#ifdef QINGYU_OUT16
#define QINGYU_AUTO_WB 1
#else
#define QINGYU_AUTO_WB 0
#endif
#endif
#ifndef QINGYU_TILE_CHAIN
/* CPU-driven variant of the same overlap (superseded by QINGYU_AUTO_WB). */
#define QINGYU_TILE_CHAIN 0
#endif
#ifndef QINGYU_WAIT_CMD
/* opt12: wait for a tile with a FIO command that is held until the accelerator
 * is idle (the CPU stalls on the bus instead of polling). */
#ifdef QINGYU_OUT16
#define QINGYU_WAIT_CMD 1
#else
#define QINGYU_WAIT_CMD 0
#endif
#endif
#ifndef QINGYU_ASYNC_STAGE
/* Environment (opt11): bias/shift pre-copy + W pairs 0..7 on the staging
 * engine, the input copy is an asynchronous FIO copy (0xbc/0xc8). */
#define QINGYU_ASYNC_STAGE 1
#endif
#ifndef QINGYU_INPUT_FIRST
/* Driver: the (asynchronous) input load is issued before tile 0's prefetch. */
#ifdef QINGYU_OUT16
#define QINGYU_INPUT_FIRST 1
#else
#define QINGYU_INPUT_FIRST 0
#endif
#endif
#ifndef QINGYU_BG_INPUT
/* Environment (opt10): staging engine copies the input and W pairs 1..7; the
 * CPU copies bias/shift and W pair 0; the input load trails the input copy. */
#define QINGYU_BG_INPUT 1
#endif
#ifndef QINGYU_BG_META
/* Environment: FIO staging engine also copies bias+shift (command 0xb4). */
#define QINGYU_BG_META 1
#endif
#ifndef QINGYU_EARLY_TILE0
/* Issue tile 0's weight and metadata commands before the input load. */
#define QINGYU_EARLY_TILE0 1
#endif
#ifndef QINGYU_BG_STAGE
#define QINGYU_BG_STAGE 1
#endif
#ifndef QINGYU_IL_EVEN_CHUNKS
#define QINGYU_IL_EVEN_CHUNKS 40u
#endif
#ifndef QINGYU_IL_PER_BATCH
#define QINGYU_IL_PER_BATCH 4u
#endif
#define QINGYU_ROWS             UINT32_C(99)
#define QINGYU_K                UINT32_C(64)
#define QINGYU_COLS             UINT32_C(256)
#ifdef QINGYU_FAST_TASK
#define QINGYU_LANES            UINT32_C(16)
#else
#define QINGYU_LANES            UINT32_C(4)
#endif
#define QINGYU_LAYERS           UINT32_C(12)
#define QINGYU_TILE_COUNT       (QINGYU_COLS / QINGYU_LANES)
#define QINGYU_TILE_OUTPUTS     (QINGYU_ROWS * QINGYU_LANES)
#ifdef QINGYU_DOUBLE_BUFFER
#define QINGYU_REG_BATCH_A      UINT32_C(0x20)
#define QINGYU_ID_VALUE         UINT32_C(0x51590002)
#else
#define QINGYU_ID_VALUE         UINT32_C(0x51590001)
#endif

#define QINGYU_REG_ID           UINT32_C(0x0000)
#define QINGYU_REG_CONTROL      UINT32_C(0x0004)
#define QINGYU_REG_STATUS       UINT32_C(0x0008)
#define QINGYU_REG_LAYER_ID     UINT32_C(0x000c)
#define QINGYU_REG_TILE_BASE    UINT32_C(0x0010)
#define QINGYU_REG_ERROR        UINT32_C(0x0014)
#define QINGYU_REG_CYCLES       UINT32_C(0x0018)
#define QINGYU_REG_OUTPUT_COUNT UINT32_C(0x001c)
#define QINGYU_INPUT_OFFSET     UINT32_C(0x1000)
#define QINGYU_WEIGHT_OFFSET    UINT32_C(0x5000)
#define QINGYU_META_OFFSET      UINT32_C(0x6000)
#define QINGYU_OUTPUT_OFFSET    UINT32_C(0x7000)

#define QINGYU_CONTROL_START    UINT32_C(0x01)
#define QINGYU_CONTROL_CLEAR    UINT32_C(0x02)
#define QINGYU_CONTROL_RESET    UINT32_C(0x04)
#define QINGYU_STATUS_BUSY      UINT32_C(0x01)
#define QINGYU_STATUS_DONE      UINT32_C(0x02)
#define QINGYU_STATUS_ERROR     UINT32_C(0x04)

enum qingyu_error {
    QINGYU_OK = 0,
    QINGYU_ERR_ARGUMENT = -1,
    QINGYU_ERR_DIMENSIONS = -2,
    QINGYU_ERR_ALIGNMENT = -3,
    QINGYU_ERR_FORMAT = -4,
    QINGYU_ERR_DEVICE_ID = -5,
    QINGYU_ERR_TIMEOUT = -6,
    QINGYU_ERR_HARDWARE = -7,
    QINGYU_ERR_OUTPUT_COUNT = -8,
    QINGYU_ERR_BUFFER_OVERLAP = -9
};

/* Set both callbacks or neither. A null pair uses volatile 32-bit MMIO.
 * Callback addresses are absolute byte addresses, including device.base.
 * read_ticks is optional and must use a stable, monotonically increasing
 * uint64 counter. These hooks also permit testing the copy/control driver on
 * a host without dereferencing the target MMIO address.
 */
typedef uint32_t (*qingyu_read32_fn)(void *context, uintptr_t address);
typedef void (*qingyu_write32_fn)(void *context, uintptr_t address,
                                 uint32_t value);
typedef uint64_t (*qingyu_ticks_fn)(void *context);

typedef struct {
    uintptr_t base;
    uint32_t poll_limit;
    void *context;
    qingyu_read32_fn read32;
    qingyu_write32_fn write32;
    qingyu_ticks_fn read_ticks;
} qingyu_device;

#ifdef QINGYU_OUT16
/* Two INT16 results per 32-bit word, low column first. */
typedef int16_t qingyu_out_t;
#define QINGYU_OUT_PER_WORD 2u
#define QINGYU_OUT_ALIGN_MASK 31u
#else
typedef int32_t qingyu_out_t;
#define QINGYU_OUT_PER_WORD 1u
#define QINGYU_OUT_ALIGN_MASK 63u
#endif

typedef struct {
    const int16_t *input;      /* [rows][k], row major */
    const int16_t *weights;    /* [k][cols], row major */
    const int64_t *bias;       /* [cols], signed 48-bit encoded biases */
    const uint8_t *shift;      /* [cols], values 0..47 */
    qingyu_out_t *output;      /* [rows][cols], row major */
    uint32_t rows;
    uint32_t k;
    uint32_t cols;
    uint32_t layer_id;
} qingyu_job;

typedef struct {
    uint32_t completed_tiles;
    uint32_t last_status;
    uint32_t hardware_error;
    uint32_t last_output_count;
    uint64_t compute_cycles_sum;
    uint64_t elapsed_ticks;
    uint32_t timing_valid;
} qingyu_result;

void qingyu_init(qingyu_device *device, uintptr_t base, uint32_t poll_limit);

/* Abort a current tile and wait for idle. This resets task/control state,
 * not SRAM contents. The next run always reloads input and every parameter.
 */
int qingyu_reset(const qingyu_device *device);

/* Execute one complete first-linear-layer task, consisting of 64 tiles.
 * No heap or floating-point support is required. All pointers must remain
 * valid until return. On failure, completed_tiles identifies the prefix of
 * output columns that was copied; do not use a partial result as a task.
 * poll_limit counts status reads per tile, not wall-clock ticks.
 */
int qingyu_run(const qingyu_device *device, const qingyu_job *job,
              qingyu_result *result);

/* Validate a device/job pair without touching the task data path.  A caller
 * that runs the same job repeatedly can validate once here and then use
 * qingyu_run_prepared(), which keeps every runtime check but skips the
 * per-column bias/shift validation already proven.  The result is not cached
 * implicitly: qingyu_run() always revalidates the whole job.
 */
int qingyu_validate(const qingyu_device *device, const qingyu_job *job);
int qingyu_run_prepared(const qingyu_device *device, const qingyu_job *job,
                        qingyu_result *result);

#ifdef __cplusplus
}
#endif

#endif
