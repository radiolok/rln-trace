/*
 * Open driver for the CH32H417 UHSIF block. Register sequence matches libUHSIF.a V1
 * (checked access by access in the Unicorn spike: tools/uhsif-re/compare.py).
 */
#include <stddef.h>

#include "uhsif.h"
#include "uhsif_regs.h"

#ifdef UHSIF_NO_STDPERIPH
/* host test build: the subset of the WCH StdPeriph API the driver uses */
typedef struct GPIO_TypeDef GPIO_TypeDef;
typedef uint32_t GPIOSpeed_TypeDef;
typedef uint32_t GPIOMode_TypeDef;
typedef struct {
    uint16_t GPIO_Pin;
    GPIOSpeed_TypeDef GPIO_Speed;
    GPIOMode_TypeDef GPIO_Mode;
} GPIO_InitTypeDef;
typedef int FunctionalState;
void *memset(void *s, int c, size_t n);
void GPIO_Init(GPIO_TypeDef *GPIOx, GPIO_InitTypeDef *GPIO_InitStruct);
void RCC_HBPeriphClockCmd(uint32_t periph, FunctionalState state);
void RCC_HB2PeriphClockCmd(uint32_t periph, FunctionalState state);
void RCC_HBPeriphResetCmd(uint32_t periph, FunctionalState state);
#ifndef UHSIF_IRQ_ATTR
#define UHSIF_IRQ_ATTR __attribute__((interrupt("machine")))
#endif
#else
#include <string.h>
#include "ch32h417.h"
/* WCH GCC: hardware-stacked fast interrupt; other compilers: -DUHSIF_IRQ_ATTR=... */
#ifndef UHSIF_IRQ_ATTR
#define UHSIF_IRQ_ATTR __attribute__((interrupt("WCH-Interrupt-fast")))
#endif
#endif

UHSIF_Para_t UHSIF_Para;

/* DMA descriptors: [line * 8 + buf], must stay in 0x20000000..0x201FFFFF */
uhsif_dscr_t uhsif_dscr_in[32] __attribute__((aligned(32)));
uhsif_dscr_t uhsif_dscr_out[32] __attribute__((aligned(32)));

/* ------------------------------------------------------------------ pins */

enum { PA, PB, PC, PD, PE, PF };
#define PIN(port, n)    ((uint8_t)((port) << 4 | (n)))

/* UHSIF_PORT0..47 -> pin, datasheet V1.8 table 2-2-16, UHSIF_PORT_RM = 00 */
static const uint8_t port_pin[48] = {
    PIN(PF, 12), PIN(PF, 13), PIN(PE, 7),  PIN(PE, 8),  PIN(PE, 9),  PIN(PE, 10), PIN(PE, 11), PIN(PE, 12),
    PIN(PE, 13), PIN(PE, 14), PIN(PE, 15), PIN(PB, 10), PIN(PB, 11), PIN(PB, 12), PIN(PB, 13), PIN(PB, 14),
    PIN(PD, 10), PIN(PD, 11), PIN(PD, 12), PIN(PD, 13), PIN(PD, 14), PIN(PD, 15), PIN(PF, 0),  PIN(PF, 1),
    PIN(PF, 2),  PIN(PC, 6),  PIN(PC, 7),  PIN(PC, 8),  PIN(PC, 9),  PIN(PA, 13), PIN(PA, 14), PIN(PA, 15),
    PIN(PC, 10), PIN(PC, 11), PIN(PC, 12), PIN(PD, 0),  PIN(PD, 1),  PIN(PD, 2),  PIN(PD, 3),  PIN(PD, 4),
    PIN(PD, 5),  PIN(PD, 6),  PIN(PD, 7),  PIN(PF, 3),  PIN(PF, 4),  PIN(PF, 5),  PIN(PE, 0),  PIN(PE, 1),
};
/* PORT0..7 for UHSIF_PORT_RM = 01 (QFN56/68) and 1x (QFN88) */
static const uint8_t port_pin_rm[2][8] = {
    { PIN(PF, 12), PIN(PF, 13), PIN(PE, 7), PIN(PC, 1), PIN(PC, 2), PIN(PC, 3),  PIN(PB, 0),  PIN(PB, 1) },
    { PIN(PC, 1),  PIN(PC, 2),  PIN(PC, 3), PIN(PB, 0), PIN(PB, 1), PIN(PE, 10), PIN(PE, 11), PIN(PE, 12) },
};
static const uint8_t clk_pin[4] = { PIN(PF, 11), PIN(PC, 0), PIN(PF, 14), PIN(PD, 9) };

