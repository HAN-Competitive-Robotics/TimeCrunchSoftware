"""Gamepad calibration window (Dear PyGui)."""
from __future__ import annotations
import pygame
import dearpygui.dearpygui as dpg
from keymap import init_keymap


def calibrate() -> None:
    pygame.joystick.init()

    dpg.create_context()
    init_keymap()
    dpg.create_viewport(title="Gamepad Calibration", width=520, height=440, resizable=True)
    dpg.setup_dearpygui()
    dpg.show_viewport()

    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg,  (30, 30, 35))
            dpg.add_theme_color(dpg.mvThemeCol_Text,       (220, 220, 220))
            dpg.add_theme_color(dpg.mvThemeCol_Separator,  (60, 60, 72))
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 16, 14)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing,   8, 6)
    dpg.bind_theme(theme)

    with dpg.window(tag="cal", no_title_bar=True, no_move=True,
                    no_resize=True, no_close=True, no_collapse=True):
        dpg.add_text("GAMEPAD CALIBRATION", color=(0, 200, 255))
        dpg.add_text("Move sticks and press buttons. Close window to exit.",
                     color=(120, 120, 130))
        dpg.add_separator()
        dpg.add_text("No gamepad connected.", tag="cal_status", color=(255, 60, 60))
        dpg.add_separator()
        dpg.add_text("", tag="cal_axes",   wrap=0)
        dpg.add_separator()
        dpg.add_text("", tag="cal_btns",   wrap=0)

    dpg.set_primary_window("cal", True)

    js: pygame.joystick.JoystickType | None = None
    if pygame.joystick.get_count() > 0:
        js = pygame.joystick.Joystick(0)
        js.init()

    while dpg.is_dearpygui_running():
        for event in pygame.event.get():
            if event.type == pygame.JOYDEVICEADDED:
                js = pygame.joystick.Joystick(event.device_index)
                js.init()
            elif event.type == pygame.JOYDEVICEREMOVED:
                js = None

        if js:
            dpg.set_value("cal_status", f"Connected: {js.get_name()}")
            dpg.configure_item("cal_status", color=(60, 255, 120))
            dpg.set_value("cal_axes",
                "\n".join(f"  Axis {i}: {js.get_axis(i):+.3f}"
                          for i in range(js.get_numaxes())))
            btns = [js.get_button(i) for i in range(js.get_numbuttons())]
            dpg.set_value("cal_btns",
                "  " + "  ".join(f"B{i}={'ON ' if v else 'off'}"
                                  for i, v in enumerate(btns)))
        else:
            dpg.set_value("cal_status", "No gamepad connected.")
            dpg.configure_item("cal_status", color=(255, 60, 60))
            dpg.set_value("cal_axes", "")
            dpg.set_value("cal_btns", "")

        vw = dpg.get_viewport_width()
        vh = dpg.get_viewport_height()
        dpg.set_item_width("cal", vw)
        dpg.set_item_height("cal", vh)

        dpg.render_dearpygui_frame()

    dpg.destroy_context()
    pygame.quit()
