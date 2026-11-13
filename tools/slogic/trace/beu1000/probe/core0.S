/* BE-U1000 silicon probe, Core 0 (EVU-BA-2.5): code in TCMA @ 0x40010000 (SRAM is not
 * executable), results in SRAM @ 0x70000000:
 *  +0x000 magic, +0x004 misa, +0x008 ntrig, +0x010 mtvec after writing direct mode
 *  +0x014/+0x018 mnstatus read: value, mcause
 *  +0x020 trig[i] x4: tselect, tinfo (| mcause<<24), tdata1 after mcontrol, after mcontrol6
 *  +0x0e0 first fault (0x30000000, before touching mnstatus) {addr, value, mcause}
 *  +0x100 probes {addr, value, mcause}; +0x2fc done
 */
	.option norvc
	.equ RES, 0x70000000

	.macro PROBE base, off, addr
	li	s11, 0
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
	csrr	t0, mhartid
	li	t1, 2
	beq	t0, t1, core2
	li	s0, RES
	li	t0, 0xC0FFEE00
	sw	t0, 0(s0)
	sw	zero, 0x300(s0)
	csrr	t0, misa
	sw	t0, 4(s0)
	csrr	t0, mtvec
	sw	t0, 0x10(s0)		/* mtvec readback (direct requested) */
	PROBE	s0, 0xe0, 0x30000000	/* first fault BEFORE touching mnstatus */
	li	s11, 0
	li	t1, 0
	csrr	t1, 0x744		/* mnstatus */
	sw	t1, 0x14(s0)
	sw	s11, 0x18(s0)

	/* triggers */
	li	s1, 0			/* i */
	addi	s2, s0, 0x20
trig_loop:
	li	t0, 8
	beq	s1, t0, trig_done
	li	s11, 0
	csrw	tselect, s1
	csrr	t1, tselect
	bnez	s11, trig_done
	bne	t1, s1, trig_done
	sw	t1, 0(s2)
	li	s11, 0
	li	t1, 0
	csrr	t1, tinfo
	slli	t2, s11, 24
	or	t1, t1, t2
	sw	t1, 4(s2)
	li	s11, 0
	li	t0, 0x200008C4		/* mcontrol: chain, match=1(napot), M, exec */
	csrw	tdata1, t0
	csrr	t1, tdata1
	sw	t1, 8(s2)
	li	t0, 0x20000000
	csrw	tdata1, t0		/* clear before next type */
	li	t0, 0x60000044		/* mcontrol6: M, exec */
	csrw	tdata1, t0
	csrr	t1, tdata1
	sw	t1, 12(s2)
	li	t0, 0x60000000		/* type6, no modes = off */
	csrw	tdata1, t0
	addi	s1, s1, 1
	addi	s2, s2, 16
	j	trig_loop
trig_done:
	sw	s1, 8(s0)

	/* core0 MMIO probes */
	addi	s3, s0, 0x100
	PROBE	s3, 0x00, 0x15104000	/* trace encoder */
	PROBE	s3, 0x0c, 0x15105000	/* trace RAM ctl */
	PROBE	s3, 0x18, 0x15106000	/* PIB */
	PROBE	s3, 0x24, 0x15107000	/* trace SRAM */
	PROBE	s3, 0x30, 0x11000000	/* QSPI0 / CORE2_* stubs */
	PROBE	s3, 0x3c, 0x15103000	/* mailbox */
	PROBE	s3, 0x48, 0x151037f0	/* CORE2_INT stub */
	PROBE	s3, 0x54, 0x00000000	/* core debug */
	PROBE	s3, 0x60, 0x02020000	/* bus error unit */
	PROBE	s3, 0x6c, 0x0D000000	/* CLIC */
	PROBE	s3, 0x78, 0x4000A014	/* core0 view of 0x4000A014 */
	PROBE	s3, 0x84, 0x15108000	/* bus matrix */
done:	li	t0, 0xD0E0D0E0
	sw	t0, 0x2fc(s0)
1:	wfi
	j	1b

core2:
	li	s0, RES
	addi	s3, s0, 0x300
	csrr	t0, misa
	sw	t0, 4(s3)
	PROBE	s3, 0x08, 0x4000A014	/* TRACE_SEL */
	PROBE	s3, 0x14, 0x4000A010	/* Software JTAG */
	PROBE	s3, 0x20, 0x4000A000	/* PIO */
	PROBE	s3, 0x2c, 0x4000A400	/* mailbox core2 */
	PROBE	s3, 0x38, 0x15104000	/* trace encoder */
	li	t0, 0xC0DE0002
	sw	t0, 0(s3)
1:	wfi
	j	1b

	.balign 64
trap:
	csrr	s11, mcause
	csrr	t6, mepc
	addi	t6, t6, 4
	csrw	mepc, t6
	mret
