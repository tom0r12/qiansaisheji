#include "qingyu_accel.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int16_t input[99 * 64];
static int16_t weights[64 * 256];
static int64_t bias[256];
static uint8_t shifts[256];
static int32_t output[99 * 256];

typedef struct {
    qingyu_job *job;
    uintptr_t base;
    unsigned writes, input_words, weight_words, meta_words;
    unsigned starts, resets, out_reads, ticks, status_polls;
    uint32_t tile, status, id;
    int mode;
} fake_soc;

static int32_t expected(uint32_t row, uint32_t col)
{
    return (int32_t)(row * 256u + col) - 100000;
}

static uint32_t read32(void *opaque, uintptr_t address)
{
    fake_soc *soc = (fake_soc *)opaque;
    uint32_t off = (uint32_t)(address - soc->base);
    if (off == QINGYU_REG_ID) return soc->id;
    if (off == QINGYU_REG_STATUS) {
        if (soc->status == QINGYU_STATUS_BUSY) {
            ++soc->status_polls;
            if (soc->mode == 1) return QINGYU_STATUS_BUSY;
            if (soc->mode == 2) return QINGYU_STATUS_ERROR;
            if (soc->status_polls >= 2u) soc->status = QINGYU_STATUS_DONE;
        }
        return soc->status;
    }
    if (off == QINGYU_REG_ERROR) return 0x17u;
    if (off == QINGYU_REG_OUTPUT_COUNT)
        return soc->mode == 3 ? 395u : QINGYU_TILE_OUTPUTS;
    if (off == QINGYU_REG_CYCLES) return 1234u;
    if (off >= QINGYU_OUTPUT_OFFSET &&
        off < QINGYU_OUTPUT_OFFSET + QINGYU_TILE_OUTPUTS * 4u) {
        uint32_t index = (off - QINGYU_OUTPUT_OFFSET) / 4u;
        ++soc->out_reads;
        assert(soc->status == QINGYU_STATUS_DONE);
        return (uint32_t)expected(index / 4u, soc->tile + index % 4u);
    }
    assert(!"unexpected read");
    return 0;
}

static void write32(void *opaque, uintptr_t address, uint32_t value)
{
    fake_soc *soc = (fake_soc *)opaque;
    uint32_t off = (uint32_t)(address - soc->base);
    ++soc->writes;
    assert(soc->ticks == 1u);
    if (off == QINGYU_REG_CONTROL) {
        if (value == QINGYU_CONTROL_RESET) {
            ++soc->resets;
            soc->status = 0;
        } else if (value == QINGYU_CONTROL_CLEAR) {
            soc->status = 0;
            soc->weight_words = 0;
            soc->meta_words = 0;
        } else if (value == QINGYU_CONTROL_START) {
            assert(soc->input_words == 3168u);
            assert(soc->weight_words == 128u);
            assert(soc->meta_words == 8u);
            soc->status = QINGYU_STATUS_BUSY;
            soc->status_polls = 0;
            ++soc->starts;
        } else assert(!"unexpected control");
        return;
    }
    if (off == QINGYU_REG_LAYER_ID) {
        assert(value == soc->job->layer_id);
        return;
    }
    if (off == QINGYU_REG_TILE_BASE) {
        assert(value == soc->starts * 4u);
        soc->tile = value;
        return;
    }
    if (off >= QINGYU_INPUT_OFFSET && off < QINGYU_INPUT_OFFSET + 12672u) {
        uint32_t i = (off - QINGYU_INPUT_OFFSET) / 2u;
        uint32_t pack = (uint32_t)(uint16_t)soc->job->input[i]
            | ((uint32_t)(uint16_t)soc->job->input[i + 1u] << 16);
        assert(value == pack);
        ++soc->input_words;
        return;
    }
    if (off >= QINGYU_WEIGHT_OFFSET && off < QINGYU_WEIGHT_OFFSET + 512u) {
        uint32_t i = (off - QINGYU_WEIGHT_OFFSET) / 2u;
        uint32_t source = (i / 4u) * 256u + soc->tile + i % 4u;
        uint32_t pack = (uint32_t)(uint16_t)soc->job->weights[source]
            | ((uint32_t)(uint16_t)soc->job->weights[source + 1u] << 16);
        assert(value == pack);
        ++soc->weight_words;
        return;
    }
    if (off >= QINGYU_META_OFFSET && off < QINGYU_META_OFFSET + 32u) {
        uint32_t lane = (off - QINGYU_META_OFFSET) / 8u;
        uint32_t col = soc->tile + lane;
        uint64_t raw = (uint64_t)soc->job->bias[col] & UINT64_C(0xffffffffffff);
        uint32_t word = ((off - QINGYU_META_OFFSET) % 8u) == 0u
            ? (uint32_t)raw
            : (uint32_t)(raw >> 32) | ((uint32_t)soc->job->shift[col] << 16);
        assert(value == word);
        ++soc->meta_words;
        return;
    }
    assert(!"unexpected write");
}

