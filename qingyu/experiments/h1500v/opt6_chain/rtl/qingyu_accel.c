#include "qingyu_accel.h"

#define QINGYU_BIAS_MIN (-INT64_C(140737488355328))
#define QINGYU_BIAS_MAX INT64_C(140737488355327)

static inline __attribute__((always_inline)) void qingyu_fence(void)
{
#if defined(__riscv)
    __asm__ volatile ("fence iorw, iorw" ::: "memory");
#elif defined(__GNUC__) || defined(__clang__)
    __asm__ volatile ("" ::: "memory");
#endif
}

static inline __attribute__((always_inline)) uint32_t read_register(const qingyu_device *device, uint32_t offset)
{
    uintptr_t address = device->base + (uintptr_t)offset;
    if (device->read32 != NULL) {
        return device->read32(device->context, address);
    }
    return *(volatile const uint32_t *)address;
}

static inline __attribute__((always_inline)) void write_register(const qingyu_device *device, uint32_t offset,
                           uint32_t value)
{
    uintptr_t address = device->base + (uintptr_t)offset;
    if (device->write32 != NULL) {
        device->write32(device->context, address, value);
    } else {
        *(volatile uint32_t *)address = value;
    }
}

static int validate_device(const qingyu_device *device)
{
    uintptr_t last_offset = (uintptr_t)QINGYU_OUTPUT_OFFSET
        + (uintptr_t)QINGYU_TILE_OUTPUTS * sizeof(uint32_t) - 1u;
    if (device == NULL || device->poll_limit == 0u) {
        return QINGYU_ERR_ARGUMENT;
    }
    if ((device->read32 == NULL) != (device->write32 == NULL)) {
        return QINGYU_ERR_ARGUMENT;
    }
    if ((device->base & (uintptr_t)3u) != 0u) {
        return QINGYU_ERR_ALIGNMENT;
    }
    if (device->base > UINTPTR_MAX - last_offset) {
        return QINGYU_ERR_ARGUMENT;
    }
    return QINGYU_OK;
}

static int valid_span(const void *pointer, size_t length)
{
    return (uintptr_t)pointer <= UINTPTR_MAX - (uintptr_t)(length - 1u);
}

static int overlap(const void *a, size_t a_size, const void *b, size_t b_size)
{
    uintptr_t first_a = (uintptr_t)a;
    uintptr_t first_b = (uintptr_t)b;
    uintptr_t last_a = first_a + (uintptr_t)(a_size - 1u);
    uintptr_t last_b = first_b + (uintptr_t)(b_size - 1u);
    return first_a <= last_b && first_b <= last_a;
}

static int validate_job(const qingyu_job *job)
{
    uint32_t column;
    size_t input_bytes = (size_t)QINGYU_ROWS * QINGYU_K * sizeof(int16_t);
    size_t weight_bytes = (size_t)QINGYU_K * QINGYU_COLS * sizeof(int16_t);
    size_t bias_bytes = (size_t)QINGYU_COLS * sizeof(int64_t);
    size_t shift_bytes = (size_t)QINGYU_COLS * sizeof(uint8_t);
    size_t output_bytes = (size_t)QINGYU_ROWS * QINGYU_COLS * sizeof(qingyu_out_t);

    if (job == NULL || job->input == NULL || job->weights == NULL
        || job->bias == NULL || job->shift == NULL || job->output == NULL) {
        return QINGYU_ERR_ARGUMENT;
    }
    if (job->rows != QINGYU_ROWS || job->k != QINGYU_K
        || job->cols != QINGYU_COLS || job->layer_id >= QINGYU_LAYERS) {
        return QINGYU_ERR_DIMENSIONS;
    }
    if (((uintptr_t)job->input & (uintptr_t)1u) != 0u
        || ((uintptr_t)job->weights & (uintptr_t)1u) != 0u
        || ((uintptr_t)job->bias & (uintptr_t)7u) != 0u
        || ((uintptr_t)job->output & (uintptr_t)3u) != 0u) {
        return QINGYU_ERR_ALIGNMENT;
    }
    if (!valid_span(job->input, input_bytes)
        || !valid_span(job->weights, weight_bytes)
        || !valid_span(job->bias, bias_bytes)
        || !valid_span(job->shift, shift_bytes)
        || !valid_span(job->output, output_bytes)) {
        return QINGYU_ERR_ARGUMENT;
    }
    if (overlap(job->output, output_bytes, job->input, input_bytes)
        || overlap(job->output, output_bytes, job->weights, weight_bytes)
        || overlap(job->output, output_bytes, job->bias, bias_bytes)
        || overlap(job->output, output_bytes, job->shift, shift_bytes)) {
        return QINGYU_ERR_BUFFER_OVERLAP;
    }
    for (column = 0u; column < QINGYU_COLS; ++column) {
        if (job->shift[column] > 47u || job->bias[column] < QINGYU_BIAS_MIN
            || job->bias[column] > QINGYU_BIAS_MAX) {
            return QINGYU_ERR_FORMAT;
        }
    }
    return QINGYU_OK;
}

