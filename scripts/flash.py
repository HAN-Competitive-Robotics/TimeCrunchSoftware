#!/usr/bin/env python3
"""Cross-platform flash script for battlebot devices.

Interactive menu when run without arguments:
    python scripts/flash.py

Direct CLI usage:
    python scripts/flash.py --robot                     # flash ESP32 + monitor
    python scripts/flash.py --dongle                    # flash nRF52840 dongle
    python scripts/flash.py --both                      # flash robot + dongle + monitor
    python scripts/flash.py --weapon-calibrate          # flash weapon-motor calibration
    python scripts/flash.py --weapon-test               # flash weapon-motor test
    python scripts/flash.py --build-robot               # build ESP32 only (no flash)
    python scripts/flash.py --robot --no-monitor        # flash without opening monitor
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT        = Path(__file__).resolve().parent.parent
ROBOT_DIR        = REPO_ROOT / "robot"
WEAPON_MOTOR_DIR = REPO_ROOT / "weapon-motor"


def info(msg):
    print(f"[flash] {msg}")


def error(msg):
    print(f"[flash] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def find_esp32_port():
    import serial.tools.list_ports

    keywords = ["cp210", "ch340", "ch341", "ftdi", "usb-uart", "usb serial"]
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if any(k in desc or k in hwid for k in keywords):
            return p.device

    import glob
    patterns = []
    if platform.system() == "Darwin":
        patterns = ["/dev/cu.usbserial*", "/dev/tty.usbserial*"]
    elif platform.system() == "Linux":
        patterns = ["/dev/ttyUSB*"]
    elif platform.system() == "Windows":
        ports = [p.device for p in serial.tools.list_ports.comports() if "COM" in p.device.upper()]
        if ports:
            return ports[0]

    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]

    return None


def check_port_available(port):
    import serial
    try:
        s = serial.Serial(port, baudrate=115200, timeout=0.5)
        s.close()
        return True
    except serial.SerialException as e:
        err = str(e).lower()
        # Match any "port busy" wording  macOS raises "Resource temporarily
        # unavailable" (errno 35) which doesn't contain "busy"/"access"/"permission"
        if any(k in err for k in ("busy", "access", "permission", "unavailable", "errno 35")):
            info(f"Port {port} is already in use.")
            if platform.system() in ("Darwin", "Linux"):
                try:
                    result = subprocess.run(
                        ["lsof", "+t", port], capture_output=True, text=True, timeout=2
                    )
                    if result.stdout:
                        info(f"Process holding the port:\n{result.stdout.strip()}")
                except Exception:
                    pass
            error(
                f"Cannot open {port}.\n"
                "Close any monitor/screen/minicom sessions first, then retry.\n"
                "  pkill -f monitor"
            )
        return True


def _idf_path():
    idf_path = Path.home() / "esp" / "esp-idf"
    if platform.system() == "Windows":
        if not any((idf_path / f).exists() for f in ("export.bat", "export.ps1")):
            error(f"ESP-IDF not found at {idf_path}. Install it or set IDF_PATH.")
    else:
        if not (idf_path / "export.sh").exists():
            error(f"ESP-IDF not found at {idf_path}. Install it or set IDF_PATH.")
    return idf_path


def _run_idf(project_dir, idf_path, build_dir, port, extra_cmake="", flash=True, monitor=True):
    """Run idf.py flash (and optionally monitor) for any ESP-IDF project."""
    env = os.environ.copy()
    env["IDF_PATH"] = str(idf_path)

    if platform.system() == "Windows":
        idf_py = shutil.which("idf.py")
        if not idf_py:
            error("idf.py not found in PATH.")
        cmd = [sys.executable, idf_py, "-B", build_dir]
        if extra_cmake:
            cmd += extra_cmake.split()
        if flash:
            cmd += ["-p", port, "flash"]
        subprocess.run(cmd, cwd=project_dir, env=env, check=True)
        if monitor:
            info("Opening monitor (Ctrl+] to exit)...")
            subprocess.run([sys.executable, idf_py, "-p", port, "monitor"],
                           cwd=project_dir, env=env, check=True)
    else:
        cmake_args = f" {extra_cmake}" if extra_cmake else ""
        if flash:
            shell_cmd = (
                f'source "{idf_path}/export.sh" && '
                f'idf.py -B {build_dir}{cmake_args} -p "{port}" flash'
            )
            subprocess.run(["bash", "-c", shell_cmd], cwd=project_dir, env=env, check=True)
        if monitor:
            info("Opening monitor (Ctrl+] to exit)...")
            shell_cmd = f'source "{idf_path}/export.sh" && idf.py -p "{port}" monitor'
            subprocess.run(["bash", "-c", shell_cmd], cwd=project_dir, env=env, check=True)


def flash_robot(port, monitor=True):
    idf_path = _idf_path()
    info(f"Flashing robot (ESP32) on {port}...")
    _run_idf(ROBOT_DIR, idf_path, "build", port, monitor=monitor)


def build_robot_only():
    idf_path = _idf_path()
    info("Building robot (ESP32)...")
    env = os.environ.copy()
    env["IDF_PATH"] = str(idf_path)
    if platform.system() == "Windows":
        idf_py = shutil.which("idf.py")
        subprocess.run([sys.executable, idf_py, "-B", "build", "build"],
                       cwd=ROBOT_DIR, env=env, check=True)
    else:
        shell_cmd = f'source "{idf_path}/export.sh" && idf.py -B build build'
        subprocess.run(["bash", "-c", shell_cmd], cwd=ROBOT_DIR, env=env, check=True)


def flash_dongle():
    info("Building + flashing nRF52840 dongle...")
    build_script = REPO_ROOT / "scripts" / "build-dongle.py"
    subprocess.run([sys.executable, str(build_script), "flash"], check=True)


def build_dongle_only():
    info("Building nRF52840 dongle...")
    build_script = REPO_ROOT / "scripts" / "build-dongle.py"
    subprocess.run([sys.executable, str(build_script), "build"], check=True)


def flash_weapon_motor(port, mode, monitor=True):
    """Flash weapon-motor firmware. mode is 'calibrate' or 'test'."""
    assert mode in ("calibrate", "test")
    idf_path  = _idf_path()
    cmake_def = "MODE_CALIBRATE" if mode == "calibrate" else "MODE_TEST"
    build_dir = f"build_{mode}"
    info(f"Flashing weapon-motor ({mode.upper()}) on {port}...")
    _run_idf(
        WEAPON_MOTOR_DIR, idf_path, build_dir, port,
        extra_cmake=f"-DWEAPON_MODE={cmake_def}",
        monitor=monitor,
    )


def find_ports():
    find_script = REPO_ROOT / "scripts" / "find-ports.py"
    subprocess.run([sys.executable, str(find_script)], check=False)


def menu():
    print()
    print("=" * 44)
    print("         Battlebot Flash Menu")
    print("=" * 44)
    print("1. Flash robot (ESP32)")
    print("2. Flash dongle (nRF52840)")
    print("3. Flash both + monitor")
    print("4. Flash weapon-motor: CALIBRATE + monitor")
    print("5. Flash weapon-motor: TEST + monitor")
    print("6. Find ports")
    print("7. Build robot only")
    print("8. Build dongle only")
    print("9. Exit")
    print("=" * 44)
    print()


def interactive():
    while True:
        menu()
        choice = input("Choice: ").strip()

        if choice == "1":
            port = find_esp32_port()
            if not port:
                error("No ESP32 port found. Plug it in or pass the port manually.")
            info(f"Using ESP32 port: {port}")
            check_port_available(port)
            flash_robot(port, monitor=True)

        elif choice == "2":
            flash_dongle()

        elif choice == "3":
            port = find_esp32_port()
            if not port:
                error("No ESP32 port found. Plug it in or pass the port manually.")
            info(f"Using ESP32 port: {port}")
            check_port_available(port)
            flash_robot(port, monitor=False)
            flash_dongle()
            flash_robot(port, monitor=True)

        elif choice == "4":
            port = find_esp32_port()
            if not port:
                error("No ESP32 port found. Plug it in or pass the port manually.")
            info(f"Using ESP32 port: {port}")
            check_port_available(port)
            flash_weapon_motor(port, "calibrate", monitor=True)

        elif choice == "5":
            port = find_esp32_port()
            if not port:
                error("No ESP32 port found. Plug it in or pass the port manually.")
            info(f"Using ESP32 port: {port}")
            check_port_available(port)
            flash_weapon_motor(port, "test", monitor=True)

        elif choice == "6":
            find_ports()

        elif choice == "7":
            build_robot_only()

        elif choice == "8":
            build_dongle_only()

        elif choice == "9":
            print("Bye.")
            sys.exit(0)

        else:
            print("Invalid choice. Enter 1-9.")


def main():
    parser = argparse.ArgumentParser(description="Flash battlebot devices")
    parser.add_argument("port", nargs="?", help="ESP32 serial port (auto-detected if omitted)")
    parser.add_argument("--robot",             action="store_true", help="Flash ESP32 robot only")
    parser.add_argument("--dongle",            action="store_true", help="Flash nRF52840 dongle only")
    parser.add_argument("--both",              action="store_true", help="Flash robot + dongle + monitor")
    parser.add_argument("--weapon-calibrate",  action="store_true", help="Flash weapon-motor calibration mode")
    parser.add_argument("--weapon-test",       action="store_true", help="Flash weapon-motor test mode")
    parser.add_argument("--no-monitor",        action="store_true", help="Skip opening monitor after flash")
    parser.add_argument("--find-ports",        action="store_true", help="List detected serial ports")
    parser.add_argument("--build-robot",       action="store_true", help="Build ESP32 robot only (no flash)")
    args = parser.parse_args()

    if not any([args.robot, args.dongle, args.both,
                args.weapon_calibrate, args.weapon_test,
                args.find_ports, args.build_robot, args.port]):
        interactive()
        return

    if args.find_ports:
        find_ports()
        return

    if args.build_robot:
        build_robot_only()
        return

    port = args.port if args.port else find_esp32_port()

    if args.dongle:
        flash_dongle()
        return

    if not port:
        error("No ESP32 port found. Plug it in or pass the port manually.")

    check_port_available(port)
    monitor = not args.no_monitor

    if args.weapon_calibrate:
        flash_weapon_motor(port, "calibrate", monitor=monitor)
        return

    if args.weapon_test:
        flash_weapon_motor(port, "test", monitor=monitor)
        return

    if args.robot:
        info(f"Using ESP32 port: {port}")
        flash_robot(port, monitor=monitor)
        return

    # --both or bare port
    info(f"Using ESP32 port: {port}")
    flash_robot(port, monitor=False)
    flash_dongle()
    if monitor:
        flash_robot(port, monitor=True)


if __name__ == "__main__":
    main()
