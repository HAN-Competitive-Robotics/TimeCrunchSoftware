# Communication

## Packet Format

The control packet is 4 bytes. **Any change to this format must be reflected in all three codebases simultaneously:** `driver/station.py`, `radio-dongle/src/main.c` (length check), and `robot/main/src/main.c` (byte parsing).

```
Serial wire format (5 bytes total):
┌──────────┬──────────┬──────────┬──────────┬──────────┐
│  Byte 0  │  Byte 1  │  Byte 2  │  Byte 3  │  Byte 4  │
│motor_left│motor_right│  weapon  │killswitch│   '\n'  │
│  0–255   │  0–255   │  0–255   │  0–255   │  0x0A    │
└──────────┴──────────┴──────────┴──────────┴──────────┘
```

The `'\n'` is a framing delimiter. **It is not transmitted over radio.** The ESB payload is exactly 4 bytes.

### Field Definitions

**Byte 0 & 1 — Motor Throttle (left and right)**

Centre value is 127 (not 128). Maps to throttle via:
```c
throttle = ((int)b - 127) * 100 / 127
// b=0   → -100 (full reverse)
// b=127 → 0    (neutral)
// b=255 → +100 (full forward, approximately)
```

Tank drive: left stick Y → byte 0, right stick Y → byte 1. 
Arcade drive: mixing happens in the station before serialisation.

**Byte 2 — Weapon Throttle**

| Range | Weapon state | Robot action |
|---|---|---|
| 0 | Off | Weapon motor stopped |
| 1–127 | Idle | Target: `WEAPON_IDLE_RPM` (3000 RPM) |
| 128–255 | Attack | Target: `WEAPON_ATTACK_RPM` (5000 RPM) |

The driver station sends only three values in practice: `0`, `64`, `255`. The byte encodes *desired mode*, not a throttle percentage.

**Byte 3 — Killswitch**

| Value | Meaning |
|---|---|
| 0 | Normal operation |
| 255 | Deep sleep command |

The firmware checks `failsafe_raw > 127`, so any value ≥ 128 triggers the killswitch. The threshold provides robustness against single-bit errors.

### Encoding Notes

- All values are unsigned bytes. No signed values, floats, or multi-byte integers.
- No checksum — USB CDC and ESB CRC-16 provide error detection.
- No sequence numbers — ESB is point-to-point with no reordering possible.
- Send rate: 50 Hz (5 bytes/packet × 50 Hz = 250 bytes/sec, < 1% of 115200 baud).
- Robot packet timeout: 500 ms (25 consecutive missed packets).

### Extending the Packet

To add a new control channel (e.g. a flipper, LEDs):
1. Update `driver/config.json` and `driver/station.py` to include the new byte
2. Update `radio-dongle/src/main.c` `handle_message()` to accept the new length
3. Update `robot/main/src/main.c` `task_core0` to parse the new byte
4. Update `nrf24_basic_config()` `payload_len` argument in `robot/main/src/nrf24.c`
5. Update `config.payload_length` in `radio-dongle/src/esb_ptx.c`

**Warning:** Changing `payload_len` on only one side causes all packets to be silently discarded.

---

## Serial Protocol (USB CDC)

The USB serial link connects the Python driver station to the nRF52840 dongle.

| Parameter | Value |
|---|---|
| Physical medium | USB 2.0 Full Speed |
| Protocol | USB CDC ACM |
| Baud rate | 115200 (reported only — USB CDC ignores it, data flows at USB speed) |
| Frame delimiter | `\n` (0x0A) or `\r` (0x0D) |
| Frame size | 5 bytes (4 data + newline) |

### Port Auto-Detection

The nRF52840 dongle exposes **two** CDC ACM interfaces:
- Interface 0: Zephyr log/shell console (lower port number)
- Interface 1: Application data (higher port number)

On macOS these appear as sequential `usbmodem` numbers. The driver station takes the highest-numbered port (`ports[-1]` in `SerialLink`).

---

## ESB Protocol (Radio)

Nordic Enhanced ShockBurst (ESB) runs on the nRF52840 dongle natively. The robot uses a custom nRF24L01+ driver that produces compatible packets. Both must use **identical** parameters — any mismatch causes complete silent failure.

### Radio Configuration