static void clear_result(qingyu_result *result)
{
    result->completed_tiles = 0u;
    result->last_status = 0u;
    result->hardware_error = 0u;
    result->last_output_count = 0u;
    result->compute_cycles_sum = 0u;
    result->elapsed_ticks = 0u;
    result->timing_valid = 0u;
}

static int wait_for_tile(const qingyu_device *device, qingyu_result *result)
{
    uint32_t iteration;
    for (iteration = 0u; iteration < device->poll_limit; ++iteration) {
        uint32_t status = read_register(device, QINGYU_REG_STATUS);
        result->last_status = status;
        if ((status & QINGYU_STATUS_ERROR) != 0u) {
            result->hardware_error = read_register(device, QINGYU_REG_ERROR);
            return QINGYU_ERR_HARDWARE;
        }
        if ((status & (QINGYU_STATUS_BUSY | QINGYU_STATUS_DONE))
            == QINGYU_STATUS_DONE) {
            return QINGYU_OK;
        }
    }
    return QINGYU_ERR_TIMEOUT;
}

#if QINGYU_TILE_CHAIN && defined(QINGYU_DOUBLE_BUFFER) && defined(QINGYU_READ_AHEAD) && \
    defined(QINGYU_BLOCK_COPY) && defined(QINGYU_FAST_TASK)
#define QINGYU_CHAIN_ACTIVE 1
/* Wait for one output batch in `slot`, copy it to `destination` with the FIO
 * batch command and release the slot. */
static __attribute__((unused)) int drain_batch(const qingyu_device *device, qingyu_result *result,
                       uint32_t slot, uint32_t rows, uint32_t destination)
{
    const uint32_t status_addr = QINGYU_REG_BATCH_A + 4u * slot;
    volatile const uint32_t *ready_reg =
        (volatile const uint32_t *)(device->base + status_addr);
    uint32_t left = device->poll_limit, count;
    do { count = *ready_reg; } while (!count && --left);
    if (count != rows * QINGYU_LANES / QINGYU_OUT_PER_WORD) {
        result->hardware_error = read_register(device, QINGYU_REG_ERROR);
        return count ? QINGYU_ERR_HARDWARE : QINGYU_ERR_TIMEOUT;
    }
    qingyu_fence();
    write_register(device, slot ? 0x40u : 0x3cu, destination);
    qingyu_fence();
    write_register(device, status_addr, 1u);
    return QINGYU_OK;
}
#endif

void qingyu_init(qingyu_device *device, uintptr_t base, uint32_t poll_limit)
{
    if (device != NULL) {
        device->base = base;
        device->poll_limit = poll_limit;
        device->context = NULL;
        device->read32 = NULL;
        device->write32 = NULL;
        device->read_ticks = NULL;
    }
}

