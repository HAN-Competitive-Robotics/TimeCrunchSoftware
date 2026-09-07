#!/usr/bin/env python3
"""WSL detection and the hints the flash scripts need when running under it.

WSL2 exposes no USB devices to Linux by default, so a board plugged into the
Windows host stays invisible until it is attached with usbipd-win. Both
flash.py and build-dongle.py have to explain that, so it lives here.
"""

import os
import platform
from pathlib import Path


def is_wsl():
    if platform.system() != "Linux":
        return False
    if "WSL_DISTRO_NAME" in os.environ or "WSLENV" in os.environ:
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


USBIPD_HINT = (
    "  WSL detected. WSL2 cannot see USB devices until Windows hands them over.\n"
    "  In an Administrator PowerShell on the Windows side:\n"
    "    usbipd list                       # note the board's BUSID\n"
    "    usbipd bind   --busid <BUSID>     # once per device\n"
    "    usbipd attach --wsl --busid <BUSID>\n"
    "  The attach is lost on every unplug and must be repeated.\n"
    "  Install usbipd-win with: winget install --exact dorssel.usbipd-win"
)

DIALOUT_HINT = (
    "  On WSL/Linux the port also needs group access:\n"
    "    sudo usermod -aG dialout $USER\n"
    "  then run 'wsl --shutdown' from Windows and reopen the terminal."
)
