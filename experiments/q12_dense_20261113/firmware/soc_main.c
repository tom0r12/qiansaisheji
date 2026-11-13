#include <stdint.h>

#define REG(off) (*(volatile uint32_t *)(uintptr_t)(0xf0000000u+(off)))
#define MAIL(off) (*(volatile uint32_t *)(uintptr_t)(0xf0020000u+(off)))
#define HOST (*(volatile uint32_t *)(uintptr_t)0xf0010000u)
#define SOURCE_BASE 0xa0040000u
#define OUTPUT_BASE 0xa0000000u
#define CONTROL_BASE 0xa0030100u
#define TASK_EPOCH 1u
#define CTRL(i) (*(volatile uint32_t *)(uintptr_t)(CONTROL_BASE+4u*(i)))
enum { REQUEST_SEQ, READY_SEQ, READY_WORDS, REQUEST_EPOCH, TOTAL_WORDS, LOAD_ERROR, READY_EPOCH };
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
static int wait_chunk(uint32_t sequence) {
    uint64_t begin=cycles();
    // Public loader readiness follows its final real control-write ACK.
    // Wait on the original FIO path, then verify the actual shared record.
    if(MAIL(12)!=0)return 0; // Bounded hardware WAIT; no repeated MMIO polls.
    for(;;) {
        uint32_t seen=CTRL(READY_SEQ);
        if(CTRL(LOAD_ERROR))return 0;
        if(seen==sequence) {
            fence();
            return CTRL(READY_EPOCH)==TASK_EPOCH;
        }
        if(seen>sequence || cycles()-begin>2000000u)return 0;
    }
}
int main(void) {
    if(REG(0)!=0x51313231u)return fail(0x101u);
    uint64_t begin=cycles();
    MAIL(4)=TASK_EPOCH;fence();
    // These are actual CPU System-Bus stores, not testbench state changes.
    CTRL(REQUEST_SEQ)=0;CTRL(READY_SEQ)=0;CTRL(READY_WORDS)=0;
    CTRL(TOTAL_WORDS)=0;CTRL(LOAD_ERROR)=0;CTRL(READY_EPOCH)=0;
    CTRL(REQUEST_EPOCH)=TASK_EPOCH;fence();CTRL(REQUEST_SEQ)=1;fence();MAIL(8)=1;fence();
    // These idle MMIO writes use the existing FIO path while platform loading
    // uses the existing memory ingress. The full task window already began.
    REG(8)=SOURCE_BASE;REG(12)=OUTPUT_BASE;
    REG(0x38)=TASK_EPOCH;REG(0x40)=TASK_EPOCH;fence();
    if(!wait_chunk(1))return fail(0x110u);
    volatile const uint32_t *source=(volatile const uint32_t *)(uintptr_t)SOURCE_BASE;
    if(source[0]!=0x31513151u)return fail(0x111u);
    uint32_t bits=source[1];
    if(bits==0 || bits>76230u)return fail(0x112u);
    uint32_t boundaries[9],words=330u+(bits+31u)/32u;boundaries[0]=words;
    for(uint32_t group=0;group<8;group++) {
        bits=source[2+group];
        if(bits==0 || bits>24640u)return fail(0x113u);
        words+=(bits+31u)/32u;boundaries[group+1]=words;
    }
    if(words>8873u || CTRL(TOTAL_WORDS)!=words || CTRL(READY_WORDS)!=boundaries[0])return fail(0x114u);
    REG(0x34)=words;REG(0x3c)=boundaries[0];
    fence();REG(4)=1;fence();
    for(uint32_t sequence=2;sequence<=9;sequence++) {
        CTRL(REQUEST_SEQ)=sequence;fence();MAIL(8)=sequence;fence();
        if(!wait_chunk(sequence))return fail(0x120u+sequence);
        if(CTRL(READY_WORDS)!=boundaries[sequence-1] || CTRL(TOTAL_WORDS)!=words)return fail(0x130u+sequence);
        REG(0x3c)=boundaries[sequence-1];fence();
        if(REG(0x3c)!=boundaries[sequence-1])return fail(0x140u+sequence);
        if(REG(0x10)&4u)return fail(0x150u+sequence);
    }
    uint32_t status=REG(0x14); // Blocking WAIT is safe only after final commit.
    uint64_t elapsed=cycles()-begin;
    if((status&7u)!=2u)return fail(0x200u|(status<<16));
    volatile const uint32_t *output=(volatile const uint32_t *)(uintptr_t)OUTPUT_BASE;
    if(output[0]!=0x31443151u)return fail(0x103u);
    for(uint32_t i=1;i<=16;i++)if(output[i]!=25344u)return fail(0x104u);
    volatile uint32_t *diagnostics=(volatile uint32_t *)(uintptr_t)0xa0030000u;
    diagnostics[0]=(uint32_t)elapsed;diagnostics[1]=(uint32_t)(elapsed>>32);
    diagnostics[2]=REG(0x18);diagnostics[3]=status;fence();HOST=1;
    return 0;
}