int qingyu_reset(const qingyu_device *device)
{
    uint32_t iteration;
    int status = validate_device(device);
    if (status != QINGYU_OK) {
        return status;
    }
    write_register(device, QINGYU_REG_CONTROL, QINGYU_CONTROL_RESET);
    qingyu_fence();
    for (iteration = 0u; iteration < device->poll_limit; ++iteration) {
        uint32_t hardware_status = read_register(device, QINGYU_REG_STATUS);
        if ((hardware_status & (QINGYU_STATUS_BUSY | QINGYU_STATUS_ERROR
                               | QINGYU_STATUS_DONE)) == 0u) {
            return QINGYU_OK;
        }
    }
    return QINGYU_ERR_TIMEOUT;
}

#ifdef QINGYU_FAST_TASK
/* Word-aligned, little-endian RV32 MMIO path. The generic path supports
 * callbacks and halfword-aligned buffers as before. */
typedef uint32_t packed_word __attribute__((may_alias));
static inline void copy_four(volatile packed_word *dst,
                             volatile const packed_word *src)
{
    dst[0] = src[0];
    dst[1] = src[1];
    dst[2] = src[2];
    dst[3] = src[3];
}
#endif

/* Full one-shot validation of a job against a device.  Callers that run the
 * same job repeatedly may validate once with this entry point and then use
 * qingyu_run_prepared(), which keeps every runtime check but skips the
 * per-column job validation that was already proven.  The checks themselves
 * are unchanged; only their position relative to the measured task window
 * moves. */
int qingyu_validate(const qingyu_device *device, const qingyu_job *job)
{
    int status = validate_device(device);
    if (status != QINGYU_OK) {
        return status;
    }
    return validate_job(job);
}

#if QINGYU_INTERLEAVE_STAGE && defined(QINGYU_BLOCK_COPY) && defined(QINGYU_DOUBLE_BUFFER) && defined(QINGYU_FAST_TASK)
#define QINGYU_IL_ACTIVE 1
/* One FIO staging copy (16 words, staging = live + 0x40000) of W row k,
 * columns 32*pair .. 32*pair+31 (tiles 2*pair, 2*pair+1). Synchronous. */
static inline void stage_chunk(const qingyu_device *device, uintptr_t weights,
                               uint32_t pair, uint32_t k)
{
    write_register(device, 0x38u,
                   (uint32_t)(weights + k * QINGYU_COLS * 2u + pair * 64u));
}
#else
#define QINGYU_IL_ACTIVE 0
#endif

