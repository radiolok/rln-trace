// Источник для прозвонки SLogic16U3 на STM32F4-Discovery: счётчик n на выводах,
// бит k (канал SLogic CHk) переключается f/2^k раз в секунду, f = 16 МГц / 32 = 500 кГц.
//   CH0..CH7 — PD0..PD7, CH8..CH15 — PE0..PE7; биты 8 и 9 дублируются на PE8, PE9.
// Такт — HSI после сброса (16 МГц, ±1 %), шаг цикла отмеряет SysTick (DWT
// отладчик при подключении сбрасывает, SysTick — нет).
// Зелёный PD12 мигает ~1 Гц — прошивка идёт. На PE0/PE1 платы — выходы INT1/INT2
// акселерометра: если вывод не следует за подтяжкой, его кто-то держит, он
// остаётся входом, горит красный PD14; тогда CH8/CH9 брать с PE8/PE9.
#include <stdint.h>

#define REG(a) (*(volatile uint32_t *)(a))
#define RCC_AHB1ENR REG(0x40023830)
#define GPIOD 0x40020C00
#define GPIOE 0x40021000
#define MODER 0x00
#define OSPEEDR 0x08
#define PUPDR 0x0C
#define IDR 0x10
#define ODR 0x14
#define SYST_CSR REG(0xE000E010)
#define SYST_RVR REG(0xE000E014)
#define SYST_CVR REG(0xE000E018)
#define DEMCR REG(0xE000EDFC)
#define DWT_CTRL REG(0xE0001000)
#define DWT_CYCCNT REG(0xE0001004)

#define STEP 32

static void wait(uint32_t cycles)
{
    uint32_t t = DWT_CYCCNT;
    while (DWT_CYCCNT - t < cycles)
        ;
}

// 1, если вывод PEi идёт за подтяжкой вверх и вниз (никто его не держит)
static int free_pin(int i)
{
    REG(GPIOE + PUPDR) = (REG(GPIOE + PUPDR) & ~(3u << 2 * i)) | 1u << 2 * i;
    wait(16000);
    int up = REG(GPIOE + IDR) >> i & 1;
    REG(GPIOE + PUPDR) = (REG(GPIOE + PUPDR) & ~(3u << 2 * i)) | 2u << 2 * i;
    wait(16000);
    int down = REG(GPIOE + IDR) >> i & 1;
    REG(GPIOE + PUPDR) &= ~(3u << 2 * i);
    return up && !down;
}

void reset(void)
{
    RCC_AHB1ENR |= (1u << 3) | (1u << 4);  // GPIOD, GPIOE
    (void)RCC_AHB1ENR;
    DEMCR |= 1u << 24;  // TRCENA
    DWT_CYCCNT = 0;
    DWT_CTRL |= 1u;

    uint32_t emode = 0x5550, red = 0;  // PE2..PE7 свободны всегда
    for (int i = 0; i < 2; i++) {
        if (free_pin(i))
            emode |= 1u << 2 * i;
        else
            red = 1u << 14;
    }
    REG(GPIOE + MODER) = (REG(GPIOE + MODER) & 0xFFF00000u) | 0x50000u | emode;  // + PE8, PE9
    REG(GPIOE + OSPEEDR) |= 0x55555u;
    REG(GPIOD + MODER) = (REG(GPIOD + MODER) & 0xCCFF0000u) | 0x11005555u;  // PD0..7, PD12, PD14
    REG(GPIOD + OSPEEDR) |= 0x5555u;

    SYST_RVR = STEP - 1;
    SYST_CVR = 0;
    SYST_CSR = 5;  // такт процессора, без прерывания
    uint32_t n = 0;
    for (;;) {
        while (!(SYST_CSR & 1u << 16))  // COUNTFLAG, сбрасывается чтением
            ;
        n++;
        REG(GPIOD + ODR) = (n & 0xFFu) | ((n >> 18) & 1u) << 12 | red;
        REG(GPIOE + ODR) = ((n >> 8) & 0xFFu) | (n & 0x300u);
    }
}

extern uint32_t _estack;
__attribute__((section(".vectors"), used))
const void *vectors[2] = {&_estack, (void *)reset};
