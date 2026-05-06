idf_component_register(
    SRCS "src/main.c"
         "src/motor_driver.c"
         "src/tempsensor_driver.c"
         "src/encoder_driver.c"
         "src/weapon_controller.c"
         "src/nrf24.c"
    INCLUDE_DIRS "./include"
)
