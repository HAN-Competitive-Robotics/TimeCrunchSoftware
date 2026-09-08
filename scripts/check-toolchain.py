#!/usr/bin/env python3
"""Report where this machine's toolchain differs from what the project pins.

    python scripts/check-toolchain.py

Every version this checks has already broken something here by drifting. The
point is to make that drift visible in one command instead of surfacing as a
compiler traceback, a missing Windows wheel, or keybinds that silently stop
working.

Exit code is 0 when everything matches, 1 otherwise, so CI or a pre-flight
script can gate on it. Nothing is installed or modified.
"""
import argparse
import platform
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import toolchain_versions as V

REPO_ROOT = Path(__file__).resolve().parent.parent

GOOD, BAD, WARN = "ok", "MISMATCH", "missing"
rows: list[tuple[str, str, str, str]] = []   # (status, what, want, got)


def record(status, what, want, got):
    rows.append((status, what, want, got))


def check_python():
    got = f"{sys.version_info.major}.{sys.version_info.minor}"
    record(GOOD if got == V.PYTHON else BAD, "Python", V.PYTHON, got)


def check_packages():
    try:
        from importlib import metadata
    except ImportError:
        record(WARN, "python packages", "-", "importlib.metadata unavailable")
        return
    for dist, want in V.PYTHON_PACKAGES.items():
        try:
            got = metadata.version(dist)
        except metadata.PackageNotFoundError:
            record(WARN, dist, want, "not installed")
            continue
        record(GOOD if got == want else BAD, dist, want, got)


def _git_describe(path: Path) -> str | None:
    if not (path / ".git").exists() and not (path / ".git").is_file():
        return None
    try:
        out = subprocess.run(["git", "-C", str(path), "describe", "--tags"],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


def check_esp_idf():
    import os
    candidates = []
    if os.environ.get("IDF_PATH"):
        candidates.append(Path(os.environ["IDF_PATH"]))
    candidates.append(Path.home() / "esp" / "esp-idf")

    for path in candidates:
        if not path.exists():
            continue
        got = _git_describe(path)
        if got is None:
            record(WARN, f"ESP-IDF ({path})", V.ESP_IDF, "no git metadata")
            return
        # A tagged release describes exactly as the tag; anything else is a
        # development snapshot some distance past one.
        record(GOOD if got == V.ESP_IDF else BAD, f"ESP-IDF ({path})",
               V.ESP_IDF, got)
        return
    record(WARN, "ESP-IDF", V.ESP_IDF, "not found")


def check_ncs():
    env = REPO_ROOT / "radio-dongle" / "local" / "ncs.env"
    if not env.exists():
        record(WARN, "nRF Connect SDK", V.NCS, "no radio-dongle/local/ncs.env")
        return
    m = re.search(r'NCS_SDK\s*=\s*"?([^"\n]+)', env.read_text())
    if not m:
        record(WARN, "nRF Connect SDK", V.NCS, "NCS_SDK not set in ncs.env")
        return
    sdk = Path(m.group(1).strip())
    got = sdk.name  # by convention the directory is named for the version
    record(GOOD if got == V.NCS else BAD, f"nRF Connect SDK ({sdk})", V.NCS, got)


def check_requirements_match():
    """The pins in requirements.txt must agree with toolchain_versions.py."""
    req = REPO_ROOT / "driver" / "requirements.txt"
    if not req.exists():
        record(WARN, "requirements.txt", "-", "not found")
        return
    pinned = dict(re.findall(r"^([A-Za-z0-9_.-]+)==([^\s#]+)", req.read_text(), re.M))
    for dist, want in V.PYTHON_PACKAGES.items():
        got = pinned.get(dist)
        if got is None:
            record(BAD, f"requirements.txt {dist}", f"=={want}", "not pinned with ==")
        else:
            record(GOOD if got == want else BAD,
                   f"requirements.txt {dist}", want, got)


def main():
    ap = argparse.ArgumentParser(description="Check toolchain versions")
    ap.add_argument("--quiet", action="store_true",
                    help="Only print problems")
    args = ap.parse_args()

    print(f"Platform: {platform.platform()}")
    print(f"Checking against the pins in scripts/toolchain_versions.py")
    print()

    check_python()
    check_packages()
    check_requirements_match()
    check_esp_idf()
    check_ncs()

    width = max(len(w) for _, w, _, _ in rows)
    problems = 0
    for status, what, want, got in rows:
        if status == GOOD and args.quiet:
            continue
        mark = {GOOD: "ok  ", BAD: "FAIL", WARN: "warn"}[status]
        print(f"  {mark}  {what:<{width}}  want {want:<10} got {got}")
        if status == BAD:
            problems += 1

    print()
    if problems:
        print(f"{problems} mismatch(es).")
        print("A 'warn' is a tool this machine does not have, which is fine if")
        print("you do not build that part. A 'FAIL' is a version that will")
        print("produce different results from everyone else's machine.")
    else:
        print("Everything matches.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
