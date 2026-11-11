/* Integration regression. The second task uses the normal cold-task harness.
 * The first image and its golden output occupy unused upper shared SRAM. */
#define main measured_task_main
#include "../sw/soc_perf_main.c"
#undef main

int main(void)
{
    qingyu_device device;
    qingyu_result result;
    qingyu_init(&device, 0xf0000000u, 1000000u);
    qingyu_job first={
        .input=(const int16_t *)0xa0050000u, .weights=(const int16_t *)0xa0054000u,
        .bias=(const int64_t *)0xa005c000u, .shift=(const uint8_t *)0xa005c800u,
        .output=(int32_t *)0xa0010000u, .rows=99, .k=64, .cols=256, .layer_id=1
    };
    int rc=qingyu_run(&device,&first,&result);
    volatile int32_t *out=first.output;
    volatile const int32_t *golden=(const int32_t *)0xa0060000u;
    for (unsigned i=0; rc==0 && i<99*256; ++i) {
        if(out[i]!=golden[i]) rc=-1;
        out[i]=0x55555555;
    }
    if(rc!=0) {
        *(volatile uint32_t *)0xf0010000u=0xe0000001u;
        return rc;
    }
    return measured_task_main();
}
