# Robot Firmware (ESP32)

## Overview

The robot firmware is an ESP-IDF project running on an ESP32 DevKit. It manages all real-time hardware interfaces: radio reception, motor control, weapon speed control, thermal safety, and encoder feedback.

**Entry point:** `robot/main/src/main.c`  `app_main()`  
**Build system:** ESP-IDF (CMake-based, `idf.py` toolchain)  
**RTOS:** FreeRTOS (bundled with ESP-IDF)

---

## Source File Structure

```
robot/
├── CMakeLists.txt                 ESP-IDF project definition
├── main/
│   ├── CMakeLists.txt             Component registration
│   ├── src/
│   │   ├── main.c                 app_main, task definitions, inter-task state
│   │   ├── motor_driver.c         MCPWM PWM generation, thermal gate
│   │   ├── nrf24.c                nRF24L01+ SPI driver, IRQ handler
│   │   ├── weapon_controller.c    PI speed controller, anti-windup
│   │   ├── encoder_driver.c       PCNT pulse counter, RPM timer
│   │   └── tempsensor_driver.c    BMP280 I²C driver, temperature compensation
│   └── include/
│       ├── motor_driver.h         Motor API + GPIO pin definitions
│       ├── nrf24.h                nRF24 API + register/command definitions
│       ├── weapon_controller.h    PI parameters + weapon API
│       ├── encoder_driver.h       Encoder GPIO + encoder API
│       └── tempsensor_driver.h    I²C bus pins + sensor API
├── sdkconfig.defaults             Baseline Kconfig (check into git)
└── sdkconfig                      Auto-generated Kconfig (do not check in)
```

---

## Initialisation Sequence

All hardware initialisation happens inside `task_core0` before the main loop. This is deliberate: by the time `task_core1` and `task_temp` first iterate, all shared hardware resources are fully configured.

```c
void task_core0(void *pvParameters)
{
    // 1. Configure MCPWM (3 channels, neutral pulse)
    motor_driver_init();

    // 2. Configure both I²C buses, read BMP280 calibration bytes
    tempsensor_driver_init();

    // 3. Configure PCNT, start 100ms RPM timer
    encoder_driver_init();

    // 4. Initialise PI state variables
    weapon_controller_init();

    // 5. Configure GPIOs (CE, CSN, IRQ), SPI bus, nRF24 registers
    nrf24_init();
    nrf24_basic_config(address, 40, 4);

    // 6. Create IRQ semaphore, attach GPIO interrupt handler
    nrf24_init_irq();

    // → Enter radio receive loop
}
```

