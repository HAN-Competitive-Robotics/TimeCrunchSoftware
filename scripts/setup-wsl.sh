#!/usr/bin/env bash
# One-shot WSL setup for building and flashing the robot firmware.
#
# Usage from the repo root:
#   ./scripts/setup-wsl.sh
#
# Installs the ESP-IDF build dependencies, clones ESP-IDF to ~/esp/esp-idf
# (the only location scripts/flash.py checks on Linux), and installs the esp32
# toolchain. Safe to re-run; each step is skipped if already done.
#
# Pin a different ESP-IDF release with:
#   IDF_VERSION=v5.5.5 ./scripts/setup-wsl.sh
#
# This does NOT set up the ground station. driver/station.py needs a gamepad
# and a GPU, neither of which WSL exposes by default, so it belongs on native
# Windows Python. See docs/onboarding.md.

set -euo pipefail

IDF_VERSION="${IDF_VERSION:-v5.4.4}"
IDF_DIR="$HOME/esp/esp-idf"

info() { printf '[setup-wsl] %s\n' "$*"; }
die()  { printf '[setup-wsl] ERROR: %s\n' "$*" >&2; exit 1; }

if ! grep -qi microsoft /proc/version 2>/dev/null; then
	die "This does not look like WSL. Run it inside your WSL distribution."
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------- line endings
# A clone made on the Windows side with core.autocrlf=true leaves CRLF in
# robot/idf, which fails here as "bad interpreter: /bin/bash^M".
if grep -qU $'\r' "$REPO_ROOT/robot/idf" 2>/dev/null; then
	if [ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]; then
		info "WARNING: robot/idf has Windows line endings, but you have uncommitted"
		info "         changes so it was left alone. Commit or stash, then re-run."
	else
		info "Fixing Windows line endings in the checkout..."
		git -C "$REPO_ROOT" config core.autocrlf input
		git -C "$REPO_ROOT" rm --cached -r . >/dev/null
		git -C "$REPO_ROOT" reset --hard
	fi
else
	info "Line endings OK."
fi

# --------------------------------------------------------------- apt packages
info "Installing build dependencies (sudo password may be requested)..."
sudo apt-get update
sudo apt-get install -y \
	git wget flex bison gperf ccache dfu-util \
	cmake ninja-build libffi-dev libssl-dev libusb-1.0-0 \
	python3 python3-venv python3-setuptools python3-serial

# python3-serial rather than "pip install pyserial": Ubuntu 23.04+ refuses pip
# installs outside a venv (PEP 668), and scripts/flash.py imports serial.

# -------------------------------------------------------------------- ESP-IDF
if [ -d "$IDF_DIR/.git" ]; then
	info "ESP-IDF already present at $IDF_DIR, skipping clone."
else
	info "Cloning ESP-IDF $IDF_VERSION to $IDF_DIR (this takes a while)..."
	mkdir -p "$HOME/esp"
	git clone --depth 1 --shallow-submodules --recursive \
		--branch "$IDF_VERSION" \
		https://github.com/espressif/esp-idf.git "$IDF_DIR"
fi

info "Installing the esp32 toolchain (downloads roughly 1.5 GB)..."
( cd "$IDF_DIR" && ./install.sh esp32 )

# ---------------------------------------------------------------- convenience
if ! grep -q "alias get_idf=" "$HOME/.bashrc" 2>/dev/null; then
	info "Adding 'get_idf' alias to ~/.bashrc"
	printf "\nalias get_idf='. %s/export.sh'\n" "$IDF_DIR" >> "$HOME/.bashrc"
fi

cat <<'DONE'

[setup-wsl] Done.

Next steps:

  1. Activate the toolchain in each new shell:
       get_idf                 (or: . ~/esp/esp-idf/export.sh)

  2. Hand the board to WSL. In an Administrator PowerShell on Windows:
       usbipd list                       # note the board's BUSID
       usbipd bind   --busid <BUSID>     # once per device
       usbipd attach --wsl --busid <BUSID>
     Repeat the attach after every unplug.

  3. Give yourself serial access (once, then 'wsl --shutdown' from Windows):
       sudo usermod -aG dialout $USER

  4. Check the board is visible, then flash:
       python3 scripts/find-ports.py
       python3 scripts/flash.py --robot

The ground station runs on native Windows, not here:
       py -3.12 -m pip install -r driver\requirements.txt
       py -3.12 driver\station.py
DONE
