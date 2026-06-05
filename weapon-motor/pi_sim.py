import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
from matplotlib.animation import FuncAnimation

# Simulation params
TAU = 0.08
DT = 0.005
HISTORY_SEC = 3.0
HISTORY_LEN = int(HISTORY_SEC / DT)

# State
rpm = 0.0
integral = 0.0
history_t = np.linspace(-HISTORY_SEC, 0, HISTORY_LEN)
history_rpm = np.zeros(HISTORY_LEN)
history_target = np.zeros(HISTORY_LEN)
history_u = np.zeros(HISTORY_LEN)

disturbance = 0.0

fig = plt.figure(figsize=(12, 7))
fig.subplots_adjust(left=0.08, right=0.95, top=0.9, bottom=0.25)

# Main scrolling graph
ax_graph = fig.add_axes([0.08, 0.38, 0.55, 0.52])
line_rpm, = ax_graph.plot(history_t, history_rpm, lw=2, color='C0', label='RPM')
line_target, = ax_graph.plot(history_t, history_target, lw=1.5, color='C3', linestyle='--', label='Target')
ax_graph.set_xlim(-HISTORY_SEC, 0)
ax_graph.set_ylim(0, 16000)
ax_graph.set_ylabel('RPM')
ax_graph.set_title('Real-Time Motor PI Controller')
ax_graph.legend(loc='upper left')
ax_graph.grid(True)

# Big number displays
ax_rpm_text = fig.add_axes([0.70, 0.65, 0.22, 0.18])
ax_rpm_text.set_xlim(0, 1)
ax_rpm_text.set_ylim(0, 1)
ax_rpm_text.axis('off')
rpm_text = ax_rpm_text.text(0.5, 0.5, '0', fontsize=48, ha='center', va='center', color='C0', weight='bold')
ax_rpm_text.text(0.5, 0.1, 'RPM', fontsize=14, ha='center', va='center', color='gray')

ax_duty_text = fig.add_axes([0.70, 0.40, 0.22, 0.18])
ax_duty_text.set_xlim(0, 1)
ax_duty_text.set_ylim(0, 1)
ax_duty_text.axis('off')
duty_text = ax_duty_text.text(0.5, 0.5, '0%', fontsize=48, ha='center', va='center', color='C2', weight='bold')
ax_duty_text.text(0.5, 0.1, 'Duty', fontsize=14, ha='center', va='center', color='gray')

# Sliders
ax_kp = plt.axes([0.15, 0.18, 0.30, 0.03])
ax_ki = plt.axes([0.15, 0.12, 0.30, 0.03])
ax_target = plt.axes([0.15, 0.06, 0.30, 0.03])

s_kp = Slider(ax_kp, 'Kp', 0.0, 0.05, valinit=0.005)
s_ki = Slider(ax_ki, 'Ki', 0.0, 0.2, valinit=0.02)
s_target = Slider(ax_target, 'Target RPM', 0.0, 15000.0, valinit=5000.0)

# Disrupt button
ax_disrupt = plt.axes([0.60, 0.08, 0.12, 0.08])
btn_disrupt = Button(ax_disrupt, 'DISRUPT', color='tomato', hovercolor='red')

def on_disrupt(event):
    global disturbance
    # Big sudden load spike, lasts longer
    disturbance = np.random.uniform(-8000, -4000)

btn_disrupt.on_clicked(on_disrupt)

# Reset button
ax_reset = plt.axes([0.78, 0.08, 0.10, 0.08])
btn_reset = Button(ax_reset, 'Reset')

def on_reset(event):
    global rpm, integral, disturbance, history_rpm, history_u, history_target
    rpm = 0.0
    integral = 0.0
    disturbance = 0.0
    history_rpm[:] = 0.0
    history_u[:] = 0.0
    history_target[:] = 0.0
    s_kp.reset()
    s_ki.reset()
    s_target.reset()

btn_reset.on_clicked(on_reset)

def update(frame):
    global rpm, integral, disturbance, history_rpm, history_u, history_target

    kp = s_kp.val
    ki = s_ki.val
    target = s_target.val

    err = target - rpm
    integral += err * DT
    u = kp * err + ki * integral
    u = max(0.0, min(100.0, u))

    # Plant: first-order motor + disturbance
    rpm += DT * (-rpm / TAU + 700.0 * u / TAU + disturbance / TAU)
    rpm = max(0.0, rpm)

    # Decay disturbance slowly so it lingers
    disturbance *= 0.992
    if abs(disturbance) < 10:
        disturbance = 0.0

    # Shift history
    history_rpm = np.roll(history_rpm, -1)
    history_rpm[-1] = rpm
    history_target = np.roll(history_target, -1)
    history_target[-1] = target
    history_u = np.roll(history_u, -1)
    history_u[-1] = u

    # Update graph
    line_rpm.set_ydata(history_rpm)
    line_target.set_ydata(history_target)

    # Update big numbers
    rpm_text.set_text(f'{rpm:.0f}')
    duty_text.set_text(f'{u:.1f}%')

    # Color feedback
    if abs(err) < target * 0.05:
        rpm_text.set_color('C2')
    elif abs(err) < target * 0.2:
        rpm_text.set_color('C1')
    else:
        rpm_text.set_color('C0')

    # NOTE: blit disabled to stop text flickering when values change
    return line_rpm, line_target, rpm_text, duty_text

ani = FuncAnimation(fig, update, interval=DT * 1000, blit=False, cache_frame_data=False)
plt.show()
