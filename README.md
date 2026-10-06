# Loopglass

Loopglass is a Linux desktop utility that shows local web servers owned by your user account. It can open a server in your browser or ask to stop its owning process. It runs without root privileges, network accounts, or telemetry.

![Loopglass wordmark](loopglass/brand/loopglass-lockup-dark.svg)

## Install

Requires Linux, Python 3.10 through 3.14, a graphical desktop, and internet access to install Python dependencies. The current release has been exercised on a Wayland desktop; other Linux desktops need community testing. A system tray is optional. This source-available release is licensed for personal evaluation only.

1. Download the [latest source archive](https://github.com/Zykoraa/loopglass/releases/latest) from Releases and extract it, or clone this repository.
2. In the extracted directory, run `python3 install.py` as your normal user. Do not use `sudo`.
3. Open **Loopglass** from your application launcher, or run `~/.local/share/loopglass/venv/bin/loopglass`.

The installer creates a private virtual environment and a per-user desktop launcher. It uses `uv` when available and otherwise uses Python's `venv` and `pip`. It installs PySide6 and psutil from the Python package index. If your distro does not provide `venv` or `pip`, install its Python virtual-environment package or [uv](https://docs.astral.sh/uv/getting-started/installation/), then rerun the installer.

To start Loopglass at login, run `python3 install.py --autostart`. To disable login startup, run `python3 install.py --no-autostart`. Running `python3 install.py` from a newer download updates the installed app and preserves the current startup choice. To remove it, run `python3 install.py --uninstall` from any downloaded version. Removal keeps preferences in your normal Qt settings store. Respect `XDG_DATA_HOME` and `XDG_CONFIG_HOME` if you use custom paths.

For source development, create a virtual environment, install the project with `python -m pip install -e .`, then run `loopglass`. The `app.py` wrapper is kept for older local launchers.

## How it works

Loopglass scans TCP listeners owned by your normal Linux user account every 12 seconds. It sends a short `HEAD /` probe to candidate sockets to identify HTTP or HTTPS; this may appear in a server's access log. New and expired candidates are checked in bounded batches of up to 24 per scan, with eight parallel probes. An HTTP error response still counts as a web server. Non-HTTP services are never offered a Stop button.

**Running web apps** groups likely project servers by working directory and process. **All HTTP(S) listeners** includes every confirmed HTTP(S) socket, including helpers belonging to desktop applications. **Other listening ports** contains nonproject HTTP(S) sockets and sockets whose protocol could not be confirmed. Counts describe each view and can overlap. The address scope shows whether a listener is bound to loopback, one interface, or all interfaces.

Select a URL to open it or request **Stop gracefully**. Loopglass checks the original process, all of its user IDs, its start time, and the original socket inode before sending SIGTERM. If that process still owns the socket after two seconds, **Force stop** becomes available and asks again before SIGKILL. Stopping a process may close its other ports and may close a terminal, editor, or desktop helper if that program owns the selected socket. Read the confirmation dialog before proceeding. Loopglass does not stop a parent process or entire process tree automatically.

New project web apps can trigger a desktop notification after the first scan. Optional reminders count time since Loopglass first observed a port during this session, rather than claiming the socket's true creation time. When a tray is available, closing the window hides it; otherwise closing quits. The launcher raises an already-running instance.

## Limits and privacy

The main view uses a working-directory heuristic, so an installed helper may appear there if its current directory resembles a project, or a real project may appear only in **All HTTP(S) listeners**. Protocol checks recognize conventional HTTP response lines. HTTP/2-only services, unusual protocols, and services bound to unreachable addresses may stay in **Other listening ports**. Socket metadata cannot reliably identify which tool launched a process. A socket can change after a scan; the open and stop actions recheck its original ownership. Loopglass does not read process command-line arguments, which can contain secrets.

All scanning and preferences remain on your computer. Loopglass makes no outbound connections except when you choose to open a local URL in your browser; installation fetches dependencies from the package index. Linux system notifications may be sent through the tray or `notify-send`.

## Verify and report issues

Run `python3 -m unittest -v` from the source directory after installing dependencies. The integration tests launch and stop only their own temporary servers. For UI tests in a headless environment, use `QT_QPA_PLATFORM=offscreen`.

Please [file an issue](https://github.com/Zykoraa/loopglass/issues) with your Linux distribution, desktop environment, Python version, and the steps to reproduce. Avoid posting private paths or command-line arguments in public reports.

## Name, rights, and assets

**Loopglass** is a working product name. Before commercial sales, review Qt for Python licensing and the applicable LGPL obligations or obtain commercial Qt terms. Formal trademark, domain, and marketplace clearance remains to be done before broad commercial marketing. The code is source-available with rights reserved; see [LICENSE](LICENSE). Dependencies and the outlined Noto Sans wordmark have separate terms in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). The SVG mark and dark/light wordmarks are in `loopglass/brand/` and `loopglass/icon.svg`.
