try:
    import pygame
except ImportError:
    import sys
    print("ERROR: pygame required. pip install pygame")
    sys.exit(1)


def calibrate():
    pygame.init()
    pygame.joystick.init()
    print("=== Gamepad Calibration ===")
    print("Move sticks and press buttons. Press ESC to quit.\n")

    clock  = pygame.time.Clock()
    screen = pygame.display.set_mode((600, 400), pygame.RESIZABLE)
    pygame.display.set_caption("Gamepad Calibration")
    font = pygame.font.SysFont("monospace", 16)

    js = None
    if pygame.joystick.get_count() > 0:
        js = pygame.joystick.Joystick(0)
        js.init()
        print(f"Connected: {js.get_name()}")
        print(f"Axes: {js.get_numaxes()}  Buttons: {js.get_numbuttons()}")

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            if event.type == pygame.VIDEORESIZE:
                screen = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            if event.type == pygame.JOYDEVICEADDED:
                js = pygame.joystick.Joystick(event.device_index)
                js.init()
            if event.type == pygame.JOYDEVICEREMOVED:
                js = None

        screen.fill((30, 30, 35))
        y = 20
        if js:
            for i in range(js.get_numaxes()):
                val = js.get_axis(i)
                col = (0, 200, 255) if abs(val) > 0.1 else (220, 220, 220)
                screen.blit(font.render(f"Axis {i}: {val:+.3f}", True, col), (20, y))
                y += 22
            y += 10
            buttons = [js.get_button(i) for i in range(js.get_numbuttons())]
            btn_str = "  ".join(f"B{i}={'ON' if v else 'off'}" for i, v in enumerate(buttons))
            for chunk in [btn_str[j:j+80] for j in range(0, len(btn_str), 80)]:
                screen.blit(font.render(chunk, True, (220, 220, 220)), (20, y))
                y += 22
        else:
            screen.blit(font.render("No gamepad connected.", True, (255, 60, 60)), (20, y))

        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
