/*
 * usbstream: приёмник потока самопроверки fw/ch569/usbstream.
 *
 * Читает EP2 IN через асинхронный libusb, проверяет каждый блок (формат —
 * fw/ch569/usbstream/stream.h) и раз в секунду печатает скорость и ошибки.
 * Код возврата 0 — ни одной ошибки после синхронизации, 1 — были ошибки, 2 — сбой USB.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include <errno.h>
#include <inttypes.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include <libusb.h>

#include "check.h"

#define EP_STREAM 0x82
static volatile sig_atomic_t stop;
static int usb_failed;
static int in_flight;
static struct parser P;
static FILE *dump;

static void on_signal(int sig)
{
	(void)sig;
	stop = 1;
}

static void LIBUSB_CALL on_transfer(struct libusb_transfer *t)
{
	if(t->status == LIBUSB_TRANSFER_COMPLETED) {
		check_parse(&P, t->buffer, t->actual_length);
		if(dump && fwrite(t->buffer, 1, t->actual_length, dump) != (size_t)t->actual_length) {
			fprintf(stderr, "запись в файл: %s\n", strerror(errno));
			stop = 1;
		}
	} else if(t->status != LIBUSB_TRANSFER_CANCELLED && !stop) {
		/* после остановки отменённые передачи через USB/IP иногда приходят как STALL */
		fprintf(stderr, "передача: %s\n", libusb_error_name(t->status));
		usb_failed = 1;
		stop = 1;
	}
	if(!stop && libusb_submit_transfer(t) == 0)
		return;
	in_flight--;
}