| Parameter | Value |
|---|---|
| Frequency channel | 40 (2440 MHz) |
| Bitrate | 2 Mbps |
| Payload length | 4 bytes (fixed) |
| Address length | 5 bytes |
| Pipe 0 address | `1NODE` (`0x31 0x4E 0x4F 0x44 0x45`) |
| CRC | 2 bytes |
| Dynamic payload | Disabled |
| ACK / retransmit | No-ACK, 0 retransmits |

### Address Details

```c
// Dongle (Zephyr ESB):
uint8_t base_addr_0[4] = {0x4E, 0x4F, 0x44, 0x45};  // "NODE"
uint8_t addr_prefix[8] = {0x31, ...};                 // '1' for pipe 0
// Resulting address: 0x31 + "NODE" = "1NODE"

// Robot (nRF24L01+):
const uint8_t address[5] = {'1', 'N', 'O', 'D', 'E'};
```

### No-ACK Behaviour

The dongle sends with `noack = true`. The nRF24L01+ still sends an ACK because `EN_DYN_ACK` (FEATURE register bit 0) is not set. This is harmless: the dongle has `retransmit_count = 0` and discards the received ACK. Communication is fully functional.

To eliminate unnecessary ACK traffic (future improvement): set `FEATURE = 0x01` on the nRF24L01+ to enable `EN_DYN_ACK`.

### Channel Selection

Channel 40 = 2440 MHz. Sits between Wi-Fi channels 6 (2437 MHz) and 11 (2462 MHz). Not a quiet region, but avoids the highest-traffic Wi-Fi channels. To change: update both `esb_set_rf_channel(40)` in `radio-dongle/src/esb_ptx.c` and `nrf24_basic_config(..., 40, ...)` in `robot/main/src/main.c`. Valid range: 0–125.

### Dropped Packets

ESB with `retransmit_count = 0` is fire-and-forget. A dropped packet (CRC failure, collision) is invisible to the ESP32 — no interrupt fires, no error is reported. At 50 Hz a single dropped packet produces at most 20 ms of stale motor state, which is imperceptible. The 500 ms timeout (25 consecutive drops) is the safety backstop.

---

## Failsafe Behaviour

### Scenario A — Radio Link Drop

500 ms after the last valid packet: all motors stop, `failsafe_active = true`. task_core1 sees `failsafe_active` and zeroes the weapon. Recovery is automatic on the next valid packet.

```c
if (have_packet &&
    (xTaskGetTickCount() - last_packet_tick) >= pdMS_TO_TICKS(500)) {
    motor_set_throttle(MOTOR_LEFT_WHEEL, 0);
    motor_set_throttle(MOTOR_RIGHT_WHEEL, 0);
    state.weapon_throttle = 0;
    state.failsafe_active = true;
    have_packet = false;
}
```

### Scenario B — Operator Killswitch

Operator holds B / F key → station sends burst of 5 packets with `failsafe=255` → robot receives at least 1 → `hard_failsafe = true` → motors stop → 200 ms delay (allow coast-down) → `esp_deep_sleep_start()`. Power cycle only to recover.

### Scenario C — Thermal Emergency (≥ 90 °C)

Identical effect to the killswitch. `temp_critical` is evaluated on **every received packet** in task_core0, not in the 1 Hz task_temp, giving 20 ms worst-case detection latency (vs. up to 1 second if it were in task_temp).

### Scenario D — Per-Motor Cutoff (≥ 100 °C)

`task_temp` (1 Hz) calls `motor_safety_check()`. A motor ≥ 100 °C gets its throttle zeroed via `apply_throttle_direct` (bypasses the thermal gate since the gate IS the cutoff). Clears automatically when temperature drops below 90 °C.

### What Does NOT Happen

- The robot does **not** stop if the serial link drops while the dongle continues transmitting — this cannot happen, the dongle has no caching.
- The robot **cannot** be woken from deep sleep by software. `esp_deep_sleep_start()` with no wakeup sources configured means only the reset pin or power cycle can wake it.

### Testing Failsafes

| Test | How |
|---|---|
| Packet timeout | Unplug the dongle — motors stop within 500–550 ms, resume when re-plugged |
| Killswitch | Hold killswitch in station — robot sleeps, requires power cycle |
| Thermal (simulated) | Temporarily lower `KILLSWITCH_TEMP_C` to 30 °C, warm a BMP280 by hand |

---

## See Also

- [Architecture](architecture.md)
- [Robot Firmware](firmware/robot-firmware.md)
- [Radio Dongle Firmware](firmware/radio-dongle.md)