/* GPIO modes as libUHSIF sets them. The block appears to take the pins over by itself: in
 * master mode PCLK and every control output are left as plain push-pull GPIO outputs. */
#define M_AF_PP   0x18u
#define M_IPD     0x28u
#define M_IPU     0x48u
#define M_OUT_PP  0x10u
#define SPEED_VH  3u

enum { K_AF, K_IPD, K_IPU, K_OUT, K_N };
static const uint32_t kind_mode[K_N] = { M_AF_PP, M_IPD, M_IPU, M_OUT_PP };

/* control signals: UHSIF_PORT number, kind as slave, kind as master */
static const struct { uint8_t port, slave, master; } ctrl[] = {
    { 3,  K_IPD, K_OUT },   /* SEL0 */
    { 4,  K_IPD, K_OUT },   /* SEL1 */
    { 5,  K_IPU, K_IPU },   /* AF#: input pull-up in every mode, as in the library */
    { 7,  K_OUT, K_IPD },   /* AE# */
    { 8,  K_IPU, K_OUT },   /* EOP# */
    { 9,  K_OUT, K_IPD },   /* WRNF */
    { 11, K_OUT, K_IPD },   /* RDNE */
    { 12, K_IPU, K_OUT },   /* RD# */
    { 13, K_IPU, K_OUT },   /* OE# */
    { 14, K_IPU, K_OUT },   /* WR# */
    { 15, K_IPU, K_OUT },   /* CS# */
};

static uint8_t pin_of(uint8_t port_rm, uint8_t n)
{
    if (n < 8 && port_rm != 0)
        return port_pin_rm[port_rm == 1 ? 0 : 1][n];
    return port_pin[n];
}

static void pins_apply(uint16_t mask[6][K_N])
{
    for (unsigned port = 0; port < 6; port++)
        for (unsigned k = 0; k < K_N; k++) {
            if (!mask[port][k])
                continue;
            GPIO_InitTypeDef g;
            g.GPIO_Pin = mask[port][k];
            g.GPIO_Speed = (GPIOSpeed_TypeDef)SPEED_VH;
            g.GPIO_Mode = (GPIOMode_TypeDef)kind_mode[k];
            GPIO_Init((GPIO_TypeDef *)(0x40010800u + 0x400u * port), &g);
        }
}

static void pin_add(uint16_t mask[6][K_N], uint8_t pin, unsigned kind)
{
    mask[pin >> 4][kind] |= (uint16_t)(1u << (pin & 15));
}

uint8_t UHSIF_Get_Ver(void)
{
    return 1;
}

uint8_t UHSIF_GPIO_Init(uint8_t mode_select, uint8_t uhsif_port_rm, uint8_t uhsif_clk_rmm,
                        uint8_t clk_div, uint8_t width_bit)
{
    if (mode_select > 2 || uhsif_port_rm > 2 || uhsif_clk_rmm > 3)
        return DEF_UHSIF_GPIO_CFG_ERR;
    if (clk_div > 0x3F)
        return DEF_UHSIF_DIV_ERR;
    if (width_bit > 3)
        return DEF_UHSIF_DATA_OVER_ERR;

    memset((void *)&UHSIF_Para, 0, sizeof(UHSIF_Para));
    UHSIF_Para.thread_max = DEF_LINE_COUNT_MAX;
    UHSIF_Para.Width_Bit = width_bit;
    RCC_HBPeriphClockCmd(UHSIF_RCC_HB_EN, 1);
    RCC_HB2PeriphClockCmd(UHSIF_RCC_HB2_GPIO, 1);

    uint16_t mask[6][K_N] = { { 0 } };
    unsigned data_pins = 8u * (width_bit + 1u);
    for (unsigned i = 0; i < data_pins; i++)
        pin_add(mask, port_pin[16 + i], K_AF);
    int master = mode_select == DEF_UHSIF_MASTER_MODE;
    pin_add(mask, clk_pin[uhsif_clk_rmm], master ? K_OUT : K_IPD);
    for (unsigned i = 0; i < sizeof(ctrl) / sizeof(ctrl[0]); i++)
        pin_add(mask, pin_of(uhsif_port_rm, ctrl[i].port), master ? ctrl[i].master : ctrl[i].slave);
    pins_apply(mask);
    UHSIF_Para.Mode = mode_select;

    if (master) {
        UHSIF_RCC_CFGR_DIV &= ~0x3Fu;
        UHSIF_RCC_CFGR_DIV |= clk_div;
    }
    UHSIF_AFIO_PCFR1 &= ~UHSIF_AFIO_REMAP_MASK;
    UHSIF_AFIO_PCFR1 |= (uint32_t)uhsif_port_rm << 8 | (uint32_t)uhsif_clk_rmm << 6;
    return DEF_UHSIF_SUCESS;
}

