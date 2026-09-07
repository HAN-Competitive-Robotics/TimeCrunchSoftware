#include "usb.h"

#include <zephyr/usb/usb_device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(usb_cdc, CONFIG_LOG_DEFAULT_LEVEL);

#define CDC_DEV_NODE DT_CHOSEN(zephyr_console)

static const struct device *cdc_dev;

int usb_cdc_init(void)
{
	int err;

	cdc_dev = DEVICE_DT_GET(CDC_DEV_NODE);
	if (!device_is_ready(cdc_dev)) {
		LOG_ERR("CDC ACM device not ready (check devicetree/console routing)");
		return -ENODEV;
	}

	err = usb_enable(NULL);
	if (err) {
		LOG_ERR("usb_enable failed: %d", err);
		return err;
	}

	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_BAUD_RATE, 115200);

	LOG_INF("USB CDC ACM ready");
	return 0;
}

/*
 * uart_fifo_read()/uart_fifo_fill() are the interrupt-driven API and are only
 * valid from inside a UART ISR, after uart_irq_rx_ready() reports data. This
 * firmware never calls uart_irq_callback_set() or uart_irq_rx_enable(), so
 * uart_fifo_read() returned 0 forever from usb_rx_thread_fn() and the CDC OUT
 * endpoint was never drained. The host filled its driver buffer and then
 * blocked in write() permanently.
 *
 * uart_poll_in()/uart_poll_out() are the polling API and are safe to call from
 * a thread, which is what usb_rx_thread_fn() already is.
 */
int usb_cdc_read(uint8_t *buf, size_t max_len)
{
	if (!cdc_dev || !buf || max_len == 0) {
		return 0;
	}

	size_t n = 0;

	while (n < max_len) {
		unsigned char c;

		if (uart_poll_in(cdc_dev, &c) != 0) {
			break;
		}
		buf[n++] = c;
	}

	return (int)n;
}

int usb_cdc_write(const uint8_t *buf, size_t len)
{
	if (!cdc_dev || !buf || len == 0) {
		return 0;
	}

	for (size_t i = 0; i < len; i++) {
		uart_poll_out(cdc_dev, buf[i]);
	}

	return (int)len;
}
