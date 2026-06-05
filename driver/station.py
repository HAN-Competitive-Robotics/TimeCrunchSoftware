#!/usr/bin/env python3
"""HCR Mission Control — main entry point."""

import argparse
import json
import sys
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / "config.json"

# Ensure dependencies fail early with a clean message.
try:
    import pygame
except ImportError:
    print("ERROR: pygame required. pip install pygame")
    sys.exit(1)

try:
    import serial
except ImportError:
    print("ERROR: pyserial required. pip install pyserial")
    sys.exit(1)

from profiles import ProfileManager, BINDABLE_ACTIONS
from keymap import _init_key_maps, key_to_name, key_display, gp_display
from serial_link import SerialLink
from inputmapper import InputMapper
from gui import GUI, SCREEN_MAIN, SCREEN_KEYBINDS
from calibrate import calibrate


def main():
    parser = argparse.ArgumentParser(description="HCR Mission Control")
    parser.add_argument("--calibrate", action="store_true",
                        help="Show gamepad axis/button numbers")
    args = parser.parse_args()

    if args.calibrate:
        calibrate()
        return

    cfg      = json.loads(CONFIG_PATH.read_text())
    profiles = ProfileManager()

    pygame.init()
    _init_key_maps()

    gui    = GUI(cfg)
    mapper = InputMapper(profiles.active)
    link   = SerialLink(cfg)

    if link.ensure_connected():
        gui.add_log(f"Serial connected: {link.port_name}")
    else:
        gui.add_log("Serial searching...")

    if mapper.joystick_name:
        gui.add_log(f"Gamepad: {mapper.joystick_name}")
    else:
        gui.add_log("No gamepad — keyboard only")

    gui.add_log(f"Profile: {profiles.active['name']}")

    rate_hz    = cfg["serial"]["rate_hz"]
    start_time = pygame.time.get_ticks()
    last_send  = 0
    last_tick  = pygame.time.get_ticks()

    gs = {
        "drive_inverted": False,
        "weapon_state":   "safe",
    }
    prev_invert_raw      = False
    armed                = False
    prev_arm_raw         = False
    prev_weapon_btn      = False
    killswitch_triggered = False

    running = True
    while running:
        now       = pygame.time.get_ticks()
        last_tick = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.VIDEORESIZE:
                gui.screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                gui.handle_click(event.pos, profiles, mapper, gs)

            elif event.type == pygame.KEYDOWN:
                k = event.key

                # Keybind KB capture
                if (gui.capturing
                        and gui.current_screen == SCREEN_KEYBINDS
                        and gui.capture_col == 0):
                    if k == pygame.K_ESCAPE:
                        gui.capturing = False
                    else:
                        _, _, is_axis, kb_pos, kb_neg, _ = BINDABLE_ACTIONS[gui.capture_row]
                        name = key_to_name(k)
                        if is_axis:
                            if gui.capture_step == 0:
                                profiles.set_keybind(kb_pos, name)
                                mapper.set_profile(profiles.active)
                                gui.capture_step = 1
                            else:
                                profiles.set_keybind(kb_neg, name)
                                mapper.set_profile(profiles.active)
                                gui.capturing = False
                                gui.add_log(f"Bound {kb_pos}/{kb_neg}")
                        else:
                            profiles.set_keybind(kb_pos, name)
                            mapper.set_profile(profiles.active)
                            gui.capturing = False
                            gui.add_log(f"Bound {kb_pos}: {key_display(name)}")
                    continue

                # Close overlays / navigate
                if k == pygame.K_ESCAPE:
                    if gui.capturing:
                        gui.capturing = False
                    elif gui.dropdown.open:
                        gui.dropdown.open = False
                    elif gui.current_screen != SCREEN_MAIN:
                        gui.current_screen = SCREEN_MAIN
                    else:
                        running = False

                elif k == pygame.K_F2:
                    if gui.current_screen == SCREEN_KEYBINDS:
                        gui.current_screen = SCREEN_MAIN
                    else:
                        gui.current_screen  = SCREEN_KEYBINDS
                        gui.keybind_cursor  = 0
                        gui.keybind_col     = 0

                elif gui.current_screen == SCREEN_KEYBINDS:
                    n = len(BINDABLE_ACTIONS)
                    if k == pygame.K_UP:
                        gui.keybind_cursor = (gui.keybind_cursor - 1) % n
                    elif k == pygame.K_DOWN:
                        gui.keybind_cursor = (gui.keybind_cursor + 1) % n
                    elif k == pygame.K_LEFT:
                        gui.keybind_col = 0
                    elif k == pygame.K_RIGHT:
                        gui.keybind_col = 1
                    elif k == pygame.K_RETURN:
                        gui._start_capture(gui.keybind_cursor, gui.keybind_col)

                elif gui.current_screen == SCREEN_MAIN and not gui.overlay_active:
                    if k == pygame.K_t:
                        profiles.toggle_drive_mode()
                        mapper.set_profile(profiles.active)
                        gs["drive_inverted"] = False
                        gui.add_log(f"Drive mode: {profiles.active['drive_mode'].upper()}")

            # Gamepad capture: button
            elif (event.type == pygame.JOYBUTTONDOWN
                  and gui.capturing
                  and gui.current_screen == SCREEN_KEYBINDS
                  and gui.capture_col == 1):
                _, _, _, _, _, gp_key = BINDABLE_ACTIONS[gui.capture_row]
                gp_cfg = {"button": event.button}
                profiles.set_gamepad_bind(gp_key, gp_cfg)
                mapper.set_profile(profiles.active)
                gui.capturing = False
                gui.add_log(f"Bound {gp_key}: B{event.button}")

            # Gamepad capture: axis
            elif (event.type == pygame.JOYAXISMOTION
                  and gui.capturing
                  and gui.current_screen == SCREEN_KEYBINDS
                  and gui.capture_col == 1
                  and abs(event.value) > 0.5):
                _, _, is_axis, _, _, gp_key = BINDABLE_ACTIONS[gui.capture_row]
                if is_axis:
                    gp_cfg = {"axis": event.axis, "invert": event.value < 0, "deadzone": 0.15}
                else:
                    gp_cfg = {"axis": event.axis, "threshold": 0.5}
                profiles.set_gamepad_bind(gp_key, gp_cfg)
                mapper.set_profile(profiles.active)
                gui.capturing = False
                gui.add_log(f"Bound {gp_key}: {gp_display(gp_cfg)}")

            msg = mapper.handle_event(event)
            if msg:
                gui.add_log(msg)

        # Pause robot controls when any overlay is open
        paused = gui.overlay_active or gui.current_screen != SCREEN_MAIN

        if paused:
            gui.draw(link, mapper, profiles, 127, 127,
                     gs["drive_inverted"], armed, gs["weapon_state"], killswitch_triggered,
                     now - start_time)
            gui.clock.tick(60)
            continue

        keys = pygame.key.get_pressed()
        fwd, right = mapper.read_drive(keys)

        if profiles.active.get("drive_mode") == "arcade":
            motor_l = int(max(0, min(255, 127 + (fwd + right) * 128)))
            motor_r = int(max(0, min(255, 127 + (fwd - right) * 128)))
        else:
            motor_l = int(max(0, min(255, 127 + fwd   * 128)))
            motor_r = int(max(0, min(255, 127 + right * 128)))

        invert_raw = mapper.read_button("drive_invert", keys)
        if invert_raw and not prev_invert_raw:
            gs["drive_inverted"] = not gs["drive_inverted"]
            gui.add_log(f"Drive invert {'ON' if gs['drive_inverted'] else 'OFF'}")
        prev_invert_raw = invert_raw

        if gs["drive_inverted"]:
            motor_l, motor_r = motor_r, motor_l

        kill_raw = mapper.read_button("killswitch", keys)
        if kill_raw and not killswitch_triggered:
            killswitch_triggered = True
            gui.add_log("KILLSWITCH — robot latched until power cycle")
            burst = bytes([127, 127, 127, 255]) + b"\n"
            if link.ensure_connected():
                for _ in range(5):
                    link.send(burst)
            else:
                gui.add_log("WARNING: killswitch sent but serial not connected")
        failsafe_byte = 255 if kill_raw else 0

        arm_raw = mapper.read_button("arm", keys)
        if arm_raw and not prev_arm_raw:
            armed = not armed
            gui.add_log(f"Robot {'ARMED' if armed else 'DISARMED'}")
        prev_arm_raw = arm_raw

        if not armed:
            motor_l = motor_r = 127
            gs["weapon_state"] = "safe"

        weapon_btn     = mapper.read_button("weapon", keys)
        weapon_rev_btn = mapper.read_button("weapon_rev", keys)
        if armed:
            if weapon_btn and not prev_weapon_btn:
                gs["weapon_state"] = "safe" if gs["weapon_state"] != "safe" else "idle"
            elif gs["weapon_state"] == "idle" and weapon_rev_btn:
                gs["weapon_state"] = "attack"
            elif gs["weapon_state"] == "attack" and not weapon_rev_btn:
                gs["weapon_state"] = "idle"
        prev_weapon_btn = weapon_btn

        # Protocol: 127=off, 128-190=idle fwd, 191-255=attack fwd (firmware main.c comment)
        weapon_byte = {"safe": 127, "idle": 160, "attack": 255}[gs["weapon_state"]]
        packet = bytes([motor_l, motor_r, weapon_byte, failsafe_byte]) + b"\n"

        if now - last_send >= 1000 / rate_hz:
            was_searching = link.state == "searching"
            if link.ensure_connected():
                if was_searching:
                    gui.add_log(f"Serial connected: {link.port_name}")
                if link.send(packet):
                    print(f"[TX] {packet.hex()}  "
                          f"motors=({motor_l},{motor_r}) weapon={weapon_byte} fs={failsafe_byte}")
                else:
                    gui.add_log("Serial write failed")
            last_send = now

        gui.draw(link, mapper, profiles, motor_l, motor_r,
                 gs["drive_inverted"], armed, gs["weapon_state"], killswitch_triggered,
                 now - start_time)
        gui.clock.tick(rate_hz)

    pygame.quit()
    print("Ground station shut down.")


if __name__ == "__main__":
    main()
