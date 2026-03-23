#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "motor_driver.h"

void task_core0(void *pvParameters)
{
    while (1)
    {
        printf("hello core 0\n");
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

void task_core1(void *pvParameters)
{
    motor_driver_init();

    while (1)
    {
        printf("hello core 1\n");
        motor_set_throttle(MOTOR_WEAPON, -100);
        vTaskDelay(pdMS_TO_TICKS(1000));
        motor_set_throttle(MOTOR_WEAPON, -50);
        vTaskDelay(pdMS_TO_TICKS(1000));
        motor_set_throttle(MOTOR_WEAPON, 0);
        vTaskDelay(pdMS_TO_TICKS(1000));
        motor_set_throttle(MOTOR_WEAPON, 50);
        vTaskDelay(pdMS_TO_TICKS(1000));
        motor_set_throttle(MOTOR_WEAPON, 100);
        printf("bye core 1 \n");
    }
}

void app_main(void)
{
    xTaskCreatePinnedToCore(
        task_core0,     // function
        "task_core0",   // name
        2048,           // stack size
        NULL,           // parameters
        1,              // priority
        NULL,           // task handle
        0               // core 0
    );

    xTaskCreatePinnedToCore(
        task_core1,
        "task_core1",
        2048,
        NULL,
        1,
        NULL,
        1               // core 1
    );
}