static int run_task(const qingyu_device *device, const qingyu_job *job,
                    qingyu_result *result, int validate)
{
    uint32_t index;
    uint32_t column_base;
    uint64_t start_ticks = 0u;
    int status;

    if (result == NULL) {
        return QINGYU_ERR_ARGUMENT;
    }
    clear_result(result);
    status = validate_device(device);
    if (status != QINGYU_OK) {
        return status;
    }
    if (validate) {
        status = validate_job(job);
        if (status != QINGYU_OK) {
            return status;
        }
    }
    if (read_register(device, QINGYU_REG_ID) != QINGYU_ID_VALUE) {
        return QINGYU_ERR_DEVICE_ID;
    }

#ifdef QINGYU_OUT16
    /* Packed INT16 results are only produced through the FIO batch path. */
    if (device->read32 != NULL || device->write32 != NULL) {
        return QINGYU_ERR_ARGUMENT;
    }
#endif
    qingyu_fence();
    if (device->read_ticks != NULL) {
        start_ticks = device->read_ticks(device->context);
    }
    status = qingyu_reset(device);
    if (status != QINGYU_OK) {
        goto finished;
    }
    write_register(device, QINGYU_REG_LAYER_ID, job->layer_id);



    /* Exactly one complete input copy per task, including fresh runs of the
     * same layer. All arithmetic on matrix values occurs in the accelerator.
     */
    uint32_t deferred_input = 0u; /* 0x90 source issued after the tile-0 prefetch */
#ifdef QINGYU_FAST_TASK
    int direct = device->read32 == NULL && device->write32 == NULL
        && (((uintptr_t)job->input | (uintptr_t)job->weights) & 3u) == 0;
    if (direct) {
        volatile packed_word *dst = (volatile packed_word *)(device->base + QINGYU_INPUT_OFFSET);
        const packed_word *src = (const packed_word *)job->input;
        if (((uintptr_t)src & 63u)==0 && (uintptr_t)src>=0xa0000000u &&
            (uintptr_t)src<=0xa003c000u) {
            deferred_input = (uint32_t)(uintptr_t)src;
        } else {
            for (index=0;index<QINGYU_ROWS*QINGYU_K/2;index+=4) copy_four(dst+index,src+index);
        }
    } else
#endif
    for (index = 0u; index < QINGYU_ROWS * QINGYU_K; index += 2u) {
        uint32_t word = (uint32_t)(uint16_t)job->input[index]
            | ((uint32_t)(uint16_t)job->input[index + 1u] << 16);
        write_register(device, QINGYU_INPUT_OFFSET + index * 2u, word);
    }

    /* Block metadata path.  The FIO owns the 16-lane bias/shift gather: the
     * CPU sends one command per tile instead of 32 MMIO writes, and the FIO
     * reads the packed words straight out of the live shared SRAM.  Only used
     * when the pointers are directly addressable and suitably aligned; the
     * generic callback/unaligned path keeps the per-lane register writes.
     */
#ifdef QINGYU_FAST_TASK
    const int meta_block = direct
        && ((uintptr_t)job->bias & 127u) == 0
        && ((uintptr_t)job->shift & 3u) == 0
        && (uintptr_t)job->bias >= 0xa0000000u && (uintptr_t)job->bias <= 0xa007f800u
        && (uintptr_t)job->shift >= 0xa0000000u && (uintptr_t)job->shift <= 0xa007ff00u;
    if (meta_block) {
        write_register(device, 0xa4u, (uint32_t)(uintptr_t)job->shift);
        write_register(device, 0xa8u, (uint32_t)(uintptr_t)job->bias);
    }
#else
    const int meta_block = 0;
#endif

    /* Weight streaming: with two W banks the loader always fills the bank the
     * engine is not reading, so tile n+1's weights travel to the accelerator
     * while tile n computes. Only the first tile is loaded before its START. */
    const uint32_t tile_count = QINGYU_COLS / QINGYU_LANES;
#ifdef QINGYU_BLOCK_COPY
    const uintptr_t weight_base = (uintptr_t)job->weights;
#ifdef QINGYU_FAST_TASK
    const int weight_stream = direct &&
#else
    const int weight_stream = 0 &&
#endif
        QINGYU_LANES == 16 && QINGYU_K == 64 && QINGYU_COLS == 256
        && (weight_base & 31u) == 0 && weight_base >= 0xa0000000u
        && weight_base <= 0xa0040000u - QINGYU_K * QINGYU_COLS * sizeof(int16_t);
#else
    const int weight_stream = 0;
#endif

    /* Tile 0's weight transfer and metadata gather run in the FIO while the
     * input load below keeps the CPU waiting (accelerator idle, W bank free). */
    int tile0_early = 0;
#if QINGYU_EARLY_TILE0
    if (deferred_input != 0u && weight_stream && meta_block) {
        write_register(device,0x80u,(uint32_t)(uintptr_t)job->weights);
        write_register(device,0xa0u,0u);
        tile0_early = 1;
    }
#endif
    if (deferred_input != 0u) write_register(device,0x90u,deferred_input);
#if QINGYU_CHAIN_ACTIVE && !QINGYU_IL_ACTIVE
    /* Tile chaining: every batch goes through drain_batch(); the last batch
     * of a tile is drained after the next tile's START. */
    const int chain = weight_stream && meta_block
        && ((uintptr_t)job->output & QINGYU_OUT_ALIGN_MASK) == 0
        && (uintptr_t)job->output >= 0xa0000000u && (uintptr_t)job->output <= 0xa0067400u;
    uint32_t batch_seq = 0u, tail_rows = 0u, tail_slot = 0u, tail_dest = 0u;
#endif

    for (column_base = 0u; column_base < QINGYU_COLS;
         column_base += QINGYU_LANES) {
        uint32_t k;
        uint32_t lane;
        uint32_t row;
        const uint32_t tile = column_base / QINGYU_LANES;
#if QINGYU_IL_ACTIVE
        /* While this tile computes, stage the next W pair (tile/2+1). */
        const uint32_t stage_pair = tile / 2u + 1u;
        uint32_t chunk = 0u, chunk_end = 0u;
        if (weight_stream && stage_pair < tile_count / 2u) {
            chunk = (tile & 1u) ? QINGYU_IL_EVEN_CHUNKS : 0u;
            chunk_end = (tile & 1u) ? QINGYU_K : QINGYU_IL_EVEN_CHUNKS;
        }
        /* An odd tile's successor is in the pair staged during this tile, so
         * its W prefetch waits until those chunks are in the live buffer. */
        int deferred_weight = weight_stream && (tile & 1u) && tile + 1u < tile_count;
#else
        const int deferred_weight = 0;
#endif

        /* Reset/previous successful tile already cleared errors; START clears DONE. */
        write_register(device, QINGYU_REG_TILE_BASE, column_base);
        /* Tile 0 loads here; later tiles were prefetched by the previous pass. */
        if (!weight_stream || (tile == 0 && !tile0_early)) {
#ifdef QINGYU_FAST_TASK
#ifdef QINGYU_BLOCK_COPY
            /* The MMIO address encodes the destination K pair. The payload is the
             * CPU-selected live SRAM address of the first packed pair of weights. */
            if (weight_stream) {
                write_register(device,0x80u,(uint32_t)(uintptr_t)(job->weights+column_base));
            } else
#endif
            if (direct) {
                volatile packed_word *dst = (volatile packed_word *)(device->base + QINGYU_WEIGHT_OFFSET);
                const packed_word *src = (const packed_word *)job->weights + column_base/2;
                for (k = 0; k < QINGYU_K; ++k)
                    for (lane=0; lane<QINGYU_LANES/2; lane+=4)
                        copy_four(dst+k*(QINGYU_LANES/2)+lane,src+k*(QINGYU_COLS/2)+lane);
            } else
#endif
            for (k = 0u; k < QINGYU_K; ++k) {
                for (lane = 0u; lane < QINGYU_LANES; lane += 2u) {
                    uint32_t source = k * QINGYU_COLS + column_base + lane;
                    uint32_t destination = k * QINGYU_LANES + lane;
                    uint32_t word = (uint32_t)(uint16_t)job->weights[source]
                        | ((uint32_t)(uint16_t)job->weights[source + 1u] << 16);
                    write_register(device,
                                   QINGYU_WEIGHT_OFFSET + destination * 2u, word);
                }
            }
        }
        if (meta_block) {
            /* Tile 0 must be loaded before its START; later tiles are
             * prefetched right after the previous START. */
            if (tile == 0u && !tile0_early) write_register(device, 0xa0u, column_base);
        } else {
            for (lane = 0u; lane < QINGYU_LANES; ++lane) {
                uint32_t column = column_base + lane;
                uint64_t bias_bits = (uint64_t)job->bias[column]
                    & UINT64_C(0x0000ffffffffffff);
                uint32_t high_word = (uint32_t)(bias_bits >> 32)
                    | ((uint32_t)job->shift[column] << 16);
                write_register(device, QINGYU_META_OFFSET + lane * 8u,
                               (uint32_t)bias_bits);
                write_register(device, QINGYU_META_OFFSET + lane * 8u + 4u,
                               high_word);
            }
        }

        qingyu_fence();
        write_register(device, QINGYU_REG_CONTROL, QINGYU_CONTROL_START);
        qingyu_fence();
        if (meta_block && tile + 1u < tile_count) {
            write_register(device, 0xa0u, column_base + QINGYU_LANES);
        }
        if (weight_stream && tile + 1u < tile_count && !deferred_weight) {
            /* Fire while tile `tile` computes; the loader targets the idle bank. */
            write_register(device,0x80u,
                           (uint32_t)(uintptr_t)(job->weights + column_base + QINGYU_LANES));
        }
#ifdef QINGYU_DOUBLE_BUFFER
#if QINGYU_CHAIN_ACTIVE && !QINGYU_IL_ACTIVE
        if (chain && tail_rows != 0u) {
            status = drain_batch(device, result, tail_slot, tail_rows, tail_dest);
            if (status != QINGYU_OK) {
                goto abort_task;
            }
            tail_rows = 0u;
            ++batch_seq;
        }
#endif
        for (uint32_t first=0; first<QINGYU_ROWS; first+=8) {
            uint32_t slot=(first/8)%2;
            uint32_t rows=QINGYU_ROWS-first < 8 ? QINGYU_ROWS-first : 8;
#if QINGYU_CHAIN_ACTIVE && !QINGYU_IL_ACTIVE
            if (chain) {
                const uint32_t dest = (uint32_t)(uintptr_t)(job->output + first * QINGYU_COLS + column_base);
                slot = batch_seq & 1u;
                if (first + 8u >= QINGYU_ROWS && tile + 1u < tile_count) {
                    tail_rows = rows; tail_slot = slot; tail_dest = dest;
                    break;
                }
                status = drain_batch(device, result, slot, rows, dest);
                if (status != QINGYU_OK) {
                    goto abort_task;
                }
                ++batch_seq;
                continue;
            }
#endif
            uint32_t status_addr=QINGYU_REG_BATCH_A+4*slot;
            uint32_t count=0;
            if (direct) {
                volatile const uint32_t *ready_reg=(volatile const uint32_t *)(device->base+status_addr);
                uint32_t left=device->poll_limit;
                do { count=*ready_reg; } while(!count && --left);
            } else {
                for (uint32_t poll=0; !count && poll<device->poll_limit; ++poll)
                    count=read_register(device,status_addr);
            }
            if (count != rows*QINGYU_LANES/QINGYU_OUT_PER_WORD) {
                result->hardware_error=read_register(device,QINGYU_REG_ERROR);
                status=count ? QINGYU_ERR_HARDWARE : QINGYU_ERR_TIMEOUT;
                goto abort_task;
            }
            qingyu_fence();
#ifdef QINGYU_READ_AHEAD
            uint32_t port=0x28u+slot*4u;
#else
            uint32_t offset=QINGYU_OUTPUT_OFFSET + slot*512;
#endif
            if (direct && ((uintptr_t)(job->output+first*QINGYU_COLS+column_base)&QINGYU_OUT_ALIGN_MASK)==0 &&
                (uintptr_t)job->output>=0xa0000000u && (uintptr_t)job->output<=0xa0067400u) {
                write_register(device,slot ? 0x40u : 0x3cu,
                    (uint32_t)(uintptr_t)(job->output+first*QINGYU_COLS+column_base));
            } else for (row=0; row<rows; ++row) {
                qingyu_out_t *dst=job->output+(first+row)*QINGYU_COLS+column_base;
#ifdef QINGYU_READ_AHEAD
#ifdef QINGYU_BLOCK_COPY
                uintptr_t destination=(uintptr_t)dst;
                if (direct && !(destination & 63u) && destination>=0xa0000000u &&
                    destination<=0xa007ffc0u) {
                    write_register(device,0x30u+4*slot,(uint32_t)destination);
                    continue;
                }
#endif
                if (direct) {
                    volatile const uint32_t *src=(volatile const uint32_t *)(device->base+port);
                    for (lane=0;lane<QINGYU_LANES;++lane) dst[lane]=(int32_t)*src;
                } else {
                    for (lane=0;lane<QINGYU_LANES;++lane) dst[lane]=(int32_t)read_register(device,port);
                }
#else
                uint32_t addr=offset+4*row*QINGYU_LANES;
                if (direct) {
                    volatile const packed_word *src=(volatile const packed_word *)(device->base+addr);
                    for (lane=0;lane<QINGYU_LANES;lane+=4)
                        copy_four((packed_word *)dst+lane,src+lane);
                } else {
                    for (lane=0;lane<QINGYU_LANES;++lane)
                        dst[lane]=(int32_t)read_register(device,addr+4*lane);
                }
#endif
            }
            qingyu_fence();
            write_register(device,status_addr,1);
#if QINGYU_IL_ACTIVE
            for (uint32_t n = 0u; n < QINGYU_IL_PER_BATCH && chunk < chunk_end; ++n, ++chunk)
                stage_chunk(device, weight_base, stage_pair, chunk);
            if (deferred_weight && chunk >= chunk_end) {
                write_register(device,0x80u,
                    (uint32_t)(uintptr_t)(job->weights + column_base + QINGYU_LANES));
                deferred_weight = 0;
            }
#endif
        }
#if QINGYU_IL_ACTIVE
        while (chunk < chunk_end)
            stage_chunk(device, weight_base, stage_pair, chunk++);
        if (deferred_weight) {
            write_register(device,0x80u,
                (uint32_t)(uintptr_t)(job->weights + column_base + QINGYU_LANES));
        }
#endif
#endif
        status = wait_for_tile(device, result);
        if (status != QINGYU_OK) {
            goto abort_task;
        }
        result->last_output_count = read_register(device,
                                                  QINGYU_REG_OUTPUT_COUNT);
        if (result->last_output_count != QINGYU_TILE_OUTPUTS) {
            status = QINGYU_ERR_OUTPUT_COUNT;
            goto abort_task;
        }
        result->compute_cycles_sum += read_register(device,
                                                    QINGYU_REG_CYCLES);

#ifndef QINGYU_DOUBLE_BUFFER
        qingyu_fence();
#ifdef QINGYU_FAST_TASK
        if (direct) {
            volatile const packed_word *src = (volatile const packed_word *)(device->base + QINGYU_OUTPUT_OFFSET);
            packed_word *dst = (packed_word *)job->output + column_base;
            for (row = 0; row < QINGYU_ROWS; ++row) {
                for (lane=0; lane<QINGYU_LANES; lane+=4)
                    copy_four(dst+row*QINGYU_COLS+lane,src+row*QINGYU_LANES+lane);
            }
        } else
#endif
        for (row = 0u; row < QINGYU_ROWS; ++row) {
            for (lane = 0u; lane < QINGYU_LANES; ++lane) {
                uint32_t output_index = row * QINGYU_COLS + column_base + lane;
                uint32_t tile_index = row * QINGYU_LANES + lane;
                job->output[output_index] = (int32_t)read_register(
                    device, QINGYU_OUTPUT_OFFSET + tile_index * 4u);
            }
        }
#endif
        ++result->completed_tiles;
    }
    status = QINGYU_OK;
    goto finished;

abort_task:
    /* Preserve the recorded failure before aborting the hardware. A failed
     * task is never reported as a successful timing/accuracy measurement.
     */
    (void)qingyu_reset(device);

finished:
    qingyu_fence();
    if (device->read_ticks != NULL) {
        result->elapsed_ticks = device->read_ticks(device->context) - start_ticks;
        result->timing_valid = (status == QINGYU_OK) ? 1u : 0u;
    }
    return status;
}

int qingyu_run(const qingyu_device *device, const qingyu_job *job,
              qingyu_result *result)
{
    return run_task(device, job, result, 1);
}

int qingyu_run_prepared(const qingyu_device *device, const qingyu_job *job,
                        qingyu_result *result)
{
    return run_task(device, job, result, 0);
}
