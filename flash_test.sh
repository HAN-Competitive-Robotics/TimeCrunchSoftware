#!/usr/bin/env bash
# Build, flash both devices, then open ESP32 serial monitor.
# Usage: ./flash_test.sh [esp_port] [dongle_port]
#   esp_port    default: /dev/cu.usbserial-0001
#   dongle_port default: /dev/cu.usbmodem1301

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ESP_PORT="${1:-/dev/cu.usbserial-0001}"
IDF_PATH="$HOME/esp/esp-idf"

echo "=== Flashing ESP32 receiver on $ESP_PORT ==="
source "$IDF_PATH/export.sh"
cd "$SCRIPT_DIR/controller"
idf.py -p "$ESP_PORT" flash

echo ""
echo "=== Building + flashing nRF52840 dongle ==="
cd "$SCRIPT_DIR/DongleFirmware"
bash build.sh flash

echo ""
echo "=== Opening ESP32 monitor (Ctrl+] to exit) ==="
cd "$SCRIPT_DIR/controller"
idf.py -p "$ESP_PORT" monitor
