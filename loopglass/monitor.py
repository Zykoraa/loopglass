"""Unprivileged discovery and guarded process control for local TCP web apps."""

from __future__ import annotations

import ipaddress
import os
import signal
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path

import psutil


@dataclass(frozen=True)
class Listener:
    pid: int
    started: float
    name: str
    cwd: str
    family: int
    bind_host: str
    port: int
    protocol: str | None = None
    inode: int | None = None

    @property
    def key(self) -> tuple:
        return (self.pid, self.started, self.family, self.bind_host, self.port, self.inode)

    @property
    def scope(self) -> str:
        address = ipaddress.ip_address(self.bind_host.split("%")[0])
        if address.is_unspecified:
            return "All interfaces"
        if address.is_loopback:
            return "Loopback only"
        return "Specific interface"

    @property
    def connect_host(self) -> str:
        if ipaddress.ip_address(self.bind_host.split("%")[0]).is_unspecified:
            return "127.0.0.1" if self.family == socket.AF_INET else "::1"
        return self.bind_host

    @property
    def url(self) -> str:
        host = self.connect_host
        if self.family == socket.AF_INET6:
            host = f"[{host.replace('%', '%25')}]"
        return f"{self.protocol or 'http'}://{host}:{self.port}/"


def is_web_app(item: Listener) -> bool:
    """Prefer user workspaces, including external mounts, over installed app helpers."""
    if not item.protocol or not item.cwd:
        return False
    try:
        cwd = Path(item.cwd).resolve()
        installed_roots = ("/usr", "/opt", "/var", "/run", "/etc", "/bin", "/sbin", "/lib", "/lib64")
        return cwd != Path("/") and not any(
            cwd.is_relative_to(root) for root in installed_roots
        )
    except OSError:
        return False


@dataclass(frozen=True)
class StopResult:
    closed: bool
    can_force: bool
    message: str


def _owns_listener(proc: psutil.Process, target: Listener) -> bool:
    try:
        if abs(proc.create_time() - target.started) > 0.001:
            return False
        if target.inode is None:
            return False
        for conn in proc.net_connections(kind="tcp"):
            if (conn.status == psutil.CONN_LISTEN and conn.family == target.family
                    and conn.laddr and conn.laddr.ip == target.bind_host
                    and conn.laddr.port == target.port and conn.fd >= 0):
                try:
                    if os.stat(f"/proc/{target.pid}/fd/{conn.fd}").st_ino == target.inode:
                        return True
                except (FileNotFoundError, PermissionError, OSError):
                    continue
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        pass
    return False


def discover_listeners() -> list[Listener]:
    """Return TCP listeners owned by this UID; inaccessible system sockets are omitted."""
    result = []
    uid = os.getuid()
    if uid == 0 or os.getresuid() != (uid, uid, uid):
        return []
    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, OSError):
        connections = []
    processes: dict[int, psutil.Process] = {}
    for conn in connections:
        if conn.status != psutil.CONN_LISTEN or not conn.laddr or conn.pid is None:
            continue
        try:
            proc = processes.setdefault(conn.pid, psutil.Process(conn.pid))
            credentials = proc.uids()
            if (credentials.real, credentials.effective, credentials.saved) != (uid, uid, uid):
                continue
            started = proc.create_time()
            name = proc.name()
            try:
                cwd = proc.cwd()
            except (psutil.AccessDenied, OSError):
                cwd = ""
            try:
                inode = os.stat(f"/proc/{conn.pid}/fd/{conn.fd}").st_ino if conn.fd >= 0 else None
            except (FileNotFoundError, PermissionError, OSError):
                inode = None
            result.append(Listener(conn.pid, started, name, cwd,
                                   conn.family, conn.laddr.ip, conn.laddr.port, inode=inode))
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            continue
    return sorted({item.key: item for item in result}.values(),
                  key=lambda item: (item.cwd, item.pid, item.port, item.bind_host))


def _http_response(sock: socket.socket) -> bool:
    sock.settimeout(0.45)
    sock.sendall(b"HEAD / HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n\r\n")
    return sock.recv(32).startswith((b"HTTP/1.", b"HTTP/2"))


