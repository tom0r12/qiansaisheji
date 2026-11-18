.section .init,"ax",@progbits
.globl _start
_start:
  .option push
  .option norelax
  la gp, __global_pointer$
  .option pop
  la sp, _stack_top
  la t0, _sidata
  la t1, _sdata
  la t2, _edata
1:
  bgeu t1,t2,2f
  lw t3,0(t0)
  sw t3,0(t1)
  addi t0,t0,4
  addi t1,t1,4
  j 1b
2:
  la t0,_sbss
  la t1,_ebss
3:
  bgeu t0,t1,4f
  sw zero,0(t0)
  addi t0,t0,4
  j 3b
4:
  la t0,trap
  csrw mtvec,t0
  call main
5:
  j 5b
.balign 64
trap:
  csrr t0,mcause
  li t1,0xf0010000
  li t2,0xe1000000
  or t0,t0,t2
  sw t0,0(t1)
6:
  j 6b
