#include "usb.h"

#include <zephyr/usb/usb_device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(usb_cdc, CONFIG_LOG_DEFAULT_LEVEL);

#define CDC_DEV_NODE DT_CHOSEN(zephyr_console)

static const struct device *cdc_dev;


//USB initialization
int usb_cdc_init(void)
{
    int err;

    cdc_dev = DEVICE_DT_GET(CDC_DEV_NODE);
    if (!device_is_ready(cdc_dev))
    {
        //LOG_ERR("CDC ACM device not ready (check devicetree/console routing)");
        return -ENODEV;
    }

    err = usb_enable(NULL);
    if (err)
    {
       // LOG_ERR("usb_enable failed: %d", err);
        return err;
    }

   

    (void)uart_line_ctrl_set(cdc_dev, UART_LINE_CTRL_BAUD_RATE, 115200);

    //LOG_INF("USB CDC ACM ready");
    return 0;
}

//USB read
int usb_cdc_read(uint8_t *buf, size_t max_len)
{
    if (!cdc_dev || !buf || max_len == 0)
    {
        return 0;
    }

    return uart_fifo_read(cdc_dev, buf, (int)max_len);
}
//USB write
int usb_cdc_write(const uint8_t *buf, size_t len)
{
    if (!cdc_dev || !buf || len == 0)
    {
        return 0;
    }

    return uart_fifo_fill(cdc_dev, buf, (int)len);
}