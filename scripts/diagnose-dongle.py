#!/usr/bin/env python3
"""Collect everything needed to diagnose a dongle that won't accept data.

    python scripts/diagnose-dongle.py

Read-only apart from one optional 5-byte neutral packet (motors stopped,
weapon off), the same bytes the ground station sends while idle. Skip even
that with --no-write. Nothing here can block: every serial call has a timeout.

Paste the whole output when reporting a problem.
"""

import argparse
import platform
import re
import sys
import time
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parent.parent
DONGLE_DIR  = REPO_ROOT / "radio-dongle"
BUILD_DIR   = DONGLE_DIR / "build" / "zephyr"

# 1915 = Nordic (bootloader), 2fe3 = Zephyr Project (our firmware running)
DONGLE_VIDS = (0x1915, 0x2FE3)


def hdr(title):
    print()
    print("=" * 68)
    print(title)
    print("=" * 68)


def section_host():
    hdr("1. HOST")
    print(f"platform : {platform.platform()}")
    print(f"python   : {sys.version.split()[0]} ({sys.executable})")
    try:
        import serial
        print(f"pyserial : {serial.__version__}")
    except ImportError:
        print("pyserial : NOT INSTALLED  -> pip install pyserial")


def section_ports():
    """Every serial port with full identity, so we can see what Windows bound."""
    hdr("2. SERIAL PORTS")
    try:
        import serial.tools.list_ports
    except ImportError:
        print("pyserial missing, skipping")
        return []

    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("No serial ports at all.")
        return []

    candidates = []
    for p in ports:
        vid = f"{p.vid:04x}" if p.vid is not None else "----"
        pid = f"{p.pid:04x}" if p.pid is not None else "----"
        is_dongle = p.vid in DONGLE_VIDS
        mark = "  <-- DONGLE" if is_dongle else ""
        print(f"{p.device:<14} vid:pid={vid}:{pid}  {p.description}{mark}")
        print(f"{'':<14} hwid={p.hwid}")
        if is_dongle:
            candidates.append(p.device)

    if not candidates:
        print("\nNo port with a Nordic (1915) or Zephyr (2fe3) VID.")
        print("The dongle is either unplugged or not enumerating.")
    return candidates


def _read_kv(path, keys):
    if not path.exists():
        return None
    found = {}
    for line in path.read_text(errors="replace").splitlines():
        for k in keys:
            if line.startswith(k + "=") or line == f"# {k} is not set":
                found[k] = line.strip()
    return found


def section_build():
    """What the firmware was actually built with, from the generated config."""
    hdr("3. FIRMWARE BUILD")
    cfg = BUILD_DIR / ".config"
    if not cfg.exists():
        print(f"No build found at {cfg}")
        print("This machine has not built the dongle firmware.")
        return

    keys = [
        "CONFIG_CLOCK_CONTROL",
        "CONFIG_CLOCK_CONTROL_NRF",
        "CONFIG_ESB",
        "CONFIG_USB_DEVICE_STACK",
        "CONFIG_USB_CDC_ACM",
        "CONFIG_UART_CONSOLE",
        "CONFIG_UART_INTERRUPT_DRIVEN",
        "CONFIG_LOG_MODE_DEFERRED",
    ]
    found = _read_kv(cfg, keys)
    for k in keys:
        print(found.get(k, f"{k}: (absent)"))

    # Which device the app actually talks to: usb.c uses DT_CHOSEN(zephyr_console)
    dts = BUILD_DIR / "zephyr.dts"
    print()
    if dts.exists():
        text = dts.read_text(errors="replace")
        m = re.search(r"chosen\s*\{(.*?)\}", text, re.S)
        if m:
            for line in m.group(1).splitlines():
                if line.strip():
                    print("  " + line.strip())
        console = re.search(r"zephyr,console\s*=\s*&?([\w\-]+)", text)
        if console:
            node = console.group(1)
            print(f"\n-> zephyr,console resolves to: {node}")
            if "cdc" not in node.lower():
                print("   WARNING: not a CDC ACM node. usb.c reads/writes this")
                print("   device, so the app would be talking to a hardware UART")
                print("   while the host talks to a USB endpoint nobody reads.")
    else:
        print(f"No {dts.name} (build incomplete?)")


