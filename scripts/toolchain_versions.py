"""Single source of truth for every external version this project pins.

Every tool here has already caused a real failure by being unpinned. Change a
version in this file, not in the docs, the setup script, or a README, and the
rest follows.
"""

# Exact interpreter, not a floor. pygame 2.6.1 publishes no Windows wheel above
# cp313, so "3.10 or newer" sends people to 3.14 where pip falls back to a
# source build and dies in the MSVC compiler.
PYTHON = "3.12"

# Tagged release, not master. An unpinned esp-idf clone gets the rolling
# development branch, which is currently v6.1-dev: a moving snapshot nobody can
# reproduce from a version number, and a major version ahead of this code.
ESP_IDF = "v5.4.4"

# The dongle project uses the legacy Zephyr USB device stack
# (CONFIG_USB_DEVICE_STACK=y), which the NCS 3.x line drops, and the
# nrf52840dongle/nrf52840 board name plus --no-sysbuild both assume 2.7.
NCS = "v2.7.0"

# Mirrors driver/requirements.txt. Kept here so the checker can report a
# mismatch without parsing pip metadata formats.
PYTHON_PACKAGES = {
    "pyserial":  "3.5",
    "pygame":    "2.6.1",
    "dearpygui": "2.3.1",
}

# Import name for each distribution, where they differ.
IMPORT_NAMES = {
    "pyserial": "serial",
}
