/*
 * CH32H417 UHSIF register map, reconstructed from libUHSIF.a behaviour
 * (see doc/ch32h417-uhsif.md). Names are ours; field meanings are hypotheses
 * until checked on hardware.
 */
#ifndef UHSIF_REGS_H
#define UHSIF_REGS_H

#include <stdint.h>

#define UHSIF_REG(off)          (*(volatile uint32_t *)(0x40038000u + (off)))

/* 76 configuration words loaded from the vendor table by UHSIF_Cfg */
#define UHSIF_CFG_WORDS         76u
#define UHSIF_CFG(i)            UHSIF_REG(4u * (i))

#define UHSIF_CTRL              UHSIF_REG(0x000)   /* [31] run, [4] cleared on start, [3] PCLK polarity */
#define UHSIF_CTRL_RUN          (1u << 31)
#define UHSIF_CTRL_BIT4         (1u << 4)
#define UHSIF_CTRL_CLK_POL      (1u << 3)
#define UHSIF_BUS               UHSIF_REG(0x004)   /* [20] data-out edge, [3:2] width */
#define UHSIF_BUS_DOUT_POL      (1u << 20)
#define UHSIF_BUS_WIDTH_SHIFT   2u
#define UHSIF_BUS_KEEP          0xFFEFFFF3u
#define UHSIF_INT_FLAG          UHSIF_REG(0x014)   /* [11+n] line n interrupt */
#define UHSIF_INT_LINE(n)       (1u << (11u + (n)))
#define UHSIF_REG_SOC_FIX       11u                /* word 11: [11:8] cleared in slave-SOC mode */
#define UHSIF_LINE_CFG          UHSIF_REG(0x024)   /* written after the table load, per mode */

/* line n control: [31] enable, [30] dir (1 = OUT), [29:16] watermark,
 * [10] always 1, [7] !dir, [4:0] current socket */
#define UHSIF_LINE(n)           UHSIF_REG(0x0FCu + 4u * (n))
#define UHSIF_LINE_EN           (1u << 31)
#define UHSIF_LINE_DIR_OUT      (1u << 30)
#define UHSIF_LINE_WM_SHIFT     16u
#define UHSIF_LINE_ONE          (1u << 10)
#define UHSIF_LINE_NDIR         (1u << 7)
#define UHSIF_LINE_SOCK_MASK    0x1Fu
#define UHSIF_LINE_KEEP         0x0000FF7Fu

#define UHSIF_GLOBAL_EN0        UHSIF_REG(0x118)
#define UHSIF_GLOBAL_EN1        UHSIF_REG(0x11C)
#define UHSIF_TRANSITION(i)     UHSIF_REG(0x180u + 4u * (i))

/* sockets: sock = buf * 4 + line */
#define UHSIF_SOCK_BASE(s)      (0x40039000u + ((uint32_t)(s) << 6))
#define UHSIF_SOCK(s, off)      (*(volatile uint32_t *)(UHSIF_SOCK_BASE(s) + (off)))
#define UHSIF_SOCK_DSCR(s)      UHSIF_SOCK(s, 0x00)   /* [15:0] descriptor address >> 5 */
#define UHSIF_SOCK_DSCR_FLAGS   0x06010000u
#define UHSIF_SOCK_SIZE(s)      UHSIF_SOCK(s, 0x04)
#define UHSIF_SOCK_COUNT(s)     UHSIF_SOCK(s, 0x08)   /* bytes transferred */
#define UHSIF_SOCK_MODE(s)      UHSIF_SOCK(s, 0x0C)   /* [31] armed, [30] re-arm pulse */
#define UHSIF_SOCK_MODE_IN      0x8C000000u
#define UHSIF_SOCK_MODE_OUT     0x05000000u
#define UHSIF_SOCK_ARM          (1u << 31)
#define UHSIF_SOCK_REARM        (1u << 30)
#define UHSIF_SOCK_STATUS(s)    UHSIF_SOCK(s, 0x10)   /* event flags, write 1 to clear */
#define UHSIF_SOCK_ST_BIT0      0x001u
#define UHSIF_SOCK_ST_40        0x040u
#define UHSIF_SOCK_ST_80        0x080u
#define UHSIF_SOCK_ST_100       0x100u
#define UHSIF_SOCK_START        0x1C1u                /* UHSIF_Start: first IN buffer */
#define UHSIF_SOCK_INTEN(s)     UHSIF_SOCK(s, 0x14)
#define UHSIF_SOCK_INTEN_IN     0x0C0u
#define UHSIF_SOCK_INTEN_OUT    0x180u
#define UHSIF_SOCK_INTEN_FPGA   0x001u

/* microcode banks: step k = 3 words in each bank */
#define UHSIF_WAVE_A(k, j)      (*(volatile uint32_t *)(0x4003A000u + 16u * (k) + 4u * (j)))
#define UHSIF_WAVE_B(k, j)      (*(volatile uint32_t *)(0x4003B000u + 16u * (k) + 4u * (j)))

/* DMA descriptor, 32 bytes, must live in 0x20000000..0x201FFFFF */
typedef struct {
    uint32_t addr;   /* buffer */
    uint32_t dir;    /* 0 = IN, 1 = OUT */
    uint32_t next;   /* own address >> 5: one-element ring */
    uint32_t len;    /* [31:16] transfer length, [15:0] buffer size */
    uint32_t rsvd[4];
} uhsif_dscr_t;

#define UHSIF_DSCR_WINDOW       0x20000000u
#define UHSIF_DSCR_PTR_MASK     0x001FFFE0u

/* outside the block */
#define UHSIF_AFIO_PCFR1        (*(volatile uint32_t *)0x40010000u)  /* [9:8] port remap, [7:6] clk remap */
#define UHSIF_AFIO_REMAP_MASK   0x000003C0u
#define UHSIF_RCC_CFGR_DIV      (*(volatile uint32_t *)0x40021030u)  /* [5:0] UHSIF clock divider */
#define UHSIF_PFIC_IENR4        (*(volatile uint32_t *)0xE000E110u)
#define UHSIF_PFIC_IRER4        (*(volatile uint32_t *)0xE000E190u)
#define UHSIF_IRQ_BIT           (1u << (145u - 128u))
#define UHSIF_RCC_HB_EN         0x00040000u   /* RCC_UHSIFEN */
#define UHSIF_RCC_HB2_GPIO      0x000000FDu   /* AFIO + GPIOA..F */

#endif