/* ------------------------------------------------------------------ config */

void UHSIF_Cfg(void)
{
    UHSIF_Para.Socket_Size = DEF_BUFF_SIZE;
    UHSIF_Para.TX_Buff_Size = DEF_BUFF_SIZE;
    UHSIF_Para.RX_Buff_Size = DEF_BUFF_SIZE;
    UHSIF_Para.Slave_Dout_Polarity = DEF_SLAVE_DOUT_POLARITY;
    UHSIF_Para.Slave_Clk_Polarity = DEF_SLAVE_CLK_POLARITY;
    UHSIF_Para.Master_Dout_Polarity = DEF_MASTER_DOUT_POLARITY;
    UHSIF_Para.Master_Clk_Polarity = DEF_MASTER_CLK_POLARITY;

    uint8_t mode = UHSIF_Para.Mode;
    if (mode > DEF_UHSIF_MASTER_MODE)
        return;
    const uhsif_mode_tables_t *t = &uhsif_tables[mode];
    int master = mode == DEF_UHSIF_MASTER_MODE;
    uint32_t clk_pol = master ? UHSIF_Para.Master_Clk_Polarity : UHSIF_Para.Slave_Clk_Polarity;
    uint32_t dout_pol = master ? UHSIF_Para.Master_Dout_Polarity : UHSIF_Para.Slave_Dout_Polarity;

    for (unsigned i = 0; i < UHSIF_CFG_WORDS; i++) {
        uint32_t v = t->regs[i];
        if (i == 0)
            v = (v & ~UHSIF_CTRL_CLK_POL) | clk_pol << 3;
        else if (i == 1)
            v = (v & UHSIF_BUS_KEEP) | dout_pol << 20 | (uint32_t)UHSIF_Para.Width_Bit << UHSIF_BUS_WIDTH_SHIFT;
        else if (i == UHSIF_REG_SOC_FIX && mode == DEF_UHSIF_SLAVE_SOC_MODE)
            v &= 0xFFFFF0FFu;
        UHSIF_CFG(i) = v;
    }

    uint32_t line_cfg;
    if (mode == DEF_UHSIF_SLAVE_FPGA_MODE)
        line_cfg = 0x00111100u;
    else if (mode == DEF_UHSIF_SLAVE_SOC_MODE)
        line_cfg = 0x00011100u;
    else if (UHSIF_Para.thread_max == 1)
        line_cfg = 0x00004055u;
    else if (UHSIF_Para.thread_max == 2)
        line_cfg = 0x01004055u;
    else
        line_cfg = 0x01404055u;
    UHSIF_LINE_CFG = line_cfg;

    for (uint32_t k = 0; k < t->steps; k++) {
        const uint32_t *row = &t->wavedata[6u * t->position[k]];
        for (unsigned j = 0; j < 3; j++) {
            UHSIF_WAVE_A(k, j) = row[j];
            UHSIF_WAVE_B(k, j) = row[3 + j];
        }
    }
    for (uint32_t i = 0; i < t->transitions; i++)
        UHSIF_TRANSITION(i) = t->transition[i];
}

static void sock_init(uint32_t sock, uint8_t dir)
{
    UHSIF_SOCK_DSCR(sock) |= UHSIF_SOCK_DSCR_FLAGS;
    UHSIF_SOCK_SIZE(sock) = UHSIF_Para.Socket_Size;
    UHSIF_SOCK_COUNT(sock) = 0;
    if (dir == DEF_LINE_DIR_OUT) {
        UHSIF_SOCK_MODE(sock) |= UHSIF_SOCK_MODE_OUT;
        UHSIF_SOCK_INTEN(sock) = UHSIF_SOCK_INTEN_OUT;
    } else {
        UHSIF_SOCK_MODE(sock) |= UHSIF_SOCK_MODE_IN;
        UHSIF_SOCK_INTEN(sock) = UHSIF_SOCK_INTEN_IN;
        if (UHSIF_Para.Mode == DEF_UHSIF_SLAVE_FPGA_MODE)
            UHSIF_SOCK_INTEN(sock) |= UHSIF_SOCK_INTEN_FPGA;
    }
}

