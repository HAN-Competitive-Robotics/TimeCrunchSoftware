#!/usr/bin/env python3
"""Cross-platform flash script for battlebot devices.

Interactive menu when run without arguments:
    python scripts/flash-all.py

Direct CLI usage:
    python scripts/flash-all.py --both          # flash robot + dongle + monitor
    python scripts/flash-all.py --robot         # flash ESP32 only + monitor
    python scripts/flash-all.py --dongle        # flash nRF52840 dongle only
    python scripts/flash-all.py --robot --no-monitor /dev/ttyUSB0
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROBOT_DIR = REPO_ROOT / "robot"


def info(msg):
    print(f"[flash-all] {msg}")


def error(msg):
    print(f"[flash-all] ERROR: {msg}", file=sys.stderr)
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
        if "busy" in err or "access" in err or "permission" in err:
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


def flash_esp32(port, monitor=True):
    idf_path = Path.home() / "esp" / "esp-idf"
    if platform.system() == "Windows":
        if not any((idf_path / f).exists() for f in ("export.bat", "export.ps1")):
            error(f"ESP-IDF not found at {idf_path}. Install it or set IDF_PATH.")
    else:
        if not (idf_path / "export.sh").exists():
            error(f"ESP-IDF not found at {idf_path}. Install it or set IDF_PATH.")

    info(f"Flashing ESP32 receiver on {port}...")
    env = os.environ.copy()
    env["IDF_PATH"] = str(idf_path)

    if platform.system() == "Windows":
        idf_py = shutil.which("idf.py")
        if not idf_py:
            error("idf.py not found in PATH.")
        subprocess.run([sys.executable, idf_py, "-p", port, "flash"], cwd=ROBOT_DIR, env=env, check=True)
        if monitor:
            info("Opening ESP32 monitor (Ctrl+] to exit)...")
            subprocess.run([sys.executable, idf_py, "-p", port, "monitor"], cwd=ROBOT_DIR, env=env, check=True)
    else:
        shell_cmd = f'source "{idf_path}/export.sh" && idf.py -p "{port}" flash'
        subprocess.run(["bash", "-c", shell_cmd], cwd=ROBOT_DIR, env=env, check=True)
        if monitor:
            info("Opening ESP32 monitor (Ctrl+] to exit)...")
            shell_cmd = f'source "{idf_path}/export.sh" && idf.py -p "{port}" monitor'
            subprocess.run(["bash", "-c", shell_cmd], cwd=ROBOT_DIR, env=env, check=True)


def flash_dongle():
    info("Building + flashing nRF52840 dongle...")
    build_script = REPO_ROOT / "scripts" / "build-dongle.py"
    subprocess.run([sys.executable, str(build_script), "flash"], check=True)


def build_dongle_only():
    info("Building nRF52840 dongle...")
    build_script = REPO_ROOT / "scripts" / "build-dongle.py"
    subprocess.run([sys.executable, str(build_script), "build"], check=True)


def find_ports():
    find_script = REPO_ROOT / "scripts" / "find-ports.py"
    subprocess.run([sys.executable, str(find_script)], check=False)


def menu():
    print()
    print("=" * 40)
    print("       Battlebot Flash Menu")
    print("=" * 40)
    print("1. Flash battlebot (ESP32)")
    print("2. Flash dongle (nRF52840)")
    print("3. Flash both + monitor")
    print("4. Find ports")
    print("5. Build dongle only")
    print("6. Exit")
    print("=" * 40)
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
            flash_esp32(port, monitor=True)

        elif choice == "2":
            flash_dongle()

        elif choice == "3":
            port = find_esp32_port()
            if not port:
                error("No ESP32 port found. Plug it in or pass the port manually.")
            info(f"Using ESP32 port: {port}")
            check_port_available(port)
            flash_esp32(port, monitor=False)
            flash_dongle()
            info("Opening ESP32 monitor (Ctrl+] to exit)...")
            flash_esp32(port, monitor=True)

        elif choice == "4":
            find_ports()

        elif choice == "5":
            build_dongle_only()

        elif choice == "6":
            print("Bye.")
            sys.exit(0)

        else:
            print("Invalid choice. Enter 1-6.")


def main():
    parser = argparse.ArgumentParser(description="Flash battlebot devices")
    parser.add_argument("port", nargs="?", help="ESP32 serial port (auto-detected if omitted)")
    parser.add_argument("--robot", action="store_true", help="Flash ESP32 receiver only")
    parser.add_argument("--dongle", action="store_true", help="Flash nRF52840 dongle only")
    parser.add_argument("--both", action="store_true", help="Flash both devices (default)")
    parser.add_argument("--no-monitor", action="store_true", help="Skip opening monitor after flash")
    parser.add_argument("--find-ports", action="store_true", help="List detected serial ports")
    args = parser.parse_args()

    # If no CLI flags given, drop into interactive menu
    if not any([args.robot, args.dongle, args.both, args.find_ports, args.port]):
        interactive()
        return

    if args.find_ports:
        find_ports()
        return

    # Resolve port if needed
    port = args.port if args.port else find_esp32_port()

    if args.dongle:
        flash_dongle()
        return

    if not port:
        error("No ESP32 port found. Plug it in or pass the port manually.")

    if args.robot:
        info(f"Using ESP32 port: {port}")
        check_port_available(port)
        flash_esp32(port, monitor=not args.no_monitor)
        return

    # Default: --both or just a port argument
    info(f"Using ESP32 port: {port}")
    check_port_available(port)
    flash_esp32(port, monitor=False)
    flash_dongle()
    if not args.no_monitor:
        flash_esp32(port, monitor=True)


if __name__ == "__main__":
    main()