def section_live(port, do_write):
    """Does the dongle accept a write, and does it say anything?"""
    hdr(f"4. LIVE TEST ON {port}")
    import serial

    try:
        # write_timeout is the point of this test: without it a stalled
        # endpoint blocks forever instead of reporting.
        ser = serial.Serial(port, 115200, timeout=1.0, write_timeout=2.0)
    except Exception as e:
        print(f"OPEN FAILED: {type(e).__name__}: {e}")
        print("Something else holds the port, or the driver is unhappy.")
        return

    print(f"opened OK   dsr={ser.dsr} cts={ser.cts}")

    if do_write:
        pkt = b"7f7f0000\n"      # motors stopped, weapon off, failsafe clear
        try:
            t0 = time.time()
            ser.write(pkt)
            ser.flush()
            print(f"write OK    {len(pkt)} bytes in {time.time()-t0:.3f}s")
            print("            -> the dongle IS draining its USB endpoint")
        except serial.SerialTimeoutException:
            print("write TIMED OUT after 2s")
            print("            -> the dongle is NOT reading its USB endpoint.")
            print("            -> usb_rx_thread is not running, which means")
            print("               main() never reached its loop (check the LED)")
        except Exception as e:
            print(f"write FAILED: {type(e).__name__}: {e}")

    print("\nreading quietly for 2s (no reset yet)")
    t0, got = time.time(), b""
    while time.time() - t0 < 2.0:
        try:
            got += ser.read(256)
        except Exception:
            break
    print(got.decode(errors="replace") if got else "(silence, expected when idle)")

    try:
        ser.close()
    except Exception:
        pass


def _find_dongle_port():
    import serial.tools.list_ports
    for p in serial.tools.list_ports.comports():
        if p.vid in DONGLE_VIDS:
            return p.device
    return None


def section_bootlog(port, seconds=25):
    """Catch the init log, reconnecting across the reset's re-enumeration.

    A reset drops the USB device and brings it back, so the log we want
    arrives on a new handle. Reopen in a loop, and re-scan for the port in
    case the OS assigns a different one.
    """
    hdr("5. BOOT LOG")
    import serial

    print("PRESS THE RESET BUTTON ONCE NOW  (a short press and release).")
    print("Do NOT hold it, and do NOT unplug: holding it during a replug is")
    print("DFU mode, where the application never runs and prints nothing.")
    print(f"Listening on {port} for {seconds}s, reconnecting as needed.")
    print("-" * 68)

    end = time.time() + seconds
    ser, got = None, b""

    while time.time() < end:
        if ser is None:
            try:
                ser = serial.Serial(port, 115200, timeout=0.2)
            except Exception:
                rescanned = _find_dongle_port()
                if rescanned and rescanned != port:
                    print(f"\n[port moved to {rescanned}]")
                    port = rescanned
                time.sleep(0.1)
                continue
        try:
            d = ser.read(256)
            if d:
                got += d
                sys.stdout.write(d.decode(errors="replace"))
                sys.stdout.flush()
        except Exception:
            try:
                ser.close()
            except Exception:
                pass
            ser = None

    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass

    print()
    print("-" * 68)
    if not got:
        print("NOTHING received across the whole window.")
        print("If the LED is also dark, the firmware is not running its main")
        print("loop at all, which points at an init failure before that point.")


def main():
    ap = argparse.ArgumentParser(description="Diagnose the nRF52840 dongle link")
    ap.add_argument("--port", help="Force a port instead of auto-detecting")
    ap.add_argument("--no-write", action="store_true",
                    help="Skip the write test (read-only)")
    ap.add_argument("--no-reset", action="store_true",
                    help="Skip the boot-log capture that needs a RESET press")
    ap.add_argument("--reset-window", type=int, default=25, metavar="SEC",
                    help="Seconds to listen for the boot log (default 25)")
    args = ap.parse_args()

    print("nRF52840 dongle diagnostics  (paste this whole output)")
    section_host()
    candidates = section_ports()
    section_build()

    port = args.port or (candidates[0] if candidates else None)
    if port:
        section_live(port, do_write=not args.no_write)
        if not args.no_reset:
            section_bootlog(port, seconds=args.reset_window)
    else:
        hdr("4. LIVE TEST")
        print("Skipped: no dongle port found. Pass --port COMx to force one.")

    hdr("6. ANSWER THESE BY EYE")
    print("a) Is the dongle's LED blinking about once a second?  YES / NO")
    print("   (it should blink constantly whenever the firmware is running,")
    print("    with or without any data arriving)")
    print("b) Is the dongle plugged directly into the laptop, or via a hub?")
    print("c) Does 'usbipd list' show the dongle as Attached or Shared?")


if __name__ == "__main__":
    main()