uint8_t UHSIF_Line_Cfg(uint8_t line_num, uint8_t line_dir, uint8_t buff_count, uint8_t *pbuf,
                       uint16_t water_mark_value)
{
    if (line_num >= DEF_LINE_COUNT_MAX)
        return DEF_LINE_OVER_ERR;
    if (line_dir > DEF_LINE_DIR_OUT)
        return DEF_LINE_DIR_ERR;
    if (buff_count > DEF_BUFF_COUNT_MAX)
        return DEF_BUFF_OVER_ERR;
    if (pbuf == NULL)
        return DEF_UHSIF_REG_ADDR_ERR;

    UHSIF_Stu_t *stu = &UHSIF_Para.Stu[line_num];
    stu->Thread_Enable = 1;
    stu->Thread_Dir = line_dir;
    stu->Socket_Count = buff_count;
    stu->Water_Mark_Value = water_mark_value;

    uhsif_dscr_t *d = (line_dir == DEF_LINE_DIR_OUT ? uhsif_dscr_out : uhsif_dscr_in) + 8u * line_num;
    uint32_t step = line_dir == DEF_LINE_DIR_OUT ? UHSIF_Para.TX_Buff_Size : UHSIF_Para.RX_Buff_Size;
    for (uint32_t buf = 0; buf < buff_count; buf++, d++) {
        uint32_t sock = buf * 4u + line_num;
        d->next = (uint32_t)(uintptr_t)d >> 5;
        d->dir = line_dir;
        d->addr = (uint32_t)(uintptr_t)pbuf + step * buf;
        d->len = UHSIF_Para.Socket_Size << 16 | UHSIF_Para.Socket_Size;
        UHSIF_SOCK_DSCR(sock) = ((uint32_t)(uintptr_t)d >> 5) & 0xFFFFu;
        sock_init(sock, line_dir);
    }

    /* line register: socket 0 of the line, flags; same OR-into-old update as the library */
    UHSIF_LINE(line_num) &= UHSIF_LINE_KEEP;
    UHSIF_LINE(line_num) |= stu->Water_Mark_Value << UHSIF_LINE_WM_SHIFT
                          | (uint32_t)(stu->Thread_Dir == 0) << 7
                          | (uint32_t)stu->Thread_Dir << 30
                          | (uint32_t)stu->Thread_Enable << 31;
    UHSIF_SOCK_MODE(0) |= UHSIF_SOCK_ARM;   /* the library always arms socket 0 here */
    return DEF_UHSIF_SUCESS;
}

void UHSIF_Start(uint8_t sta)
{
    if (sta) {
        for (int i = 0; i < 16; i++)
            __asm__ volatile("nop");
        UHSIF_GLOBAL_EN0 |= 1u;
        UHSIF_GLOBAL_EN1 |= 1u;
        if (UHSIF_Para.Mode != DEF_UHSIF_MASTER_MODE) {
            UHSIF_CTRL &= ~UHSIF_CTRL_RUN;
            UHSIF_CTRL &= ~UHSIF_CTRL_BIT4;
            UHSIF_CTRL |= UHSIF_CTRL_RUN;
        }
        UHSIF_SOCK_STATUS(0) |= UHSIF_SOCK_START;
        UHSIF_PFIC_IENR4 = UHSIF_IRQ_BIT;
    } else {
        UHSIF_PFIC_IRER4 = UHSIF_IRQ_BIT;
        __asm__ volatile("fence" ::: "memory");
        RCC_HBPeriphResetCmd(UHSIF_RCC_HB_EN, 1);
        RCC_HBPeriphResetCmd(UHSIF_RCC_HB_EN, 0);
        RCC_HBPeriphClockCmd(UHSIF_RCC_HB_EN, 0);
        memset((void *)UHSIF_Para.Stu, 0, sizeof(UHSIF_Para.Stu));
    }
}