def probe_protocol(item: Listener) -> str | None:
    """Make at most one short HTTP and one HTTPS attempt to an owned local socket."""
    address = (item.connect_host, item.port)
    if item.family == socket.AF_INET6:
        address = (item.connect_host, item.port, 0, 0)
    try:
        with socket.socket(item.family, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.45)
            sock.connect(address)
            if _http_response(sock):
                return "http"
    except (OSError, TimeoutError):
        pass
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        with socket.socket(item.family, socket.SOCK_STREAM) as raw:
            raw.settimeout(0.45)
            raw.connect(address)
            with context.wrap_socket(raw, server_hostname="localhost") as secure:
                if _http_response(secure):
                    return "https"
    except (OSError, TimeoutError, ssl.SSLError):
        pass
    return None


class Scanner:
    MAX_PROBES_PER_SCAN = 24
    PROBE_WORKERS = 8

    def __init__(self, reprobe_seconds: float = 60):
        self.reprobe_seconds = reprobe_seconds
        self.cache: dict[tuple, tuple[float, str | None]] = {}

    def scan(self) -> list[Listener]:
        listeners = discover_listeners()
        now = time.monotonic()
        current = {item.key for item in listeners}
        self.cache = {key: value for key, value in self.cache.items() if key in current}
        unprobed = [item for item in listeners if item.inode is not None and item.key not in self.cache]
        expired = [item for item in listeners if item.inode is not None and item.key in self.cache
                   and now - self.cache[item.key][0] >= self.reprobe_seconds]
        due = unprobed + sorted(expired, key=lambda item: self.cache[item.key][0])
        # Keep UI scans bounded even when many ports do not respond to HTTP.
        with ThreadPoolExecutor(max_workers=self.PROBE_WORKERS) as pool:
            results = list(pool.map(probe_protocol, due[:self.MAX_PROBES_PER_SCAN]))
        for item, protocol in zip(due, results):
            self.cache[item.key] = (now, protocol if owns_listener(item) else None)
        return [replace(item, protocol=self.cache.get(item.key, (0, None))[1]) for item in listeners]


def owns_listener(item: Listener) -> bool:
    """Check that the original process still owns the original socket inode."""
    try:
        return _owns_listener(psutil.Process(item.pid), item)
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False


def stop_listener(item: Listener, force: bool = False, wait_seconds: float = 2.0) -> StopResult:
    """Signal only the original socket owner, then verify that its listener closed."""
    if not item.protocol:
        return StopResult(False, False, "This port was not confirmed as a web app.")
    try:
        proc = psutil.Process(item.pid)
        uid = os.getuid()
        credentials = proc.uids()
        if uid == 0 or os.getresuid() != (uid, uid, uid) or (credentials.real, credentials.effective, credentials.saved) != (uid, uid, uid):
            return StopResult(False, False, "This process does not have a normal user identity.")
        if item.inode is None:
            return StopResult(False, False, "The original socket identity is unavailable; nothing was signaled.")
        # A pidfd pins the process identity across the final check and signal.
        pidfd = os.pidfd_open(item.pid) if hasattr(os, "pidfd_open") else None
        try:
            if not _owns_listener(proc, item):
                return StopResult(False, False, "The original process no longer owns this port. Nothing was signaled.")
            credentials = proc.uids()
            if (credentials.real, credentials.effective, credentials.saved) != (uid, uid, uid):
                return StopResult(False, False, "The process identity changed; nothing was signaled.")
            sig = signal.SIGKILL if force else signal.SIGTERM
            if pidfd is not None and hasattr(signal, "pidfd_send_signal"):
                signal.pidfd_send_signal(pidfd, sig)
            else:
                # psutil checks process create time before signaling.
                proc.send_signal(sig)
        finally:
            if pidfd is not None:
                os.close(pidfd)
    except (psutil.NoSuchProcess, ProcessLookupError):
        return StopResult(True, False, "The original process already exited; its listener is no longer owned by it.")
    except (psutil.AccessDenied, PermissionError, OSError) as exc:
        return StopResult(False, False, f"Could not signal process {item.pid}: {exc}")

    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if not _owns_listener(proc, item):
            return StopResult(True, False, f"The original process no longer owns port {item.port}.")
        time.sleep(0.1)
    if _owns_listener(proc, item):
        action = "Force stop is available." if not force else "The port is still open."
        return StopResult(False, not force, f"Port {item.port} is still owned by process {item.pid}. {action}")
    return StopResult(True, False, f"The original process no longer owns port {item.port}.")
