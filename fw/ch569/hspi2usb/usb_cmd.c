/********************************** (C) COPYRIGHT *******************************
* File Name          : usb_cmd.c
* Author             : bvernoux
* Version            : V1.0
* Date               : 2022/08/20
* Description 		 :
* Copyright (c) 2022 Benjamin VERNOUX
* SPDX-License-Identifier: Apache-2.0
*
* rln-trace: fork of hydrausb3_fw 88879fa HydraUSB3_USB/User/usb_cmd.c with the
*            bridge commands SRCH, SRCI, STAT (bridge.h).
*******************************************************************************/
#include "CH56x_common.h"
#include "CH56x_usb20_devbulk.h"
#include "CH56x_usb30_devbulk.h"
#include "CH56x_usb30_devbulk_LIB.h"

#include "CH56x_debug_log.h"
#include "usb_cmd.h"
#include "bridge.h" // rln-trace

static int usb_cmd_val_last = 0;

extern debug_log_buf_t log_buf;
char cmd_usb_info_buf[CMD_USB_INFO_BUF_SIZE+1];

/*******************************************************************************
 * @fn     usb_cmd_rx
 *
 * @brief  Callback called by USB2 & USB3 endpoint 1
 *         - For USB3 this usb_cmd_rx() is called from IRQ(USBHS_IRQHandler)
 *           with rx_usb_dma_buff containing 4096 bytes (DEF_ENDP1_MAX_SIZE)
 *         - For USB2 this usb_cmd_rx() is called from IRQ USB30_IRQHandler->EP1_OUT_Callback)
 *           with rx_usb_dma_buff containing 4096 bytes (DEF_ENDP1_MAX_SIZE)
 *
 * @param  usb_type: USB Type (USB2 HS or USB3 SS)
 * @param  rx_usb_dma_buff: USB RX DMA buffer containing 4096 bytes of data
 *                          Data received from USB
 * @param  tx_usb_dma_buff: USB TX DMA buffer containing 4096 bytes of data
 *                          Data to be transmitted over USB
 *
 * @return None
 */
void usb_cmd_rx(e_usb_type usb_type, uint8_t* rx_usb_dma_buff, uint8_t* tx_usb_dma_buff)
{
	uint32_t* cmd = (uint32_t*)(rx_usb_dma_buff);

	uint32_t cmd_val = cmd[0];
	switch(cmd_val)
	{
		case USB_CMD_LOGR:
		{
			usb_cmd_val_last = USB_CMD_LOGR;
			log_printf("cmd LOGR\n");
			memcpy(tx_usb_dma_buff, log_buf.buf, log_buf.idx); // Copy log_buff to endp1Tbuff for next receive EP1_IN_Callback
			tx_usb_dma_buff[log_buf.idx] = 0; // Add end of string
			/* Reset Log buffer index to 0 */
			log_buf.idx = 0;
		}
		break;

		case USB_CMD_USBS:
		{
			usb_cmd_val_last = USB_CMD_USBS;
			if(usb_type == USB_TYPE_USB3)
			{
				log_printf("cmd USBS USB3\n");
				snprintf(cmd_usb_info_buf, CMD_USB_INFO_BUF_SIZE, "USBS USB3:\n"
						 "LINK_STATUS=0x%08X\n"
						 "LINK_ERR_STATUS=0x%08X\n"
						 "LINK_ERR_CNT=0x%08X",
						 USBSS->LINK_STATUS,
						 USBSS->LINK_ERR_STATUS,
						 USBSS->LINK_ERR_CNT);
			}
			else
			{
				log_printf("cmd USBS USB2\n");
				if((R8_USB_SPD_TYPE & RB_USBSPEED_MASK) == 1)
				{
					snprintf(cmd_usb_info_buf, CMD_USB_INFO_BUF_SIZE, "USBS USB2:\n"
							 "USB2 SPEED=%d (0=FS,1=HS,2=LS)\nTest end with success\n",
							 (R8_USB_SPD_TYPE & RB_USBSPEED_MASK));
				}
				else
				{
					snprintf(cmd_usb_info_buf, CMD_USB_INFO_BUF_SIZE, "USBS USB2:\n"
							 "USB2 SPEED=%d (0=FS,1=HS,2=LS)\nTest failure end with error\n",
							 (R8_USB_SPD_TYPE & RB_USBSPEED_MASK));
				}
			}
			memcpy(tx_usb_dma_buff, cmd_usb_info_buf, DEF_ENDP1_MAX_SIZE); // Copy cmd_usb_info_buf to endp1Tbuff for next receive EP1_IN_Callback
		}
		break;

		case USB_CMD_USB2:
		{
			usb_cmd_val_last = USB_CMD_USB2;
			log_printf("cmd USB2\n");
			if(usb_type == USB_TYPE_USB3)
			{
				log_printf("Force USB2\n");
				USB2_force();
			}
		}
		break;

		case USB_CMD_USB3:
		{
			usb_cmd_val_last = USB_CMD_USB3;
			log_printf("cmd USB3\n");
			if(usb_type == USB_TYPE_USB2)
			{
				log_printf("Force USB3\n");
				USB3_force();
			}
		}
		break;

		/* rln-trace: bridge */
		case USB_CMD_SRCH:
		case USB_CMD_SRCI:
		{
			usb_cmd_val_last = cmd_val;
			bridge_set_source(cmd_val == USB_CMD_SRCI ? SRC_INTERNAL : SRC_HSPI);
			snprintf((char *)tx_usb_dma_buff, CMD_USB_INFO_BUF_SIZE, "source %s\n",
					 bridge_source() == SRC_INTERNAL ? "internal" : "hspi");
		}
		break;

		case USB_CMD_STAT:
		{
			usb_cmd_val_last = USB_CMD_STAT;
			snprintf((char *)tx_usb_dma_buff, CMD_USB_INFO_BUF_SIZE,
					 "source %s\n"
					 "hspi_packets %lu\n"
					 "hspi_crc_err %lu\n"
					 "hspi_num_mis %lu\n"
					 "hspi_fifo_ov %lu\n"
					 "dropped %lu\n"
					 "usb_blocks %lu\n"
					 "last_usdf 0x%07lX\n"
					 "pool_free %u\n"
					 "queued %u\n",
					 bridge_source() == SRC_INTERNAL ? "internal" : "hspi",
					 (unsigned long)bridge_stats.hspi_packets,
					 (unsigned long)bridge_stats.hspi_crc_err,
					 (unsigned long)bridge_stats.hspi_num_mis,
					 (unsigned long)bridge_stats.hspi_fifo_ov,
					 (unsigned long)bridge_stats.dropped,
					 (unsigned long)bridge_stats.usb_blocks,
					 (unsigned long)bridge_stats.last_usdf,
					 bridge_pool_free(), bridge_queued());
		}
		break;

		case USB_CMD_BOOT: /* Reboot (execute reset) */
		{
			SYS_ResetExecute();
		}
		break;

		default:
			log_printf("CMD UNKN\n");
	}
}
