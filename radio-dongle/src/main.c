#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <zephyr/drivers/clock_control.h>
#include <zephyr/drivers/clock_control/nrf_clock_control.h>

#include <zephyr/drivers/gpio.h>
#include <zephyr/devicetree.h>
#include "usb.h"
#include "esb_ptx.h"
#include <zephyr/sys/ring_buffer.h>

LOG_MODULE_REGISTER(app, CONFIG_LOG_DEFAULT_LEVEL);

#define MSG_MAX 128
static uint8_t msg_buf[MSG_MAX];
static size_t  msg_len;

#define LED0_NODE DT_ALIAS(led0)

#if !DT_NODE_HAS_STATUS(LED0_NODE, okay)
#error "No led0 alias in devicetree. Check your board selection or add an overlay."
#endif

#define USB_RB_SIZE 512
RING_BUF_DECLARE(usb_rb, USB_RB_SIZE);

static struct k_sem usb_rx_sem;

#define USB_RX_STACK_SIZE 1024
#define USB_RX_PRIORITY   5

K_THREAD_STACK_DEFINE(usb_rx_stack, USB_RX_STACK_SIZE);
static struct k_thread usb_rx_thread;

static const struct gpio_dt_spec led0 = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static bool led0_state;

static int led_debug_init(void)
{
	if (!device_is_ready(led0.port)) {
		LOG_ERR("LED device not ready");
		return -ENODEV;
	}

	int err = gpio_pin_configure_dt(&led0, GPIO_OUTPUT_INACTIVE);
	if (err) {
		LOG_ERR("Failed to configure LED pin: %d", err);
		return err;
	}

	led0_state = false;
	return 0;
}

static void led_debug_toggle(void)
{
	led0_state = !led0_state;
	(void)gpio_pin_set_dt(&led0, (int)led0_state);
}

static void usb_rx_thread_fn(void *a, void *b, void *c)
{
	ARG_UNUSED(a);
	ARG_UNUSED(b);
	ARG_UNUSED(c);

	uint8_t buf[64];

	while (1) {
		int n = usb_cdc_read(buf, sizeof(buf));

		if (n > 0) {
			uint32_t wrote = ring_buf_put(&usb_rb, buf, (uint32_t)n);
			if (wrote > 0) {
				k_sem_give(&usb_rx_sem);
			}

			if (wrote < (uint32_t)n) {
				LOG_WRN("USB RX ring buffer overflow: dropped %u bytes",
					(uint32_t)n - wrote);
			}
			continue;
		}

		k_sleep(K_MSEC(5));
	}
}

static int hex_nibble(uint8_t c)
{
	if (c >= '0' && c <= '9') return c - '0';
	if (c >= 'a' && c <= 'f') return c - 'a' + 10;
	if (c >= 'A' && c <= 'F') return c - 'A' + 10;
	return -1;
}

static void handle_message(const uint8_t *msg, size_t len)
{
	if (len != 8) {
		LOG_WRN("Unexpected message length: %u (expected 8 hex chars)", (unsigned)len);
		return;
	}

	uint8_t decoded[4];
	for (int i = 0; i < 4; i++) {
		int hi = hex_nibble(msg[i * 2]);
		int lo = hex_nibble(msg[i * 2 + 1]);
		if (hi < 0 || lo < 0) {
			LOG_WRN("Invalid hex in packet at byte %d", i);
			return;
		}
		decoded[i] = (uint8_t)((hi << 4) | lo);
	}

	if (!esb_radio_ready()) {
		LOG_WRN("ESB not ready — packet dropped");
		return;
	}

	struct esb_payload pl = esb_set_battlebot_payload(decoded[0], decoded[1], decoded[2], decoded[3]);
	int err = esb_radio_send(&pl);
	led_debug_toggle();

	if (err) {
		LOG_ERR("ESB send failed: %d", err);
	}
}

static void usb_parse_available(void)
{
	uint8_t b;

	while (ring_buf_get(&usb_rb, &b, 1) == 1) {
		if (b == '\n' || b == '\r') {
			if (msg_len > 0) {
				handle_message(msg_buf, msg_len);
				msg_len = 0;
			}
			continue;
		}

		if (msg_len < MSG_MAX) {
			msg_buf[msg_len++] = b;
		} else {
			LOG_ERR("Message too long  discarding");
			msg_len = 0;
			usb_cdc_write((const uint8_t *)"ERR: msg too long\r\n", 19);
		}
	}
}

#if defined(CONFIG_CLOCK_CONTROL_NRF)
static int clocks_start(void)
{
	int err;
	int res;
	struct onoff_manager *clk_mgr;
	struct onoff_client   clk_cli;

	clk_mgr = z_nrf_clock_control_get_onoff(CLOCK_CONTROL_NRF_SUBSYS_HF);
	if (!clk_mgr) {
		LOG_ERR("Unable to get the Clock manager");
		return -ENXIO;
	}

	sys_notify_init_spinwait(&clk_cli.notify);

	err = onoff_request(clk_mgr, &clk_cli);
	if (err < 0) {
		LOG_ERR("Clock request failed: %d", err);
		return err;
	}

	do {
		err = sys_notify_fetch_result(&clk_cli.notify, &res);
		if (!err && res) {
			LOG_ERR("Clock could not be started: %d", res);
			return res;
		}
	} while (err);

	LOG_DBG("HF clock started");
	return 0;
}
#else
static int clocks_start(void) { return 0; }
#endif

int main(void)
{
	int err;

	LOG_INF("ESB PTX + USB CDC (nRF52840 dongle) starting");

	err = clocks_start();
	if (err) {
		LOG_ERR("Clock start failed: %d", err);
		return 0;
	}

	err = led_debug_init();
	if (err) {
		LOG_ERR("LED init failed: %d", err);
		return 0;
	}

	err = usb_cdc_init();
	if (err) {
		LOG_ERR("USB CDC init failed: %d", err);
		return 0;
	}

	err = esb_radio_init();
	if (err) {
		LOG_ERR("ESB init failed: %d", err);
		return 0;
	}

	k_sem_init(&usb_rx_sem, 0, 1);

	k_thread_create(&usb_rx_thread, usb_rx_stack, USB_RX_STACK_SIZE,
			usb_rx_thread_fn, NULL, NULL, NULL,
			USB_RX_PRIORITY, 0, K_NO_WAIT);

	LOG_INF("Init complete. Entering main loop.");

	while (1) {
		if (k_sem_take(&usb_rx_sem, K_MSEC(10)) == 0) {
			usb_parse_available();
		}

		static int led_ticks;
		if (++led_ticks >= 50) {
			led_ticks = 0;
			led_debug_toggle();
		}
	}
}
