#include "esb_ptx.h"

#include <zephyr/logging/log.h>
#include <zephyr/sys/util.h>

LOG_MODULE_REGISTER(esb_radio, CONFIG_ESB_PTX_APP_LOG_LEVEL);

static volatile bool g_ready = true;

static struct esb_payload rx_payload;

static void event_handler(struct esb_evt const *event)
{
    switch (event->evt_id)
    {
    case ESB_EVENT_TX_SUCCESS:
        g_ready = true;
        LOG_DBG("ESB TX success");
        break;

    case ESB_EVENT_TX_FAILED:
        esb_flush_tx();
        g_ready = true;
        LOG_DBG("ESB TX failed");
        break;

    case ESB_EVENT_RX_RECEIVED:
        /* PTX usually only receives ACK payloads if enabled. */
        while (esb_read_rx_payload(&rx_payload) == 0)
        {
            LOG_DBG("ESB RX len %d: %02x %02x %02x %02x %02x %02x %02x %02x",
                    rx_payload.length,
                    rx_payload.data[0], rx_payload.data[1], rx_payload.data[2], rx_payload.data[3],
                    rx_payload.data[4], rx_payload.data[5], rx_payload.data[6], rx_payload.data[7]);
        }
        break;

    default:
        break;
    }
}

struct esb_payload esb_radio_default_payload(void)
{
    struct esb_payload pl = {0};

    pl.pipe = 0;
    pl.length = 4;
    pl.noack = false;

    pl.data[0] = 0x01;
    pl.data[1] = 0x00;
    pl.data[2] = 0x03;
    pl.data[3] = 0x04;

    return pl;
}

int esb_radio_init(void)
{
    int err;

    /* Default demo addresses (fine for bring-up; change for real products). */
    uint8_t base_addr_0[4] = {0x4E, 0x4F, 0x44, 0x45}; // "NODE"
    uint8_t base_addr_1[4] = {0xC2, 0xC2, 0xC2, 0xC2};
    uint8_t addr_prefix[8] = {0x31, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8}; // 0x31 is ASCII 1 -> Full address is NODE1

    struct esb_config config = ESB_DEFAULT_CONFIG;

    config.protocol = ESB_PROTOCOL_ESB;
    config.retransmit_delay = 600;
    config.bitrate = ESB_BITRATE_1MBPS;
    config.event_handler = event_handler;
    config.mode = ESB_MODE_PTX;
    config.payload_length = 4;
    config.selective_auto_ack = false;
    if (IS_ENABLED(CONFIG_ESB_FAST_SWITCHING))
    {
        config.use_fast_ramp_up = true;
    }

    err = esb_init(&config);
    if (err)
    {
        LOG_ERR("esb_init failed: %d", err);
        return err;
    }

    err = esb_set_rf_channel(40);
    if (err)
    {
        LOG_ERR("esb_set_rf_channel failed: %d", err);
        return err;
    }

    err = esb_set_base_address_0(base_addr_0);
    if (err)
    {
        LOG_ERR("set_base_address_0 failed: %d", err);
        return err;
    }

    err = esb_set_base_address_1(base_addr_1);
    if (err)
    {
        LOG_ERR("set_base_address_1 failed: %d", err);
        return err;
    }

    err = esb_set_prefixes(addr_prefix, ARRAY_SIZE(addr_prefix));
    if (err)
    {
        LOG_ERR("set_prefixes failed: %d", err);
        return err;
    }

    g_ready = true;
    LOG_INF("ESB radio initialized (PTX)");
    return 0;
}

struct esb_payload esb_set_battlebot_payload(uint8_t motor1, uint8_t motor2, uint8_t weaponEn, uint8_t failsafe)
{
    struct esb_payload pl = {0};
    pl.pipe = 0;
    pl.length = 4;
    pl.noack = false;
    pl.data[0] = motor1;
    pl.data[1] = motor2;
    pl.data[2] = weaponEn;
    pl.data[3] = failsafe;
    return pl;
}

bool esb_radio_ready(void)
{
    return g_ready;
}

int esb_radio_send(struct esb_payload *pl)
{
    int err = esb_write_payload(pl);
    if (err == 0)
    {
        g_ready = false; // only clear when queued successfully
    }
    return err;
}