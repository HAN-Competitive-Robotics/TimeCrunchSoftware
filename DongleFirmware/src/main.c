#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>

#include <zephyr/drivers/clock_control.h>
#include <zephyr/drivers/clock_control/nrf_clock_control.h>

#include <zephyr/drivers/gpio.h>
#include <zephyr/devicetree.h>

#include "usb.h"
#include "esb_ptx.h"

LOG_MODULE_REGISTER(app, CONFIG_LOG_DEFAULT_LEVEL);

/* ---- Debug LED (inline) ---- */
#define LED0_NODE DT_ALIAS(led0)

#if !DT_NODE_HAS_STATUS(LED0_NODE, okay)
#error "No led0 alias in devicetree. Check your board selection or add an overlay."
#endif

static const struct gpio_dt_spec led0 = GPIO_DT_SPEC_GET(LED0_NODE, gpios);
static bool led0_state;

static int led_debug_init(void)
{
	if (!device_is_ready(led0.port))
	{
		LOG_ERR("LED device not ready");
		return -ENODEV;
	}

	int err = gpio_pin_configure_dt(&led0, GPIO_OUTPUT_INACTIVE);
	if (err)
	{
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

/* ---- HFCLK start (your original, kept) ---- */
#if defined(CONFIG_CLOCK_CONTROL_NRF)
static int clocks_start(void)
{
	int err;
	int res;
	struct onoff_manager *clk_mgr;
	struct onoff_client clk_cli;

	clk_mgr = z_nrf_clock_control_get_onoff(CLOCK_CONTROL_NRF_SUBSYS_HF);
	if (!clk_mgr)
	{
		LOG_ERR("Unable to get the Clock manager");
		return -ENXIO;
	}

	sys_notify_init_spinwait(&clk_cli.notify);

	err = onoff_request(clk_mgr, &clk_cli);
	if (err < 0)
	{
		LOG_ERR("Clock request failed: %d", err);
		return err;
	}

	do
	{
		err = sys_notify_fetch_result(&clk_cli.notify, &res);
		if (!err && res)
		{
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

	LOG_INF("ESB PTX + USB CDC (nRF52840 dongle)");

	err = clocks_start();
	if (err)
	{
		return 0;
	}

	err = led_debug_init();
	if (err)
	{
		return 0;
	}

	err = usb_cdc_init();
	if (err)
	{
		return 0;
	}
	
	err = esb_radio_init();
	if (err)
	{
		LOG_ERR("ESB init failed: %d", err);
		return 0;
	}

	LOG_INF("Init complete. USB: send 't' to TX, or stream 8 bytes to fill payload and auto-TX.");

	struct esb_payload tx_payload = esb_radio_default_payload();

	uint8_t acc[8];
	size_t acc_len = 0;

	while (1)
	{

		uint8_t buf[64];
		int received = usb_cdc_read(buf, sizeof(buf));

		if (received > 0)
		{
			led_debug_toggle();	   // show activity
			usb_cdc_write(buf, received); // echo
		}

		k_sleep(K_MSEC(10));

		/*
		if (esb_radio_ready())
		{
			led_debug_toggle();

			
			// esb_flush_tx();

			err = esb_radio_send(&tx_payload);
			if (err)
			{

				LOG_ERR("esb send failed: %d", err);
			}
			else
			{

				tx_payload.data[1];
			}
		}
		*/

		k_sleep(K_MSEC(100));
	}
}