uint8_t UHSIF_Trans_Cfg(uint8_t line_num, uint8_t buff_cur, uint32_t trans_size)
{
    if (line_num >= DEF_LINE_COUNT_MAX)
        return DEF_LINE_OVER_ERR;
    UHSIF_Stu_t *stu = &UHSIF_Para.Stu[line_num];
    if (!stu->Thread_Enable)
        return DEF_LINE_ENABLE_ERR;
    if (buff_cur >= stu->Socket_Count)
        return DEF_DESC_OVER_ERR;

    uint32_t size = UHSIF_Para.Socket_Size;
    uint32_t sock = (buff_cur & 7u) * 4u + line_num;
    if (stu->Thread_Dir == DEF_LINE_DIR_OUT) {
        if (trans_size > size)
            return DEF_UHSIF_DATA_OVER_ERR;
        uhsif_dscr_t *d = &uhsif_dscr_out[8u * line_num + buff_cur];
        if (stu->UHSIF_First_Send < stu->Socket_Count) {
            stu->UHSIF_First_Send++;
            d->len = trans_size << 16 | size;
            UHSIF_SOCK_MODE(sock) |= UHSIF_SOCK_ARM;
            return DEF_UHSIF_SUCESS;
        }
        UHSIF_SOCK_COUNT(sock) = 0;
        d->len = trans_size << 16 | size;
    } else {
        if (UHSIF_SOCK_COUNT(sock) < size) {
            uintptr_t a = UHSIF_DSCR_WINDOW | ((UHSIF_SOCK_DSCR(sock) << 5) & UHSIF_DSCR_PTR_MASK);
            ((uhsif_dscr_t *)a)->len = size << 16 | size;
        }
        UHSIF_SOCK_COUNT(sock) = 0;
    }
    UHSIF_SOCK_MODE(sock) |= UHSIF_SOCK_REARM;
    UHSIF_SOCK_MODE(sock) &= ~UHSIF_SOCK_REARM;
    return DEF_UHSIF_SUCESS;
}

uint8_t UHSIF_Reg_Cfg(uint8_t mode, uint8_t reg_addr, uint32_t value)
{
    if (mode > DEF_UHSIF_MASTER_MODE)
        return DEF_UHSIF_MODE_ERR;
    if (reg_addr >= UHSIF_CFG_WORDS)
        return DEF_UHSIF_WR_LIMIT_ERR;
    UHSIF_CFG(reg_addr) = value;
    return UHSIF_CFG(reg_addr) == value ? DEF_UHSIF_SUCESS : DEF_UHSIF_REG_CFG_ERR;
}

/* ------------------------------------------------------------------ interrupt */

static void (*const out_cb[4])(void) = {
    UHSIF_Line0_OUT_Callback, UHSIF_Line1_OUT_Callback, UHSIF_Line2_OUT_Callback, UHSIF_Line3_OUT_Callback,
};
static void (*const in_cb[4])(uint32_t) = {
    UHSIF_Line0_IN_Callback, UHSIF_Line1_IN_Callback, UHSIF_Line2_IN_Callback, UHSIF_Line3_IN_Callback,
};

UHSIF_IRQ_ATTR void UHSIF_IRQHandler(void)
{
    uint32_t flags = UHSIF_INT_FLAG;
    unsigned line = 0;
    uint32_t cur = 0, next = 0;
    uint8_t dir = DEF_LINE_DIR_IN;
    while (line < DEF_LINE_COUNT_MAX && !(flags & UHSIF_INT_LINE(line)))
        line++;
    if (line < DEF_LINE_COUNT_MAX) {
        cur = UHSIF_LINE(line) & UHSIF_LINE_SOCK_MASK;
        next = (cur + 4u) & UHSIF_LINE_SOCK_MASK;
        dir = UHSIF_Para.Stu[line].Thread_Dir;
    } else {
        line = 0;   /* no flag: the library still services line 0, socket 0, as IN */
    }

    uint32_t st = UHSIF_SOCK_STATUS(cur);
    if (!(st & UHSIF_SOCK_ST_BIT0)) {
        UHSIF_Stu_t *stu = &UHSIF_Para.Stu[line];
        UHSIF_LINE(line) = (uint32_t)stu->Thread_Dir << 30 | stu->Water_Mark_Value << UHSIF_LINE_WM_SHIFT
                         | (uint32_t)(stu->Thread_Dir == 0) << 7 | next
                         | UHSIF_LINE_EN | UHSIF_LINE_ONE;
    }
    if (st & UHSIF_SOCK_ST_80) {
        UHSIF_SOCK_STATUS(cur) |= UHSIF_SOCK_ST_80;
    } else if (st & UHSIF_SOCK_ST_40) {
        UHSIF_SOCK_STATUS(cur) |= UHSIF_SOCK_ST_40;
        if (st & UHSIF_SOCK_ST_BIT0)
            UHSIF_SOCK_STATUS(cur) |= UHSIF_SOCK_ST_BIT0;
    } else if (st & UHSIF_SOCK_ST_100) {
        UHSIF_SOCK_STATUS(cur) |= UHSIF_SOCK_ST_100;
    }

    if (dir == DEF_LINE_DIR_OUT)
        out_cb[line]();
    else
        in_cb[line](UHSIF_SOCK_COUNT(cur));
}
