# Radio Dongle Firmware (nRF52840)

## Overview

The nRF52840 dongle acts as a transparent USB-to-radio bridge. It receives 4-byte control packets from the laptop via USB CDC serial, and transmits them over 2.4 GHz Nordic Enhanced ShockBurst to the ESP32 robot.

**MCU:** nRF52840 PCA10059 USB Dongle  
**Framework:** Zephyr RTOS  
**SDK:** nRF Connect SDK (NCS) v2.7+  
**Entry point:** `radio-dongle/src/main.c`  `main()`  
**Build tool:** `west` (Zephyr's meta-build system)

---

## Source File Structure

```
radio-dongle/
├── CMakeLists.txt          Zephyr project file
├── Kconfig                 Project-specific Kconfig options
├── prj.conf                Zephyr Kconfig selections
├── src/
│   ├── main.c              Thread creation, main loop, USB parsing
│   ├── esb_ptx.c           Nordic ESB transmitter initialisation and send
│   ├── esb_ptx.h           ESB API
│   ├── usb.c               USB CDC ACM initialisation, read/write helpers
│   └── usb.h               USB API
└── local/
    ├── ncs.env.example     Template for local SDK paths
    └── ncs.env             Your local config (git-ignored)
```

---

## Thread Architecture

The dongle runs two Zephyr threads plus the main thread:

```
main() → initialisation → main loop (waits on usb_rx_sem)
         ↑
usb_rx_thread_fn → drains USB FIFO → writes to ring buffer → signals sem
```

### USB RX Thread

```c
static void usb_rx_thread_fn(void *a, void *b, void *c)
{
    uint8_t buf[64];
    while (1) {
        int n = usb_cdc_read(buf, sizeof(buf));
        if (n > 0) {
            uint32_t wrote = ring_buf_put(&usb_rb, buf, n);
            if (wrote > 0) k_sem_give(&usb_rx_sem);
            if (wrote < n) LOG_WRN("USB RX overflow: dropped %u bytes", n - wrote);
        } else {
            k_sleep(K_MSEC(5));  // no data: sleep briefly
        }
    }
}
```

**Priority:** 5 (Zephyr default priorities; lower number = higher priority)  
**Stack:** 1024 bytes

The 5 ms sleep when no data is available introduces up to 5 ms latency. This is the dominant latency contributor on the dongle side. At 50 Hz send rate (20 ms inter-packet gap) a 5 ms wake latency adds ~25% to the propagation time.

**Ring buffer size (512 bytes):** At 5 bytes/packet × 50 Hz = 250 bytes/sec, the buffer holds ~2 seconds of data without overflow. In normal operation it is never stressed.

### Main Thread

The main thread waits on the binary semaphore `usb_rx_sem` (10 ms timeout), then calls `usb_parse_available()` to process the ring buffer:

```c
while (1) {
    if (k_sem_take(&usb_rx_sem, K_MSEC(10)) == 0) {
        usb_parse_available();
    }
    // LED heartbeat every 50 × 10ms = 500ms
    if (++led_ticks >= 50) {
        led_ticks = 0;
        led_debug_toggle();
    }
}
```

The `usb_rx_sem` is a **binary semaphore** (max count 1). If multiple batches of data arrive while the main thread is processing, subsequent `k_sem_give` calls on a full semaphore are lost. This is safe because:
1. `usb_parse_available` drains the entire ring buffer each call, not just one packet
2. The next `k_sem_take` timeout (10 ms) provides a backup polling path
3. At 50 Hz packet rate, batching is rare

---

## ESB Transmitter (`esb_ptx.c`)

### Initialisation

```c
struct esb_config config = ESB_DEFAULT_CONFIG;
config.protocol          = ESB_PROTOCOL_ESB;     // not DPL (dynamic payload)
config.selective_auto_ack = true;
config.retransmit_count  = 0;                    // no retransmits
config.bitrate           = ESB_BITRATE_2MBPS;
config.mode              = ESB_MODE_PTX;          // Primary Transmitter
config.payload_length    = 4;                    // fixed payload
```

The `ESB_PROTOCOL_ESB` (not `ESB_PROTOCOL_ESB_DPL`) selection disables dynamic payload length. The payload is always exactly 4 bytes, matching the nRF24L01+ receiver's `RX_PW_P0 = 4` configuration.

`selective_auto_ack = true` with `noack = true` in payloads means the dongle can selectively disable ACK requests per packet. With `retransmit_count = 0`, even if an ACK were requested, there would be no retransmission attempt.

### Event Handler

```c
static void event_handler(struct esb_evt const *event)
{
    switch (event->evt_id) {
    case ESB_EVENT_TX_SUCCESS:
        g_ready = true;
        break;
    case ESB_EVENT_TX_FAILED:
        esb_flush_tx();
        g_ready = true;
        break;
    case ESB_EVENT_RX_RECEIVED:
        while (esb_read_rx_payload(&rx_payload) == 0) { /* discard ACK payloads */ }
        break;
    }
}
```

`g_ready` is set to `false` when a packet is queued and back to `true` after TX_SUCCESS or TX_FAILED. This prevents queuing a new packet before the previous one has been transmitted. Since `retransmit_count = 0`, both events fire almost immediately after the packet is sent.

`ESB_EVENT_RX_RECEIVED` handles ACK payloads from the robot. Since the robot is configured to auto-ACK (see [ESB Protocol known issue](../communication/esb-protocol.md)), ACK packets arrive here and are discarded.

### `esb_radio_ready()` check

Before transmitting, `main.c` checks `esb_radio_ready()`. If the radio is not ready (previous packet still in TX FIFO), the packet is dropped with a log warning:

```c
if (!esb_radio_ready()) {
    LOG_WRN("ESB not ready  packet dropped");
    return;
}
```

At 50 Hz packets and near-instantaneous TX at 2 Mbps, this condition should never trigger in normal operation.

---

## USB CDC Driver (`usb.c`)

The USB driver wraps Zephyr's CDC ACM UART driver. Three functions:

```c
int usb_cdc_init(void)  // enumerate device, set baud rate
int usb_cdc_read(uint8_t *buf, size_t max_len)   // read from UART FIFO
int usb_cdc_write(const uint8_t *buf, size_t len) // write to UART FIFO
```

`usb_cdc_read` uses `uart_fifo_read`, which reads from the hardware FIFO non-blocking. If no bytes are available, it returns 0. This is why the USB RX thread uses a 5 ms sleep as a polling fallback.

The device node `DT_CHOSEN(zephyr_console)` selects the CDC ACM device from the Zephyr devicetree. This is configured in `prj.conf`.

---

## HF Clock Startup

The nRF52840's radio requires the **High Frequency (HF) crystal oscillator** to be running. The `clocks_start()` function in `main.c` requests and waits for HF clock:

```c
#if defined(CONFIG_CLOCK_CONTROL_NRF)
static int clocks_start(void)
{
    clk_mgr = z_nrf_clock_control_get_onoff(CLOCK_CONTROL_NRF_SUBSYS_HF);
    sys_notify_init_spinwait(&clk_cli.notify);
    onoff_request(clk_mgr, &clk_cli);
    do {
        err = sys_notify_fetch_result(&clk_cli.notify, &res);
    } while (err);
    return 0;
}
#else
static int clocks_start(void) { return 0; }  // NCS manages clock automatically
#endif
```

This spin-waits until the HF crystal is stable (typically < 1 ms). Without this, `esb_init` may fail or produce corrupted packets.

---

## Kconfig and prj.conf

`radio-dongle/prj.conf` configures the Zephyr kernel and drivers for this application. Key settings include:
- USB CDC ACM device enabled
- Nordic ESB library enabled  
- HF clock control enabled
- Log level configured

If you need to change log verbosity, modify `CONFIG_LOG_DEFAULT_LEVEL` in `prj.conf`.

---

## Building and Flashing

See [Build and Flash](build-and-flash.md) for the complete workflow. The dongle uses USB DFU (Device Firmware Update) for flashing  it does not require a debug probe (J-Link/SWD). The dongle must be placed in bootloader mode by holding the reset button while plugging in.

---

## See Also

- [ESB Protocol](../communication/esb-protocol.md)
- [Serial Protocol](../communication/serial-protocol.md)
- [Build and Flash](build-and-flash.md)
- [Zephyr Setup](../onboarding/zephyr-setup.md)
