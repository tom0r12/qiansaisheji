OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY {
 ITCM (rx) : ORIGIN = 0x80000000, LENGTH = 64K
 DTCM (rwx): ORIGIN = 0x90000000, LENGTH = 64K
}
SECTIONS {
 .text : { KEEP(*(.init)) *(.text*) *(.rodata*) . = ALIGN(4); } > ITCM
 .data : { . = ALIGN(4); _sdata = .; *(.sdata*) *(.data*) . = ALIGN(4); _edata = .; } > DTCM AT> ITCM
 _sidata = LOADADDR(.data);
 __global_pointer$ = _sdata + 0x800;
 .bss (NOLOAD) : { . = ALIGN(4); _sbss = .; *(.sbss*) *(.bss*) *(COMMON) . = ALIGN(4); _ebss = .; } > DTCM
 _stack_top = ORIGIN(DTCM) + LENGTH(DTCM);
 ASSERT(_ebss + 4096 <= _stack_top, "DTCM stack space exhausted")
}
