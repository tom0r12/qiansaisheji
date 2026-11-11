#include "qingyu_accel.h"

/* SDK-independent example entry, intentionally without a reset/startup main.
 * The board/SoC firmware supplies the actual MMIO base and encoded vectors.
 * Use separately generated X/W/bias/shift for each KWT layer. Passing a
 * synthetic vector here is a functional test, never a KWT accuracy result.
 */
int qingyu_example_run(uintptr_t accel_base, uint32_t layer_id,
                      const int16_t *input, const int16_t *weights,
                      const int64_t *bias, const uint8_t *shift,
                      int32_t *output, qingyu_result *result)
{
    qingyu_device device;
    qingyu_job job;

    /* This is a status-read budget, not a 150 MHz cycle or time guarantee.
     * Tune it for the verified target and measured worst-case tile duration.
     */
    qingyu_init(&device, accel_base, UINT32_C(1000000));
    job.input = input;
    job.weights = weights;
    job.bias = bias;
    job.shift = shift;
    job.output = output;
    job.rows = QINGYU_ROWS;
    job.k = QINGYU_K;
    job.cols = QINGYU_COLS;
    job.layer_id = layer_id;
    return qingyu_run(&device, &job, result);
}
