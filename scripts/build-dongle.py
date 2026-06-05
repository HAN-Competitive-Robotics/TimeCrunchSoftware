#!/usr/bin/env python3
"""Cross-platform build & flash script for the nRF52840 radio dongle."""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT        = Path(__file__).resolve().parent.parent
RADIO_DONGLE_DIR = REPO_ROOT / "radio-dongle"
BOARD            = "nrf52840dongle/nrf52840"
BUILD_DIR        = RADIO_DONGLE_DIR / "build"


def info(msg):
    print(f"[build-dongle] {msg}")


def error(msg):
    print(f"[build-dongle] ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _is_wsl():
    if platform.system() != "Linux":
        return False
    if "WSL_DISTRO_NAME" in os.environ or "WSLENV" in os.environ:
        return True
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except Exception:
        return False


def find_west():
    west = shutil.which("west")
    if west:
        return west

    env_file = RADIO_DONGLE_DIR / "local" / "ncs.env"
    if env_file.exists():
        ncs_toolchain = None
        for line in env_file.read_text().splitlines():
            if line.startswith("NCS_TOOLCHAIN="):
                ncs_toolchain = line.split("=", 1)[1].strip().strip('"')
        if ncs_toolchain:
            import glob
            tc = Path(ncs_toolchain)
            if platform.system() == "Windows":
                search_patterns = [
                    str(tc / "bin" / "west.exe"),
                    str(tc / "usr" / "bin" / "west.exe"),
                ]
            else:
                search_patterns = [
                    f"{ncs_toolchain}/bin/west",
                    f"{ncs_toolchain}/usr/bin/west",
                    f"{ncs_toolchain}/Cellar/python@*/**/bin/west",
                ]
            for pattern in search_patterns:
                matches = glob.glob(pattern)
                if matches:
                    return matches[0]

    if _is_wsl():
        import glob
        wsl_patterns = [
            "/mnt/c/ncs/toolchains/*/bin/west*",
            "/mnt/c/ncs/toolchains/*/usr/bin/west*",
        ]
        for pattern in wsl_patterns:
            matches = sorted(glob.glob(pattern))
            if matches:
                return matches[0]

    wsl_hint = ""
    if _is_wsl():
        wsl_hint = (
            "\n  WSL detected. Either:\n"
            "    1. Install nRF Connect SDK inside WSL, or\n"
            "    2. Create radio-dongle/local/ncs.env pointing to your Windows NCS install:\n"
            '       NCS_TOOLCHAIN=/mnt/c/ncs/toolchains/<hash>\n'
            '       NCS_SDK=/mnt/c/ncs/<version>'
        )

    error(
        "'west' not found in PATH.\n"
        "  macOS/Linux: copy radio-dongle/local/ncs.env.example to ncs.env and fill in your paths.\n"
        "  Windows:     ensure west is in your PATH (e.g. from nRF Connect SDK installation),\n"
        "               or set NCS_TOOLCHAIN in radio-dongle/local/ncs.env."
        + wsl_hint
    )


def find_nrfutil():
    nrfutil = shutil.which("nrfutil")
    if nrfutil:
        return nrfutil

    env_file = RADIO_DONGLE_DIR / "local" / "ncs.env"
    if env_file.exists():
        ncs_toolchain = None
        for line in env_file.read_text().splitlines():
            if line.startswith("NCS_TOOLCHAIN="):
                ncs_toolchain = line.split("=", 1)[1].strip().strip('"')
        if ncs_toolchain:
            tc = Path(ncs_toolchain)
            if platform.system() == "Windows":
                win_nrfutil = tc / "nrfutil" / "home" / "bin" / "nrfutil.exe"
                if win_nrfutil.exists():
                    return str(win_nrfutil)
            else:
                mac_nrfutil = tc / "nrfutil" / "home" / "bin" / "nrfutil"
                if mac_nrfutil.exists():
                    return str(mac_nrfutil)

    if _is_wsl():
        import glob
        wsl_patterns = [
            "/mnt/c/ncs/toolchains/*/nrfutil/home/bin/nrfutil*",
        ]
        for pattern in wsl_patterns:
            matches = sorted(glob.glob(pattern))
            if matches:
                return matches[0]

    wsl_hint = ""
    if _is_wsl():
        wsl_hint = (
            "\n  WSL detected. Either:\n"
            "    1. Install nRF Connect SDK inside WSL, or\n"
            "    2. Create radio-dongle/local/ncs.env pointing to your Windows NCS install:\n"
            '       NCS_TOOLCHAIN=/mnt/c/ncs/toolchains/<hash>'
        )

    error("'nrfutil' not found in PATH." + wsl_hint)


def setup_env():
    env = os.environ.copy()

    env_file = RADIO_DONGLE_DIR / "local" / "ncs.env"
    if env_file.exists():
        ncs_toolchain = None
        ncs_sdk = None
        for line in env_file.read_text().splitlines():
            if line.startswith("NCS_TOOLCHAIN="):
                ncs_toolchain = line.split("=", 1)[1].strip().strip('"')
            elif line.startswith("NCS_SDK="):
                ncs_sdk = line.split("=", 1)[1].strip().strip('"')

        if ncs_sdk:
            env["ZEPHYR_BASE"] = str(Path(ncs_sdk) / "zephyr")
        if ncs_toolchain:
            env["ZEPHYR_SDK_INSTALL_DIR"] = str(Path(ncs_toolchain) / "opt" / "zephyr-sdk")
            env["CMAKE_PREFIX_PATH"]       = str(Path(ncs_toolchain) / "opt" / "zephyr-sdk")
            env["NRFUTIL_HOME"]            = str(Path(ncs_toolchain) / "nrfutil" / "home")
            env["PATH"] = (
                str(Path(ncs_toolchain) / "bin")
                + os.pathsep
                + str(Path(ncs_toolchain) / "opt" / "python@3.12" / "bin")
                + os.pathsep
                + str(Path(ncs_toolchain) / "usr" / "bin")
                + os.pathsep
                + str(Path(ncs_toolchain) / "nrfutil" / "home" / "bin")
                + os.pathsep
                + env.get("PATH", "")
            )
            if platform.system() == "Darwin":
                env["DYLD_LIBRARY_PATH"] = "/Applications/SEGGER/JLink_V934b"
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONHOME", None)

    return env


def build(clean=False):
    west = find_west()
    env  = setup_env()

    if clean and BUILD_DIR.exists():
        info("Removing build directory...")
        shutil.rmtree(BUILD_DIR)

    info(f"Building for {BOARD}...")
    cmd = [
        west, "build",
        "--board", BOARD,
        "--build-dir", str(BUILD_DIR),
        "--no-sysbuild",
        str(RADIO_DONGLE_DIR),
    ]
    subprocess.run(cmd, env=env, check=True)
    info(f"Done. Artifacts in {BUILD_DIR}")


def flash(key_file=None):
    nrfutil = find_nrfutil()
    env      = setup_env()

    hex_file           = BUILD_DIR / "zephyr" / "zephyr.hex"
    zip_file           = BUILD_DIR / "dfu_package.zip"
    local_nrfutil_home = RADIO_DONGLE_DIR / "local" / "nrfutil-home"

    if not hex_file.exists():
        error(f"Hex file not found: {hex_file}. Build first.")

    info("Flashing via USB DFU (put dongle in bootloader mode first)...")

    nrf5sdk_tool = local_nrfutil_home / "bin" / "nrfutil-nrf5sdk-tools"
    if not nrf5sdk_tool.exists():
        info("Installing nrf5sdk-tools (one-time)...")
        local_nrfutil_home.mkdir(parents=True, exist_ok=True)
        (local_nrfutil_home / "bin").mkdir(parents=True, exist_ok=True)
        device_cmd = Path(env.get("NRFUTIL_HOME", "")) / "bin" / "nrfutil-device"
        if device_cmd.exists():
            dest = local_nrfutil_home / "bin" / "nrfutil-device"
            try:
                dest.symlink_to(device_cmd)
            except OSError:
                shutil.copy2(str(device_cmd), str(dest))
        env["NRFUTIL_HOME"] = str(local_nrfutil_home)
        subprocess.run([nrfutil, "install", "nrf5sdk-tools"], env=env, check=True)

    env["NRFUTIL_HOME"] = str(local_nrfutil_home)

    info("Packaging firmware...")
    pkg_cmd = [
        nrfutil, "nrf5sdk-tools", "pkg", "generate",
        "--hw-version", "52",
        "--sd-req", "0x00",
        "--application", str(hex_file),
        "--application-version", "1",
    ]
    if key_file:
        pkg_cmd += ["--key-file", str(key_file)]
    pkg_cmd.append(str(zip_file))
    subprocess.run(pkg_cmd, env=env, check=True)

    info("Programming...")
    try:
        subprocess.run(
            [nrfutil, "device", "program", "--firmware", str(zip_file), "--traits", "nordicDfu"],
            env=env, check=True,
        )
    except subprocess.CalledProcessError as e:
        error(
            "No DFU-capable device found.\n"
            "  Put the nRF52840 dongle in bootloader mode first:\n"
            "    1. Unplug the dongle\n"
            "    2. Hold the reset button\n"
            "    3. Plug it in while holding the button\n"
            "    4. Release the button — the LED should pulse"
        )
    info("Flash complete.")


def main():
    parser = argparse.ArgumentParser(description="Build / flash the radio dongle")
    parser.add_argument("action", nargs="?", choices=["build", "flash", "clean"], default="build")
    parser.add_argument("--key-file", type=Path, default=None, help="PEM private key for signing DFU package")
    args = parser.parse_args()

    if args.action == "clean":
        build(clean=True)
    elif args.action == "flash":
        build()
        flash(key_file=args.key_file)
    else:
        build()


if __name__ == "__main__":
    main()
