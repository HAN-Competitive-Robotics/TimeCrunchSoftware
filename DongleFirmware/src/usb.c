#include "usb.h"

#include <zephyr/usb/usbd.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(usb_cdc, CONFIG_LOG_DEFAULT_LEVEL);

#define CDC_DEV_NODE DT_CHOSEN(zephyr_console)

static const struct device *cdc_dev;

/* USB device context */
USBD_DEVICE_DEFINE(usbd_cdc,
	DEVICE_DT_GET(DT_NODELABEL(zephyr_udc0)),
	0x2FE3, /* Nordic Semiconductor test VID — change for production */
	0x0100  /* PID */
);

USBD_DESC_LANG_DEFINE(usbd_lang);
USBD_DESC_MANUFACTURER_DEFINE(usbd_mfr, "HCR");
USBD_DESC_PRODUCT_DEFINE(usbd_product, "HCR Dongle");
USBD_DESC_SERIAL_NUMBER_DEFINE(usbd_sn);

USBD_CONFIGURATION_DEFINE(usbd_fs_config, USB_SCD_SELF_POWERED, 250, NULL);

int usb_cdc_init(void)
{
	int err;

	cdc_dev = DEVICE_DT_GET(CDC_DEV_NODE);
	if (!device_is_ready(cdc_dev)) {
		LOG_ERR("CDC ACM device not ready");
		return -ENODEV;
	}

	err = usbd_add_descriptor(&usbd_cdc, &usbd_lang);
	if (err) { return err; }
	err = usbd_add_descriptor(&usbd_cdc, &usbd_mfr);
	if (err) { return err; }
	err = usbd_add_descriptor(&usbd_cdc, &usbd_product);
	if (err) { return err; }
	err = usbd_add_descriptor(&usbd_cdc, &usbd_sn);
	if (err) { return err; }

	err = usbd_add_configuration(&usbd_cdc, USBD_SPEED_FS, &usbd_fs_config);
	if (err) { return err; }

	err = usbd_register_all_classes(&usbd_cdc, USBD_SPEED_FS, 1, NULL);
	if (err) { return err; }

	err = usbd_init(&usbd_cdc);
	if (err) { return err; }

	err = usbd_enable(&usbd_cdc);
	if (err) { return err; }

	(void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_BAUD_RATE, 115200);

	LOG_INF("USB CDC ACM ready");
	return 0;
}

int usb_cdc_read(uint8_t *buf, size_t max_len)
{
	if (!cdc_dev || !buf || max_len == 0) {
		return 0;
	}

	int total = 0;
	while (total < (int)max_len) {
		uint8_t c;
		int r = uart_fifo_read(cdc_dev, &c, 1);
		if (r <= 0) {
			break;
		}
		buf[total++] = c;
	}
	return total;
}

int usb_cdc_write(const uint8_t *buf, size_t len)
{
	if (!cdc_dev || !buf || len == 0) {
		return 0;
	}

	return uart_fifo_fill(cdc_dev, buf, len);
}