static double now(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static const char *speed_name(int s)
{
	switch(s) {
	case LIBUSB_SPEED_LOW: return "USB1 LS";
	case LIBUSB_SPEED_FULL: return "USB1 FS";
	case LIBUSB_SPEED_HIGH: return "USB2 HS";
	case LIBUSB_SPEED_SUPER: return "USB3 SS";
	case LIBUSB_SPEED_SUPER_PLUS: return "USB3 SS+";
	default: return "неизвестна";
	}
}

static void report(const char *tag, double dt, uint64_t dbytes)
{
	printf("%s %8.2f МБ/с  блоков %" PRIu64 " по %u  потеряно %" PRIu64 "  повторов %" PRIu64
	       "  рестартов %" PRIu64 "  испорчено %" PRIu64 " (слов %" PRIu64 ")  рассинхр. %" PRIu64 "\n",
	       tag, dt > 0 ? dbytes / dt / 1e6 : 0.0, P.blocks, P.block_len, P.lost, P.dups,
	       P.restarts, P.bad_blocks, P.bad_words, P.desync);
	fflush(stdout);
}

#define EP_CMD_OUT 0x01
#define EP_CMD_IN  0x81
#define CMD_LEN    4096
#define MAX_CMDS   8

/* EP1 command of the firmware (usb_cmd.c): four letters, read as a little-endian
 * word whose value spells them from the top byte; the answer is text on EP1 IN */
static int send_cmd(libusb_device_handle *h, const char *cmd)
{
	static uint8_t buf[CMD_LEN];
	uint32_t v = (uint32_t)cmd[0] << 24 | (uint32_t)cmd[1] << 16 | (uint32_t)cmd[2] << 8 | (uint32_t)cmd[3];
	int n, r;

	memset(buf, 0, sizeof(buf));
	memcpy(buf, &v, 4);
	if((r = libusb_bulk_transfer(h, EP_CMD_OUT, buf, CMD_LEN, &n, 1000))) {
		fprintf(stderr, "%s: %s\n", cmd, libusb_error_name(r));
		return -1;
	}
	memset(buf, 0, sizeof(buf));
	if((r = libusb_bulk_transfer(h, EP_CMD_IN, buf, CMD_LEN, &n, 1000))) {
		fprintf(stderr, "%s, ответ: %s\n", cmd, libusb_error_name(r));
		return -1;
	}
	buf[CMD_LEN - 1] = 0;
	printf("%s:\n%s%s", cmd, (char *)buf, n && buf[strlen((char *)buf) - 1] == '\n' ? "" : "\n");
	return 0;
}

static void usage(const char *argv0)
{
	fprintf(stderr,
		"Использование: %s [-d VID:PID] [-C КОМАНДА]... [-t сек] [-n передач] [-s КиБ] [-o файл]\n"
		"  -d  устройство, по умолчанию 16c0:05dc\n"
		"  -t  длительность, 0 — до Ctrl+C (по умолчанию 10)\n"
		"  -n  передач в очереди (по умолчанию 16)\n"
		"  -s  размер передачи в КиБ, кратно 4 (по умолчанию 256)\n"
		"      все передачи вместе не больше usbfs_memory_mb (обычно 16 МБ)\n"
		"  -o  сохранить сырой поток в файл\n"
		"  -C  команда EP1 до приёма (до %d): SRCI, SRCH, STAT (hspi2usb), USBS, LOGR;\n"
		"      без -t после команд приёма нет\n", argv0, MAX_CMDS);
}

int main(int argc, char **argv)
{
	unsigned vid = 0x16c0, pid = 0x05dc;
	double duration = 10;
	int nxfer = 16, xfer_kib = 256, opt, rc = 2;
	const char *dump_path = NULL;
	const char *cmds[MAX_CMDS];
	int ncmds = 0, t_set = 0;

	while((opt = getopt(argc, argv, "d:t:n:s:o:C:h")) != -1) {
		switch(opt) {
		case 'd':
			if(sscanf(optarg, "%x:%x", &vid, &pid) != 2) {
				usage(argv[0]);
				return 2;
			}
			break;
		case 't': duration = atof(optarg); t_set = 1; break;
		case 'C':
			if(strlen(optarg) != 4 || ncmds == MAX_CMDS) {
				usage(argv[0]);
				return 2;
			}
			cmds[ncmds++] = optarg;
			break;
		case 'n': nxfer = atoi(optarg); break;
		case 's': xfer_kib = atoi(optarg); break;
		case 'o': dump_path = optarg; break;
		default: usage(argv[0]); return 2;
		}
	}
	if(nxfer < 1 || xfer_kib < 4 || xfer_kib % 4) {
		usage(argv[0]);
		return 2;
	}

	libusb_context *ctx;
	libusb_device_handle *h = NULL;
	struct libusb_transfer **xfers = calloc(nxfer, sizeof(*xfers));
	int r = libusb_init(&ctx);
	if(r) {
		fprintf(stderr, "libusb_init: %s\n", libusb_error_name(r));
		return 2;
	}
	h = libusb_open_device_with_vid_pid(ctx, vid, pid);
	if(!h) {
		fprintf(stderr, "устройство %04x:%04x не найдено или нет доступа\n", vid, pid);
		goto out;
	}
	libusb_set_auto_detach_kernel_driver(h, 1);
	if((r = libusb_claim_interface(h, 0))) {
		fprintf(stderr, "claim_interface: %s\n", libusb_error_name(r));
		goto out;
	}
	for(int i = 0; i < ncmds; i++)
		if(send_cmd(h, cmds[i]))
			goto release;
	if(ncmds && !t_set) {
		rc = 0;
		goto release;
	}

	printf("%04x:%04x, скорость %s, %d передач по %d КиБ\n", vid, pid,
	       speed_name(libusb_get_device_speed(libusb_get_device(h))), nxfer, xfer_kib);

	if(dump_path && !(dump = fopen(dump_path, "wb"))) {
		fprintf(stderr, "%s: %s\n", dump_path, strerror(errno));
		goto out;
	}

	signal(SIGINT, on_signal);
	signal(SIGTERM, on_signal);

	for(int i = 0; i < nxfer; i++) {
		size_t sz = (size_t)xfer_kib * 1024;
		uint8_t *buf = libusb_dev_mem_alloc(h, sz);
		if(!buf)
			buf = malloc(sz);
		xfers[i] = libusb_alloc_transfer(0);
		libusb_fill_bulk_transfer(xfers[i], h, EP_STREAM, buf, sz, on_transfer, NULL, 1000);
		if((r = libusb_submit_transfer(xfers[i]))) {
			fprintf(stderr, "submit: %s%s\n", libusb_error_name(r), r == LIBUSB_ERROR_NO_MEM ?
				" (передачи не помещаются в usbfs_memory_mb, уменьшите -n или -s)" : "");
			stop = 1;
			usb_failed = 1;
			break;
		}
		in_flight++;
	}

	double t0 = now(), tick = t0;
	uint64_t tick_bytes = 0;
	while(!stop) {
		struct timeval tv = { 0, 100000 };
		libusb_handle_events_timeout(ctx, &tv);
		double t = now();
		if(t - tick >= 1.0) {
			report("   ", t - tick, P.bytes - tick_bytes);
			tick = t;
			tick_bytes = P.bytes;
		}
		if(duration > 0 && t - t0 >= duration)
			stop = 1;
	}
	double total = now() - t0;

	for(int i = 0; i < nxfer; i++)
		if(xfers[i])
			libusb_cancel_transfer(xfers[i]);
	while(in_flight > 0) {
		struct timeval tv = { 0, 100000 };
		libusb_handle_events_timeout(ctx, &tv);
	}

	report("итог", total, P.bytes);
	printf("пропущено до синхронизации %" PRIu64 " байт, всего %.1f МБ за %.1f с\n",
	       P.skipped, P.bytes / 1e6, total);
	if(usb_failed)
		rc = 2;
	else if(!P.blocks) {
		fprintf(stderr, "ни одного блока: поток не найден\n");
		rc = 1;
	} else
		rc = check_errors(&P) ? 1 : 0;

	for(int i = 0; i < nxfer; i++)
		if(xfers[i])
			libusb_free_transfer(xfers[i]); /* буферы освобождает выход из процесса */
release:
	libusb_release_interface(h, 0);
out:
	if(dump)
		fclose(dump);
	if(h)
		libusb_close(h);
	libusb_exit(ctx);
	free(xfers);
	return rc;
}
