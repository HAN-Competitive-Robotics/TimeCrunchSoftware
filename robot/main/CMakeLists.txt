idf_component_register(
    SRCS "src/main.c"
         "src/motor_driver.c"
         "src/i2c_bus.c"
         "src/tempsensor_driver.c"
         "src/power_sensor_driver.c"
         "src/hall_sensor.c"
         "src/weapon_controller.c"
         "src/nrf24.c"
    INCLUDE_DIRS "./include"
)