static uint64_t ticks(void *opaque)
{
    fake_soc *soc = (fake_soc *)opaque;
    if (soc->ticks == 0u) assert(soc->writes == 0u);
    ++soc->ticks;
    if (soc->ticks == 2u && soc->mode == 0 && soc->starts == 64u)
        assert(soc->job->output[99u * 256u - 1u] == expected(98u, 255u));
    return (uint64_t)soc->ticks * 100u;
}

static void prepare(fake_soc *soc, qingyu_device *dev, qingyu_job *job)
{
    memset(soc, 0, sizeof(*soc));
    memset(output, 0, sizeof(output));
    soc->job = job;
    soc->base = 0x10000000u;
    soc->id = QINGYU_ID_VALUE;
    qingyu_init(dev, soc->base, 10u);
    dev->context = soc;
    dev->read32 = read32;
    dev->write32 = write32;
    dev->read_ticks = ticks;
}

int main(void)
{
    qingyu_device dev;
    qingyu_job job;
    qingyu_result result;
    fake_soc soc;
    uint32_t i;
    for (i = 0; i < 99u * 64u; ++i)
        input[i] = (int16_t)((int32_t)(i % 1000u) - 500);
    for (i = 0; i < 64u * 256u; ++i)
        weights[i] = (int16_t)((int32_t)(i % 997u) - 498);
    for (i = 0; i < 256u; ++i) {
        bias[i] = ((i & 1u) ? -INT64_C(1099511627776) : INT64_C(1099511627776))
            + (int64_t)i;
        shifts[i] = (uint8_t)(i % 48u);
    }
    job.input = input; job.weights = weights; job.bias = bias; job.shift = shifts;
    job.output = output; job.rows = 99; job.k = 64; job.cols = 256; job.layer_id = 11;
    prepare(&soc, &dev, &job);
    assert(qingyu_run(&dev, &job, &result) == QINGYU_OK);
    assert(soc.starts == 64u && soc.resets == 1u && soc.input_words == 3168u);
    assert(soc.out_reads == 25344u && result.completed_tiles == 64u);
    assert(result.compute_cycles_sum == UINT64_C(1234) * 64u);
    assert(result.elapsed_ticks == 100u && result.timing_valid == 1u);
    for (i = 0; i < 99u * 256u; ++i)
        assert(output[i] == expected(i / 256u, i % 256u));
    puts("PASS full 64-tile packing, negative bias, output layout, timing boundaries");

    prepare(&soc, &dev, &job); shifts[255] = 48;
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_FORMAT && soc.writes == 0u);
    shifts[255] = 15;
    prepare(&soc, &dev, &job); bias[255] = INT64_C(140737488355328);
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_FORMAT && soc.writes == 0u);
    bias[255] = 0;
    prepare(&soc, &dev, &job); job.rows = 98;
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_DIMENSIONS && soc.writes == 0u);
    job.rows = 99;
    prepare(&soc, &dev, &job); job.input = (const int16_t *)((uintptr_t)input + 1u);
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_ALIGNMENT && soc.writes == 0u);
    job.input = input;
    prepare(&soc, &dev, &job); job.output = (int32_t *)(void *)weights;
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_BUFFER_OVERLAP && soc.writes == 0u);
    job.output = output;
    prepare(&soc, &dev, &job); soc.id = 0u;
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_DEVICE_ID && soc.writes == 0u);
    puts("PASS preflight range, dimensions, alignment, overlap and ID reject before writes");

    prepare(&soc, &dev, &job); soc.mode = 1;
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_TIMEOUT);
    assert(result.completed_tiles == 0u && soc.resets == 2u && !result.timing_valid);
    prepare(&soc, &dev, &job); soc.mode = 2;
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_HARDWARE);
    assert(result.hardware_error == 0x17u && soc.resets == 2u && !result.timing_valid);
    prepare(&soc, &dev, &job); soc.mode = 3;
    assert(qingyu_run(&dev, &job, &result) == QINGYU_ERR_OUTPUT_COUNT);
    assert(result.last_output_count == 395u && soc.resets == 2u);
    puts("PASS finite timeout, hardware error, output-count failure and abort reset");
    return 0;
}