The ordering matters:
- `motor_driver_init()` first so all ESC signals are at neutral (1500 µs) immediately
- `tempsensor_driver_init()` before `weapon_controller_init()` (sensor data must be available for the PI's first safety check)
- `nrf24_init_irq()` last  no interrupts fire before the hardware is fully configured

---

## Motor Driver (`motor_driver.c`)

### Key design decisions

**All three motors use one MCPWM timer.** They share the same 50 Hz timer but each has its own operator, comparator, and generator. This synchronises all ESC signals but uses only one timer resource.

**The thermal gate is in the driver, not the caller.** `motor_set_throttle` silently ignores commands when the thermal cutoff is active. Callers do not need to check temperature themselves. This centralises the safety logic.

**`apply_throttle_direct` is private.** It bypasses the thermal gate and should only be called by `motor_safety_check` to enforce zero throttle under cutoff. If you add a new caller of `apply_throttle_direct`, you must understand you are bypassing the safety gate.

```c
static void apply_throttle_direct(motor_t motor, int throttle)
{
    // clamp to [-100, 100], convert to µs, write MCPWM comparator
}
```

---

## nRF24L01+ Driver (`nrf24.c`)

### SPI transaction model

Every nRF24 access is a SPI transaction: `csn_low()` → transfer bytes → `csn_high()`. The `spi_transfer()` function performs this atomically using ESP-IDF's `spi_device_polling_transmit`.

**Polling transmit** (not DMA, not interrupt-driven) is used because:
- Transactions are short (max 33 bytes)
- Polling latency is lower than DMA setup for short transactions
- Task_core0 calls SPI from a task context (not ISR), so blocking is acceptable

### IRQ handler

```c
static void IRAM_ATTR nrf24_irq_handler(void *arg)
{
    BaseType_t hptw = pdFALSE;
    if (nrf24_irq_sem != NULL) {
        xSemaphoreGiveFromISR(nrf24_irq_sem, &hptw);
    }
    if (hptw == pdTRUE) portYIELD_FROM_ISR();
}
```

`IRAM_ATTR` places this function in internal RAM so it runs even if the external flash (where code normally lives) is being accessed. ISRs must be in IRAM on ESP32.

`portYIELD_FROM_ISR()` requests a context switch if `xSemaphoreGiveFromISR` woke a higher-priority task. Without this, the context switch would wait until the next FreeRTOS tick (up to 1 ms delay).

### Register map

All nRF24L01+ register addresses, command codes, and bit masks are defined in `nrf24.h`. The actual register configuration is in `nrf24_basic_config()`. See [Communication](../communication.md) for the full ESB configuration rationale.

---

## Temperature Sensor Driver (`tempsensor_driver.c`)

### BMP280 usage

The BMP280 is a barometric pressure and temperature sensor. Only its **temperature channel** is used here  the pressure measurements are discarded. This is a pragmatic choice: BMP280 modules are inexpensive, widely available, and measure temperature accurately enough for thermal protection.

> **Chip ID check:** The driver reads `BMP280_CHIP_ID` (0xD0) register and compares to 0x58. BME280 (the humidity variant) returns 0x60 at the same register. If you accidentally have BME280 modules, the driver will log a warning but continue  the compensation formula is compatible. Update `BMP280_CHIP_ID` to 0x60 or remove the check if using BME280.

### Temperature compensation

The raw ADC value from BMP280 is not in Celsius. The datasheet specifies a compensation formula using factory-calibrated constants stored in the sensor's EEPROM:

```c
int32_t var1 = (((adc_T >> 3) - ((int32_t)c->dig_T1 << 1)) * (int32_t)c->dig_T2) >> 11;
int32_t var2 = (((((adc_T >> 4) - (int32_t)c->dig_T1) *
                   ((adc_T >> 4) - (int32_t)c->dig_T1)) >> 12) *
                 (int32_t)c->dig_T3) >> 14;
int32_t T = ((var1 + var2) * 5 + 128) >> 8;  // hundredths of °C
return (float)T / 100.0f;
```

This is verbatim from the BMP280 datasheet (section 4.2.3). It is intentionally cryptic because it uses fixed-point arithmetic scaled to specific power-of-2 ranges for efficient computation on MCUs without FPUs. Do not modify this calculation.

### Sensor configuration

```
ctrl_meas = 0x23:
  osrs_t = 001 (×1 oversampling for temperature)
  osrs_p = 000 (pressure disabled)
  mode   = 11  (normal mode  continuous measurement)
```

In normal mode the BMP280 measures continuously. The `standby time` (config register = 0x00) is 0.5 ms, so new measurements are available every ~2 ms. The firmware reads whenever `temp_get_temperature()` is called  there is no explicit synchronisation with the BMP280's measurement cycle, but at 50 Hz polling the occasional stale reading is acceptable.

---

## Motor PWM (MCPWM)

All three motors use the RC servo PWM protocol: 50 Hz period, 1000–2000 µs pulse width, neutral at 1500 µs.

```c
mcpwm_timer_config_t timer_config = {
    .group_id      = 0,
    .resolution_hz = 1000000,   // 1 µs per tick
    .period_ticks  = 20000,     // 20 ms = 50 Hz
};
```

Throttle-to-ticks conversion:
```c
uint32_t ticks = PWM_TICKS_MIN +
    (uint32_t)((throttle + 100) * (PWM_TICKS_MAX - PWM_TICKS_MIN) / 200);
// throttle=-100 → 1000 µs  (full reverse)
// throttle=0    → 1500 µs  (neutral)
// throttle=100  → 2000 µs  (full forward)
```

All three ESCs share one timer (synchronised) but each has its own operator, comparator, and generator. The MCPWM is initialised at neutral (1500 µs), so ESCs arm automatically if the ESP32 boots before battery is connected.

The weapon ESC (8BL150) is unidirectional — it does not support reverse. `weapon_controller_update()` clamps its output to [0, 100] to prevent a brake or reverse command from being sent.

---

## Weapon Speed Controller

The weapon runs a **PI controller with feedforward** at 100 Hz on Core 1.

**Current state:** Both `WEAPON_KP` and `WEAPON_KI` are set to `0.0` in `weapon_controller.h`. The weapon spins purely on the open-loop feedforward (`WEAPON_FF = 50%`). The PI gains are there to be tuned once the robot is running and baseline RPM measurements are available.

```c
#define WEAPON_ATTACK_RPM  5000.0f
#define WEAPON_IDLE_RPM    3000.0f
#define WEAPON_FF    50.0f   // 50% throttle baseline
#define WEAPON_KP     0.0f   // to be tuned
#define WEAPON_KI     0.0f   // to be tuned
```

Control law:
```
output = FF + KP × error + KI × ∫error·dt
  where error = target_rpm − measured_rpm

integral anti-windup: clamp integral so KI × integral ≤ (100 − FF)
output clamped to [0, 100]
```

`weapon_controller_reset()` zeroes the integral and resets the dt timestamp. Called whenever the weapon disarms to prevent an accumulated integral from causing a burst when the weapon re-arms.

**Encoder lag:** The PCNT samples every 100 ms, but the weapon loop runs at 100 Hz (10 ms). For 9 out of every 10 iterations the PI sees a stale RPM value. Effective closed-loop rate is 10 Hz, not 100 Hz. Keep gains conservative.

**Tuning procedure when ready:**
1. With KP=KI=0, adjust `WEAPON_FF` until the weapon reaches approximately target RPM at nominal battery voltage under no load.
2. Increase `KP` until the weapon responds quickly to disturbances without oscillating. Starting range: 0.002–0.01 (% throttle per RPM error).
3. Add a small `KI` (e.g. 0.0005) to eliminate steady-state error under load.
4. Verify anti-windup: stall briefly with a padded object, release — should recover smoothly without overshoot.

---

## Key Code Patterns to Know

### Queue overwrite pattern (mailbox)

```c
// Sender (task_core0):
xQueueOverwrite(state_queue, &state);

// Receiver (task_core1):
robot_state_t new_state;
if (xQueueReceive(state_queue, &new_state, 0) == pdTRUE) {
    state = new_state;
}
// If no new state: 'state' retains its previous value
```

This is the correct FreeRTOS pattern for "share latest value between tasks". A depth-1 queue with `xQueueOverwrite` never blocks and always contains the most recent value. `xQueueReceive` with zero timeout is non-blocking.

### Atomic float pattern

```c
// Write float atomically:
uint32_t bits; memcpy(&bits, &rpm, sizeof(bits));
atomic_store_explicit(&s_rpm_bits, bits, memory_order_release);

// Read float atomically:
uint32_t bits = atomic_load_explicit(&s_rpm_bits, memory_order_acquire);
float rpm; memcpy(&rpm, &bits, sizeof(rpm));
```

Use this pattern whenever a float must be shared between tasks or between an ISR/timer callback and a task.

---

## See Also

- [Architecture](../architecture.md)
- [Build and Flash](build-and-flash.md)
- [Hardware Pinout](../hardware/pinout.md)
