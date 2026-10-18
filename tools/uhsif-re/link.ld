MEMORY { FLASH (rx) : ORIGIN = 0x00010000, LENGTH = 64K  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 64K }
SECTIONS {
  .text : { *(.text*) *(.rodata*) } > FLASH
  .data : { *(.data*) *(.sdata*) } > RAM
  .bss  : { *(.bss*) *(.sbss*) *(COMMON) } > RAM
}
