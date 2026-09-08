idf_component_register(
    SRCS "src/main.c"
         "src/motor_driver.c"
         "src/i2c_bus.c"
         "src/tempsensor_driver.c"
         "src/power_sensor_driver.c"
         "src/hall_sensor.c"
         "src/weapon_controller.c"
         "src/safety_monitor.c"
         "src/nrf24.c"
         "src/trim_store.c"
    INCLUDE_DIRS "./include"
)

# No REQUIRES here on purpose. "main" is special in ESP-IDF: with no explicit
# requirements it depends on every component in the build, which is how this
# project gets driver/spi_master.h, driver/mcpwm_prelude.h and nvs_flash.
# Adding even one REQUIRES entry replaces that automatic list with just what
# is named, which breaks every other include in the component.
