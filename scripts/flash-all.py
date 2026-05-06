#!/usr/bin/env python3
"""Cross-platform flash script for both battlebot devices."""

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

    # macOS / Linux fallback by path pattern
    import glob

    patterns = []
    if platform.system() == "Darwin":
        patterns = ["/dev/cu.usbserial*", "/dev/tty.usbserial*"]
    elif platform.system() == "Linux":
        patterns = ["/dev/ttyUSB*"]
    elif platform.system() == "Windows":
        # On Windows we already scanned by description; last resort scan COM ports
        ports = [p.device for p in serial.tools.list_ports.comports() if "COM" in p.device.upper()]
        if ports:
            return ports[0]

    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]

    error(
        "No ESP32 serial port found.\n"
        "Please plug in the ESP32 or pass the port manually, e.g.:\n"
        f"  python {Path(__file__).name} /dev/ttyUSB0\n"
        f"  python {Path(__file__).name} COM3"
    )


def flash_esp32(port):
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

    # idf.py needs the ESP-IDF environment activated first
    if platform.system() == "Windows":
        # On Windows, idf.py is typically available directly if the environment is set up
        idf_py = shutil.which("idf.py")
        if not idf_py:
            error("idf.py not found in PATH. Run 'export.ps1' or 'export.bat' from ESP-IDF first.")
        subprocess.run([sys.executable, idf_py, "-p", port, "flash"], cwd=ROBOT_DIR, env=env, check=True)
    else:
        # Unix: source export.sh in a subshell
        shell_cmd = f'source "{idf_path}/export.sh" && idf.py -p "{port}" flash'
        subprocess.run(["bash", "-c", shell_cmd], cwd=ROBOT_DIR, env=env, check=True)


def flash_dongle():
    info("Building + flashing nRF52840 dongle...")
    build_script = REPO_ROOT / "scripts" / "build-dongle.py"
    subprocess.run([sys.executable, str(build_script), "flash"], check=True)


def monitor_esp32(port):
    info("Opening ESP32 monitor (Ctrl+] to exit)...")
    idf_path = Path.home() / "esp" / "esp-idf"
    env = os.environ.copy()
    env["IDF_PATH"] = str(idf_path)

    if platform.system() == "Windows":
        idf_py = shutil.which("idf.py")
        if not idf_py:
            error("idf.py not found in PATH.")
        subprocess.run([sys.executable, idf_py, "-p", port, "monitor"], cwd=ROBOT_DIR, env=env, check=True)
    else:
        shell_cmd = f'source "{idf_path}/export.sh" && idf.py -p "{port}" monitor'
        subprocess.run(["bash", "-c", shell_cmd], cwd=ROBOT_DIR, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description="Flash both devices and open ESP32 monitor")
    parser.add_argument("port", nargs="?", help="ESP32 serial port (auto-detected if omitted)")
    args = parser.parse_args()

    port = args.port if args.port else find_esp32_port()
    info(f"Using ESP32 port: {port}")

    flash_esp32(port)
    flash_dongle()
    monitor_esp32(port)


if __name__ == "__main__":
    main()
