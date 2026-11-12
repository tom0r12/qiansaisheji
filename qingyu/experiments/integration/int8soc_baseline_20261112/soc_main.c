#include <stdint.h>

#define REG(off) (*(volatile uint32_t *)(uintptr_t)(0xf0000000u+(off)))
#define HOST (*(volatile uint32_t *)(uintptr_t)0xf0010000u)
static uint64_t cycles(void) {
    uint32_t hi,lo,again;
    do {
        __asm__ volatile("csrr %0,mcycleh":"=r"(hi));
        __asm__ volatile("csrr %0,mcycle":"=r"(lo));
        __asm__ volatile("csrr %0,mcycleh":"=r"(again));
    } while(hi!=again);
    return ((uint64_t)hi<<32)|lo;
}
int main(void) {
    if(REG(0)!=0x51385231u){HOST=0x101u;return 1;}
    uint64_t begin=cycles();
    REG(8)=0xa0040000u;
    REG(12)=0xa0000000u;
    __asm__ volatile("fence rw,rw":::"memory");
    REG(4)=1;
    uint32_t status=REG(0x14); /* One blocking wait; all DMA ACKs drain first. */
    uint64_t elapsed=cycles()-begin;
    if((status&7u)!=2u){HOST=0x200u|(status<<16);return 2;}
    volatile const uint32_t *output=(volatile const uint32_t *)(uintptr_t)0xa0000000u;
    if(output[0]!=0x31593851u){HOST=0x103u;return 3;}
    for(uint32_t i=1;i<=16;i++) {
        uint32_t bits=output[i];
        if(bits==0||bits>12722){HOST=0x104u;return 4;}
    }
    volatile uint32_t *diagnostics=(volatile uint32_t *)(uintptr_t)0xa0030000u;
    diagnostics[0]=(uint32_t)elapsed;
    diagnostics[1]=(uint32_t)(elapsed>>32);
    diagnostics[2]=REG(0x18);
    diagnostics[3]=status;
    __asm__ volatile("fence rw,rw":::"memory");
    HOST=1;
    return 0;
}
