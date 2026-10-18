/*
 * Open driver for the CH32H417 UHSIF block.
 *
 * Drop-in replacement for WCH libUHSIF.a: same functions, same UHSIF_Para layout, same error
 * codes. The configuration tables (76 register words, timing-generator microcode) are WCH data
 * and are not in this repository: tools/uhsif-re/extract_tables.py generates uhsif_tables.c
 * from your copy of libUHSIF.a.
 *
 * Differences from the library, all on invalid input only:
 *   - UHSIF_Line_Cfg rejects line_num 4 (the library accepts 0..4 and overruns Stu[]);
 *   - UHSIF_Trans_Cfg checks line_num and trans_size <= Socket_Size.
 */
#ifndef UHSIF_H
#define UHSIF_H

#include <stdint.h>

#define DEF_UHSIF_SLAVE_FPGA_MODE         0
#define DEF_UHSIF_SLAVE_SOC_MODE          1
#define DEF_UHSIF_MASTER_MODE             2

#define DEF_UHSIF_PINREMAP0               0   /* QFN128 */
#define DEF_UHSIF_PINREMAP1               1   /* QFN56/68 */
#define DEF_UHSIF_PINREMAP2               2   /* QFN88 */
#define DEF_UHSIF_CLKREMAP0               0   /* PCLK on PF11 */
#define DEF_UHSIF_CLKREMAP1               1   /* PC0 */
#define DEF_UHSIF_CLKREMAP2               2   /* PF14 */
#define DEF_UHSIF_CLKREMAP3               3   /* PD9 */

#define DEF_UHSIF_DATA_BIT8               0
#define DEF_UHSIF_DATA_BIT16              1
#define DEF_UHSIF_DATA_BIT24              2
#define DEF_UHSIF_DATA_BIT32              3

#define DEF_LINE_COUNT_MAX                4
#define DEF_LINE_DIR_IN                   0
#define DEF_LINE_DIR_OUT                  1
#define DEF_BUFF_COUNT_MAX                8

#ifndef DEF_BUFF_SIZE
#define DEF_BUFF_SIZE                     16384
#endif

#ifndef DEF_SLAVE_DOUT_POLARITY
#define DEF_SLAVE_DOUT_POLARITY           1   /* data out on rising edge */
#endif
#ifndef DEF_SLAVE_CLK_POLARITY
#define DEF_SLAVE_CLK_POLARITY            0   /* clock not inverted */
#endif
#ifndef DEF_MASTER_DOUT_POLARITY
#define DEF_MASTER_DOUT_POLARITY          1
#endif
#ifndef DEF_MASTER_CLK_POLARITY
#define DEF_MASTER_CLK_POLARITY           1
#endif

#define DEF_UHSIF_SUCESS                  0x00
#define DEF_UHSIF_GPIO_CFG_ERR            0xA1
#define DEF_UHSIF_REG_ADDR_ERR            0xA2
#define DEF_UHSIF_REG_CFG_ERR             0xA3
#define DEF_UHSIF_REG_GET_ERR             0xA4
#define DEF_UHSIF_MODE_ERR                0xA5
#define DEF_UHSIF_WR_LIMIT_ERR            0xA7
#define DEF_UHSIF_DIV_ERR                 0xA8
#define DEF_UHSIF_DATA_OVER_ERR           0xA9
#define DEF_LINE_ENABLE_ERR               0xB1
#define DEF_LINE_OVER_ERR                 0xB2
#define DEF_LINE_DIR_ERR                  0xB3
#define DEF_BUFF_OVER_ERR                 0xC1
#define DEF_DESC_OVER_ERR                 0xD1

typedef struct
{
    volatile uint8_t Thread_Enable;
    volatile uint8_t Thread_Dir;
    volatile uint8_t Socket_Count;
    volatile uint8_t UHSIF_First_Send;
    volatile uint32_t Water_Mark_Value;
} UHSIF_Stu_t;

typedef struct
{
    UHSIF_Stu_t Stu[4];
    volatile uint8_t Slave_Dout_Polarity;
    volatile uint8_t Slave_Clk_Polarity;
    volatile uint8_t Master_Dout_Polarity;
    volatile uint8_t Master_Clk_Polarity;
    volatile uint32_t Socket_Size;
    volatile uint32_t TX_Buff_Size;
    volatile uint32_t RX_Buff_Size;
    volatile uint8_t Mode;
    volatile uint8_t Width_Bit;
    volatile uint8_t thread_max;
} UHSIF_Para_t;

extern UHSIF_Para_t UHSIF_Para;

uint8_t UHSIF_Get_Ver(void);
uint8_t UHSIF_GPIO_Init(uint8_t mode_select, uint8_t uhsif_port_rm, uint8_t uhsif_clk_rmm,
                        uint8_t clk_div, uint8_t width_bit);
void    UHSIF_Cfg(void);
uint8_t UHSIF_Line_Cfg(uint8_t line_num, uint8_t line_dir, uint8_t buff_count, uint8_t *pbuf,
                       uint16_t water_mark_value);
void    UHSIF_Start(uint8_t sta);   /* FunctionalState: 0 = DISABLE */
uint8_t UHSIF_Trans_Cfg(uint8_t line_num, uint8_t buff_cur, uint32_t trans_size);
uint8_t UHSIF_Reg_Cfg(uint8_t mode, uint8_t reg_addr, uint32_t value);
void    UHSIF_IRQHandler(void);

/* user callbacks, called from UHSIF_IRQHandler */
void UHSIF_Line0_IN_Callback(uint32_t rcv_count);
void UHSIF_Line1_IN_Callback(uint32_t rcv_count);
void UHSIF_Line2_IN_Callback(uint32_t rcv_count);
void UHSIF_Line3_IN_Callback(uint32_t rcv_count);
void UHSIF_Line0_OUT_Callback(void);
void UHSIF_Line1_OUT_Callback(void);
void UHSIF_Line2_OUT_Callback(void);
void UHSIF_Line3_OUT_Callback(void);

/* configuration tables, generated from libUHSIF.a (uhsif_tables.c) */
typedef struct {
    const uint32_t *regs;        /* UHSIF_CFG_WORDS words */
    const uint8_t  *position;    /* microcode program: one dictionary index per step */
    uint32_t        steps;
    const uint32_t *wavedata;    /* dictionary, 6 words per entry */
    const uint16_t *transition;
    uint32_t        transitions;
} uhsif_mode_tables_t;

extern const uhsif_mode_tables_t uhsif_tables[3];   /* indexed by DEF_UHSIF_*_MODE */

#endif
