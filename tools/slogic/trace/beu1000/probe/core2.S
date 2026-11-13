/* BE-U1000 silicon probe, Core 2 (BM-310): code in its TCMB @ 0x40008000 (Core 0 view:
 * 0x70010000), results in its TCMA @ 0x40007800 (Core 0 view: 0x7000F800):
 *  +0 magic (written last), +4 misa, +8 mtvec readback, +0xc mcause of mnstatus read
 *  +0x10 probes {addr, value, mcause}
 */
	.option norvc
	.equ RES, 0x40007800

	.macro PROBE base, off, addr
	li	s11, 0
	li	t1, 0
	li	t0, \addr
	sw	t0, \off(\base)
	lw	t1, 0(t0)
	sw	t1, \off+4(\base)
	sw	s11, \off+8(\base)
	.endm

	.text
	.globl _start
_start:
	la	t0, trap
	csrw	mtvec, t0
	li	s0, RES
	csrr	t0, misa
	sw	t0, 4(s0)
	csrr	t0, mtvec
	sw	t0, 8(s0)
	li	s11, 0
	csrr	t1, 0x744
	sw	s11, 0xc(s0)
	PROBE	s0, 0x10, 0x4000A014	/* TRACE_SEL */
	PROBE	s0, 0x1c, 0x4000A010	/* Software JTAG */
	PROBE	s0, 0x28, 0x4000A000	/* PIO */
	PROBE	s0, 0x34, 0x4000A400	/* mailbox (Core 2 view) */
	PROBE	s0, 0x40, 0x15104000	/* trace encoder */
	PROBE	s0, 0x4c, 0x15106000	/* PIB */
	PROBE	s0, 0x58, 0x70000000	/* SRAM */
	PROBE	s0, 0x64, 0x40000000	/* Core 2 ROM */
	li	t0, 0xC0DE0002
	sw	t0, 0(s0)
1:	wfi
	j	1b

	.balign 64
trap:
	csrr	s11, mcause
	csrr	t6, mepc
	addi	t6, t6, 4
	csrw	mepc, t6
	mret
