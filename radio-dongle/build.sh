#!/usr/bin/env bash
# Build script for radio-dongle (nRF52840 USB CDC → ESB bridge)
#
# Usage:
#   ./build.sh          — configure + build
#   ./build.sh clean    — delete build directory and rebuild
#   ./build.sh flash    — build then flash via nrfjprog

set -euo pipefail

BOARD="nrf52840dongle/nrf52840"
BUILD_DIR="build"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/local/ncs.env"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found."
    echo "Copy local/ncs.env.example to local/ncs.env and fill in your paths."
    exit 1
fi

# shellcheck source=local/ncs.env
source "$ENV_FILE"

WEST="$NCS_TOOLCHAIN/Cellar/python@3.12/3.12.4/Frameworks/Python.framework/Versions/3.12/bin/west"
export ZEPHYR_BASE="$NCS_SDK/zephyr"
export ZEPHYR_SDK_INSTALL_DIR="$NCS_TOOLCHAIN/opt/zephyr-sdk"
export CMAKE_PREFIX_PATH="$NCS_TOOLCHAIN/opt/zephyr-sdk"

# Ensure the NCS toolchain Python and nrfutil take priority over any active venv
unset VIRTUAL_ENV PYTHONHOME
export NRFUTIL_HOME="$NCS_TOOLCHAIN/nrfutil/home"
export DYLD_LIBRARY_PATH="/Applications/SEGGER/JLink_V934b${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
export PATH="$NCS_TOOLCHAIN/bin:$NCS_TOOLCHAIN/opt/python@3.12/bin:$NCS_TOOLCHAIN/usr/bin:$NCS_TOOLCHAIN/nrfutil/home/bin:$PATH"

if [[ ! -x "$WEST" ]]; then
    echo "Error: west not found at $WEST"
    echo "Check NCS_TOOLCHAIN in local/ncs.env is correct."
    exit 1
fi

if [[ "${1:-}" == "clean" ]]; then
    echo "Removing build directory..."
    rm -rf "$SCRIPT_DIR/$BUILD_DIR"
fi

echo "Building for $BOARD..."
"$WEST" build \
    --board "$BOARD" \
    --build-dir "$SCRIPT_DIR/$BUILD_DIR" \
    --no-sysbuild \
    "$SCRIPT_DIR"

if [[ "${1:-}" == "flash" ]]; then
    echo "Flashing via USB DFU (put dongle in bootloader mode first)..."
    NRFUTIL="$NCS_TOOLCHAIN/nrfutil/home/bin/nrfutil"
    LOCAL_NRFUTIL_HOME="$SCRIPT_DIR/local/nrfutil-home"
    HEX="$SCRIPT_DIR/$BUILD_DIR/zephyr/zephyr.hex"
    ZIP="$SCRIPT_DIR/$BUILD_DIR/dfu_package.zip"

    # Install nrf5sdk-tools locally on first run
    if [[ ! -f "$LOCAL_NRFUTIL_HOME/bin/nrfutil-nrf5sdk-tools" ]]; then
        echo "Installing nrf5sdk-tools (one-time)..."
        mkdir -p "$LOCAL_NRFUTIL_HOME"
        # Symlink device subcommand so nrfutil can still find it
        mkdir -p "$LOCAL_NRFUTIL_HOME/bin"
        ln -sf "$NCS_TOOLCHAIN/nrfutil/home/bin/nrfutil-device" "$LOCAL_NRFUTIL_HOME/bin/nrfutil-device"
        NRFUTIL_HOME="$LOCAL_NRFUTIL_HOME" "$NRFUTIL" install nrf5sdk-tools
    fi

    export NRFUTIL_HOME="$LOCAL_NRFUTIL_HOME"

    echo "Packaging firmware..."
    "$NRFUTIL" nrf5sdk-tools pkg generate \
        --hw-version 52 \
        --sd-req 0x00 \
        --application "$HEX" \
        --application-version 1 \
        "$ZIP"

    echo "Programming..."
    "$NRFUTIL" device program --firmware "$ZIP" --traits nordicDfu
    echo "Flash complete."
fi

echo "Done. Artifacts in $SCRIPT_DIR/$BUILD_DIR"
