#include <stdint.h>

/* Original E203 GPIOA/B pads and APB GPIO controller; internal peripheral DMA
   copies GPIOA words into shared SRAM over the original System Bus. The CPU
   publishes the acknowledged prefix to the engine while the copy runs. */
#define REG(off) (*(volatile uint32_t *)(uintptr_t)(0xf0000000u+(off)))
#define GPIOA(off) (*(volatile uint32_t *)(uintptr_t)(0x10012000u+(off)))
#define GPIOB(off) (*(volatile uint32_t *)(uintptr_t)(0x10040000u+(off)))
#define HOST (*(volatile uint32_t *)(uintptr_t)0xf0010000u)
#define SOURCE_BASE 0xa0040000u
#define OUTPUT_BASE 0xa0000000u
#define TASK_EPOCH 1u
#define PACKET_WORDS 8850u
#define HEADER_WORDS 10u
static void fence(void) { __asm__ volatile("fence rw,rw":::"memory"); }
static uint64_t cycles(void) {
    uint32_t hi,lo,again;
    do {
        __asm__ volatile("csrr %0,mcycleh":"=r"(hi));
        __asm__ volatile("csrr %0,mcycle":"=r"(lo));
        __asm__ volatile("csrr %0,mcycleh":"=r"(again));
    } while(hi!=again);
    return ((uint64_t)hi<<32)|lo;
}
static int fail(uint32_t code) { HOST=code;return (int)code; }
int main(void) {
    if(REG(0)!=0x51313231u)return fail(0x101u);
    uint64_t begin=cycles();
    /* Full task timing begins here, before GPIO configuration or payload. */
    REG(8)=SOURCE_BASE;fence();
    /* Original APB GPIO layout: DIR+0, IN+4, OUT+8, IOFCFG+0x1c.
       A[31:0]=data, B[0]=READY input, B[1]=REQ, B[9:2]=burst length; IOFs off. */
    GPIOA(0)=0u;GPIOA(0x1c)=0u;
    GPIOB(0)=0u;GPIOB(0x1c)=0u;GPIOB(8)=0u;fence();
    GPIOB(0)=0x3feu;fence();
    REG(12)=OUTPUT_BASE;REG(0x38)=TASK_EPOCH;REG(0x40)=TASK_EPOCH;REG(0x34)=PACKET_WORDS;fence();
    /* One peripheral-DMA copy of the whole packet (non-blocking). */
    REG(0x80)=SOURCE_BASE;REG(0x84)=PACKET_WORDS;fence();
    uint32_t done;
    do { done=REG(0x8c); } while(done<HEADER_WORDS);
    volatile const uint32_t *source=(volatile const uint32_t *)(uintptr_t)SOURCE_BASE;
    if(source[0]!=0x32583151u)return fail(0x111u);
    if(source[1]!=76032u)return fail(0x112u);
    for(uint32_t group=0;group<8u;group++) if(source[2u+group]!=24576u)return fail(0x113u);
    REG(0x3c)=done;fence();REG(4)=1;fence();
    uint32_t published=done;
    while(published<PACKET_WORDS) {
        done=REG(0x8c);
        if(done!=published){REG(0x3c)=done;published=done;}
    }
    fence();
    if(REG(0x88)!=0u)return fail(0x180u);
    uint32_t status=REG(0x14);
    uint64_t elapsed=cycles()-begin;
    if((status&7u)!=2u)return fail(0x200u|(status<<16));
    volatile const uint32_t *output=(volatile const uint32_t *)(uintptr_t)OUTPUT_BASE;
    if(output[0]!=0x32443151u)return fail(0x103u);
    for(uint32_t i=1;i<=16u;i++)if(output[i]!=1584u)return fail(0x104u);
    volatile uint32_t *diagnostics=(volatile uint32_t *)(uintptr_t)0xa0030000u;
    diagnostics[0]=(uint32_t)elapsed;diagnostics[1]=(uint32_t)(elapsed>>32);
    diagnostics[2]=REG(0x18);diagnostics[3]=status;fence();HOST=1;
    return 0;
}
