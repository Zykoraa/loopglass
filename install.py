#!/usr/bin/env python3
"""Per-user installer for Loopglass from a source checkout or release archive."""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def xdg_path(name: str, fallback: str) -> Path:
    return Path(os.environ.get(name) or Path.home() / fallback).expanduser().resolve()


def desktop_exec(path: Path) -> str:
    value = str(path).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`").replace("%", "%%")
    return f'"{value}"'


def write_desktop(path: Path, executable: Path, autostart: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    command = desktop_exec(executable) + (" --autostart" if autostart else "")
    path.write_text(
        "[Desktop Entry]\nType=Application\nName=Loopglass\n"
        "Comment=Find and safely stop local web apps\n"
        f"Exec={command}\nIcon=loopglass\nTerminal=false\n"
        "Categories=Utility;Development;\nStartupNotify=true\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--autostart", action="store_true", help="start at login")
    action.add_argument("--no-autostart", action="store_true", help="disable login startup")
    action.add_argument("--uninstall", action="store_true", help="remove the per-user install")
    args = parser.parse_args()
    if platform.system() != "Linux" or os.geteuid() == 0:
        parser.error("Loopglass must be installed by a normal Linux user, without sudo")
    if not (3, 10) <= sys.version_info[:2] < (3, 15):
        parser.error("Python 3.10 through 3.14 is required")

    data = xdg_path("XDG_DATA_HOME", ".local/share")
    config = xdg_path("XDG_CONFIG_HOME", ".config")
    app_dir = data / "loopglass"
    venv = app_dir / "venv"
    executable = venv / "bin/loopglass"
    marker = app_dir / ".loopglass-managed"
    desktop = data / "applications/loopglass.desktop"
    autostart = config / "autostart/loopglass.desktop"
    icon = data / "icons/hicolor/scalable/apps/loopglass.svg"

    if args.uninstall:
        for path in (desktop, autostart, icon):
            path.unlink(missing_ok=True)
        if marker.is_file():
            shutil.rmtree(app_dir)
        print("Loopglass per-user installation removed. Preferences were kept.")
        return 0

    app_dir.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv")
    if not venv.exists():
        if uv:
            subprocess.run([uv, "venv", "--python", sys.executable, str(venv)], check=True)  # nosec B603
        else:
            subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)  # nosec B603
    python = venv / "bin/python"
    if uv:
        subprocess.run([uv, "pip", "install", "--python", str(python), "--upgrade", str(ROOT)], check=True)  # nosec B603
    else:
        subprocess.run([str(python), "-m", "pip", "install", "--upgrade", str(ROOT)], check=True)  # nosec B603
    marker.write_text("Managed by Loopglass install.py\n", encoding="utf-8")
    icon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "loopglass/icon.svg", icon)
    write_desktop(desktop, executable, autostart=False)
    if args.autostart:
        write_desktop(autostart, executable, autostart=True)
    elif args.no_autostart:
        autostart.unlink(missing_ok=True)
    print(f"Installed Loopglass: {executable}")
    print(f"Launcher: {desktop}")
    print("Login startup: enabled" if autostart.exists() else "Login startup: disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
