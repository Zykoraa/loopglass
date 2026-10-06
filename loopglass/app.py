"""Window and optional tray for the local web app monitor."""

from __future__ import annotations

import argparse
import fcntl
import os
import shutil
import socket
import stat

# notify-send is invoked with a fixed executable and an argument list.
import subprocess  # nosec B404
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QRunnable,
    QSettings,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QFont,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtSvgWidgets import QSvgWidget
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSystemTrayIcon,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .monitor import (
    Listener,
    Scanner,
    StopResult,
    is_web_app,
    owns_listener,
    stop_listener,
)
from .theme import COLORS, MENU_STYLE, WINDOW_STYLE

APP_DIR = Path(__file__).resolve().parent


def icon_with_count(count: int | None = None) -> QIcon:
    """Render the vector brand mark with a small live-app badge for the tray."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    base = QIcon(str(APP_DIR / "icon.svg")).pixmap(64, 64)
    painter.drawPixmap(0, 0, base)
    if count is not None:
        painter.setBrush(QColor(COLORS["green"]))
        painter.setPen(QColor(COLORS["background"]))
        painter.drawRoundedRect(37, 38, 26, 24, 9, 9)
        painter.setFont(QFont("Noto Sans", 11, QFont.Weight.Bold))
        painter.drawText(37, 38, 26, 24, Qt.AlignmentFlag.AlignCenter,
                         "9+" if count > 9 else str(count))
    painter.end()
    return QIcon(pix)


class WorkerSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.function()
        except Exception as exc:  # noqa: BLE001 - report worker failures to the UI
            try:
                self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
            except RuntimeError:
                pass  # The window closed while a scan was finishing.
        else:
            try:
                self.signals.finished.emit(result)
            except RuntimeError:
                pass


class MonitorWindow(QMainWindow):
    SCAN_INTERVAL_MS = 12_000

    def __init__(self, autostart: bool = False):
        super().__init__()
        self.scanner = Scanner()
        self.pool = QThreadPool(self)
        self.settings = QSettings("Local Web Monitor", "Local Web Monitor")
        self.listeners: list[Listener] = []
        self.seen_once = False
        self.seen_web_keys: set[tuple] = set()
        self.first_seen: dict[tuple, float] = {}
        self.reminded_keys: set[tuple] = set()
        self.force_key: tuple | None = None
        self.busy = False
        self.tray: QSystemTrayIcon | None = None
        self.autostart = autostart
        self._build_ui()
        self._ensure_tray()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(self.SCAN_INTERVAL_MS)
        QTimer.singleShot(0, self.refresh)

    def _build_ui(self):
        self.setWindowTitle("Loopglass — Local web apps")
        self.setWindowIcon(icon_with_count())
        self.resize(940, 610)
        root = QWidget()
        root.setObjectName("mainSurface")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(12)
        eyebrow = QLabel("●  LOCAL WEB APPS  /  LIVE SOCKETS")
        eyebrow.setObjectName("eyebrow")
        layout.addWidget(eyebrow)
        hero = QHBoxLayout()
        brand = QSvgWidget(str(APP_DIR / "brand" / "loopglass-lockup-dark.svg"))
        brand.setFixedSize(282, 60)
        brand.setAccessibleName("Loopglass")
        hero.addWidget(brand)
        hero.addStretch()
        self.count_badge = QLabel("-- WEB PROCESSES")
        self.count_badge.setObjectName("countBadge")
        hero.addWidget(self.count_badge)
        layout.addLayout(hero)
        self.summary = QLabel("Scanning local listening ports…")
        self.summary.setObjectName("summary")
        layout.addWidget(self.summary)

        self.tabs = QTabWidget()
        self.web_tree = self._make_tree(["Project / URL", "Process", "Process uptime", "Address scope"])
        self.all_tree = self._make_tree(["Project / URL", "Process", "Process uptime", "Address scope"])
        self.other_tree = self._make_tree(["Process / address", "PID", "Process uptime", "Address scope"])
        self.web_tree.setAccessibleName("Running web app listeners")
        self.all_tree.setAccessibleName("All HTTP and HTTPS listeners")
        self.other_tree.setAccessibleName("Other listening ports")
        self.web_tree.itemSelectionChanged.connect(self._update_actions)
        self.all_tree.itemSelectionChanged.connect(self._update_actions)
        self.tabs.addTab(self.web_tree, "Running web apps")
        self.tabs.addTab(self.all_tree, "All HTTP(S) listeners")
        self.tabs.addTab(self.other_tree, "Other listening ports")
        layout.addWidget(self.tabs, 1)

        actions = QHBoxLayout()
        self.open_button = QPushButton("↗  Open in browser")
        self.open_button.setObjectName("openButton")
        self.open_button.clicked.connect(self._open_selected)
        self.stop_button = QPushButton("■  Stop gracefully")
        self.stop_button.setObjectName("stopButton")
        self.stop_button.clicked.connect(self._stop_selected)
        self.force_button = QPushButton("⚠  Force stop")
        self.force_button.setObjectName("forceButton")
        self.force_button.clicked.connect(self._force_selected)
        self.refresh_button = QPushButton("↻  Refresh")
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.clicked.connect(self.refresh)
        self.refresh_button.setShortcut("F5")
        for button in (self.open_button, self.stop_button, self.force_button, self.refresh_button):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        options = QHBoxLayout()
        self.remind_check = QCheckBox("Remind me about apps left running for")
        self.remind_check.setChecked(self.settings.value("remind_enabled", False, type=bool))
        self.remind_check.toggled.connect(self._save_settings)
        self.remind_hours = QSpinBox()
        self.remind_hours.setRange(1, 168)
        self.remind_hours.setValue(self.settings.value("remind_hours", 4, type=int))
        self.remind_hours.valueChanged.connect(self._save_settings)
        options.addWidget(self.remind_check)
        options.addWidget(self.remind_hours)
        options.addWidget(QLabel("hours"))
        options.addStretch()
        layout.addLayout(options)
        self.setCentralWidget(root)
        self.statusBar().showMessage("Only your own TCP listeners are shown. Select a URL to open or stop it.")
        self.setStyleSheet(WINDOW_STYLE)
        self.tabs.currentChanged.connect(self._update_actions)
        self._update_actions()

    def _make_tree(self, headers: list[str]) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setColumnCount(4)
        tree.setHeaderLabels(headers)
        tree.setAlternatingRowColors(True)
        tree.setRootIsDecorated(True)
        tree.setUniformRowHeights(True)
        header = tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in (1, 2, 3):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        tree.setColumnWidth(1, 145)
        tree.setColumnWidth(2, 85)
        tree.setColumnWidth(3, 130)
        tree.setIndentation(19)
        return tree

    def _save_settings(self, *_):
        self.settings.setValue("remind_enabled", self.remind_check.isChecked())
        self.settings.setValue("remind_hours", self.remind_hours.value())

    def _selected_endpoint(self) -> Listener | None:
        tree = self.tabs.currentWidget()
        if tree not in (self.web_tree, self.all_tree):
            return None
        selected = tree.selectedItems()
        if selected:
            value = selected[0].data(0, Qt.ItemDataRole.UserRole)
            if isinstance(value, Listener):
                return value
        return None

    def _update_actions(self):
        item = self._selected_endpoint()
        self.open_button.setEnabled(item is not None and not self.busy)
        self.stop_button.setEnabled(item is not None and not self.busy)
        self.force_button.setVisible(item is not None and item.key == self.force_key)
        self.force_button.setEnabled(item is not None and not self.busy)

    def _ensure_tray(self):
        available = QSystemTrayIcon.isSystemTrayAvailable()
        if self.tray is not None and not available:
            self.tray.hide()
            self.tray = None
            self.show_normal()
        if self.tray is not None or not available:
            return
        tray = QSystemTrayIcon(icon_with_count(0), self)
        tray.setToolTip("Loopglass")
        tray.activated.connect(self._tray_activated)
        self.tray = tray
        self._rebuild_tray()
        tray.show()

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_normal()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _rebuild_tray(self):
        if self.tray is None:
            return
        web = [item for item in self.listeners if is_web_app(item)]
        app_count = len({(item.pid, item.started) for item in web})
        self.tray.setIcon(icon_with_count(app_count))
        self.tray.setToolTip(f"Loopglass — {app_count} running web app process(es), {len(web)} port(s)")
        menu = QMenu()
        menu.setStyleSheet(MENU_STYLE)
        show = menu.addAction("Show Loopglass")
        show.triggered.connect(self.show_normal)
        menu.addSeparator()
        for item in web[:12]:
            sub = menu.addMenu(f"{Path(item.cwd).name or item.name} · {item.port}")
            open_action = sub.addAction(f"Open {item.url}")
            open_action.triggered.connect(lambda checked=False, target=item: self.open_url(target))
            stop_action = sub.addAction("Stop gracefully…")
            stop_action.triggered.connect(lambda checked=False, target=item: self.stop_target(target))
        if len(web) > 12:
            more = menu.addAction(f"{len(web) - 12} more ports — open window to view")
            more.triggered.connect(self.show_normal)
        if not web:
            empty = menu.addAction("No confirmed web apps")
            empty.setEnabled(False)
        menu.addSeparator()
        refresh = menu.addAction("Refresh")
        refresh.triggered.connect(self.refresh)
        quit_action = menu.addAction("Quit Loopglass")
        quit_action.triggered.connect(QApplication.instance().quit)
        self.tray.setContextMenu(menu)

    def _notify(self, title: str, body: str):
        if self.tray is not None and self.tray.isVisible() and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 6000)
        elif notify_send := shutil.which("notify-send"):
            subprocess.Popen([notify_send, "-a", "Loopglass", title, body],  # nosec B603
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.setEnabled(False)
        self._update_actions()
        self.statusBar().showMessage("Scanning local listeners…")
        job = Job(self.scanner.scan)
        job.signals.finished.connect(self._scan_done)
        job.signals.failed.connect(self._job_failed)
        self.pool.start(job)

    def _scan_done(self, listeners: list[Listener]):
        self.busy = False
        self.refresh_button.setEnabled(True)
        self.listeners = listeners
        self.statusBar().showMessage("Local listeners updated.", 3000)
        self._render()
        self._ensure_tray()
        self._rebuild_tray()
        web = [item for item in listeners if is_web_app(item)]
        current = {item.key for item in web}
        now = time.monotonic()
        for key in current:
            self.first_seen.setdefault(key, now)
        if self.seen_once:
            new = [item for item in web if item.key not in self.seen_web_keys]
            if new:
                if len(new) == 1:
                    self._notify("New local web app", f"{new[0].url} · {new[0].name} (PID {new[0].pid})")
                else:
                    self._notify("New local web apps", f"{len(new)} web app ports are now listening.")
            if self.remind_check.isChecked():
                age = self.remind_hours.value() * 3600
                overdue = [item for item in web if item.key not in self.reminded_keys
                           and now - self.first_seen[item.key] >= age]
                if overdue:
                    self._notify("Web apps still running", f"{len(overdue)} app port(s) have been observed for at least {self.remind_hours.value()} hours.")
                    self.reminded_keys.update(item.key for item in overdue)
        self.seen_once = True
        self.seen_web_keys.update(current)
        self.first_seen = {key: value for key, value in self.first_seen.items() if key in current}
        if self.force_key not in {item.key for item in listeners if item.protocol}:
            self.force_key = None
        self._update_actions()

    @staticmethod
    def _tree_state(tree: QTreeWidget) -> tuple[set[tuple], int, tuple | None]:
        collapsed = set()
        selected = tree.selectedItems()
        selected_key = selected[0].data(0, Qt.ItemDataRole.UserRole + 1) if selected else None
        def visit(item: QTreeWidgetItem):
            key = item.data(0, Qt.ItemDataRole.UserRole + 1)
            if key is not None and item.childCount() and not item.isExpanded():
                collapsed.add(key)
            for index in range(item.childCount()):
                visit(item.child(index))
        for index in range(tree.topLevelItemCount()):
            visit(tree.topLevelItem(index))
        return collapsed, tree.verticalScrollBar().value(), selected_key

    def _render(self):
        web = [item for item in self.listeners if is_web_app(item)]
        confirmed = [item for item in self.listeners if item.protocol]
        other = [item for item in self.listeners if not is_web_app(item)]
        main_count = len({(item.pid, item.started) for item in web})
        all_count = len({(item.pid, item.started) for item in confirmed})
        self.count_badge.setText(f"{main_count:02d} WEB PROCESSES")
        self.summary.setText(
            f"<span style='color:{COLORS['green']}'><b>{main_count}</b></span> likely project web app(s)"
            f"&nbsp;&nbsp;·&nbsp;&nbsp;<span style='color:{COLORS['cyan']}'><b>{len(confirmed)}</b></span> confirmed HTTP(S) port(s)"
            f"&nbsp;&nbsp;·&nbsp;&nbsp;<span style='color:{COLORS['amber']}'><b>{len(other)}</b></span> port(s) outside the main view"
        )
        self.tabs.setTabText(0, f"Running web apps ({main_count})")
        self.tabs.setTabText(1, f"All HTTP(S) listeners ({all_count})")
        self.tabs.setTabText(2, f"Other listening ports ({len(other)})")
        selected = {}
        for tree in (self.web_tree, self.all_tree):
            rows = tree.selectedItems()
            value = rows[0].data(0, Qt.ItemDataRole.UserRole) if rows else None
            selected[tree] = value.key if isinstance(value, Listener) else None
        self._populate_web_tree(self.web_tree, web, selected[self.web_tree])
        self._populate_web_tree(self.all_tree, confirmed, selected[self.all_tree])

        other_collapsed, other_scroll, other_selected = self._tree_state(self.other_tree)
        self.other_tree.clear()
        by_process = defaultdict(list)
        for item in other:
            by_process[(item.pid, item.started)].append(item)
        for _identity, ports in sorted(by_process.items()):
            first = ports[0]
            process = QTreeWidgetItem([first.name, str(first.pid), self._uptime(first), ""])
            process_key = ("other-process", first.pid, first.started)
            process.setData(0, Qt.ItemDataRole.UserRole + 1, process_key)
            process.setToolTip(0, first.cwd)
            process.setForeground(0, QBrush(QColor(COLORS["muted"])))
            self.other_tree.addTopLevelItem(process)
            for item in ports:
                host = f"[{item.bind_host}]" if item.family == socket.AF_INET6 else item.bind_host
                label = f"{host}:{item.port}" + (" · HTTP(S)" if item.protocol else "")
                endpoint = QTreeWidgetItem([label, str(item.pid),
                                            self._uptime(item), item.scope])
                endpoint_key = ("other-endpoint", item.key)
                endpoint.setData(0, Qt.ItemDataRole.UserRole + 1, endpoint_key)
                endpoint.setForeground(0, QBrush(QColor(COLORS["amber"] if item.protocol else COLORS["muted"])))
                endpoint.setForeground(3, QBrush(QColor(COLORS["amber"] if item.scope != "Loopback only" else COLORS["green"])))
                process.addChild(endpoint)
                if endpoint_key == other_selected:
                    self.other_tree.setCurrentItem(endpoint)
            process.setExpanded(process_key not in other_collapsed)
        self.other_tree.verticalScrollBar().setValue(other_scroll)

    def _populate_web_tree(self, tree: QTreeWidget, items: list[Listener], selected_key: tuple | None):
        collapsed, scroll, _ = self._tree_state(tree)
        tree.clear()
        projects = defaultdict(list)
        for item in items:
            projects[item.cwd or "(working directory unavailable)"].append(item)
        for cwd, group in sorted(projects.items()):
            project = QTreeWidgetItem([Path(cwd).name or cwd, "", "", ""])
            project_key = ("project", cwd)
            project.setData(0, Qt.ItemDataRole.UserRole + 1, project_key)
            project.setToolTip(0, cwd)
            project.setForeground(0, QBrush(QColor(COLORS["green"])))
            project.setFont(0, QFont("JetBrains Mono", 12, QFont.Weight.Bold))
            tree.addTopLevelItem(project)
            by_process = defaultdict(list)
            for item in group:
                by_process[(item.pid, item.started)].append(item)
            for _identity, ports in sorted(by_process.items()):
                first = ports[0]
                process = QTreeWidgetItem([first.name, f"PID {first.pid}", self._uptime(first), ""])
                process_key = ("process", cwd, first.pid, first.started)
                process.setData(0, Qt.ItemDataRole.UserRole + 1, process_key)
                process.setToolTip(0, f"{first.name} (PID {first.pid})")
                process.setForeground(0, QBrush(QColor(COLORS["text"])))
                process.setForeground(1, QBrush(QColor(COLORS["muted"])))
                project.addChild(process)
                for item in ports:
                    endpoint = QTreeWidgetItem([item.url, f"{item.name} · {item.pid}",
                                                self._uptime(item), item.scope])
                    endpoint.setData(0, Qt.ItemDataRole.UserRole, item)
                    endpoint.setData(0, Qt.ItemDataRole.UserRole + 1, ("endpoint", item.key))
                    endpoint.setToolTip(0, f"Bound to {item.bind_host}:{item.port}")
                    endpoint.setForeground(0, QBrush(QColor(COLORS["cyan"])))
                    endpoint.setForeground(2, QBrush(QColor(COLORS["muted"])))
                    endpoint.setForeground(3, QBrush(QColor(COLORS["green"] if item.scope == "Loopback only" else COLORS["amber"])))
                    process.addChild(endpoint)
                    if item.key == selected_key:
                        tree.setCurrentItem(endpoint)
                process.setExpanded(process_key not in collapsed)
            project.setExpanded(project_key not in collapsed)
        tree.verticalScrollBar().setValue(scroll)

    @staticmethod
    def _uptime(item: Listener) -> str:
        seconds = max(0, int(time.time() - item.started))
        if seconds >= 86400:
            return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"
        if seconds >= 3600:
            return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
        return f"{seconds // 60}m"

    def open_url(self, item: Listener):
        if item.protocol:
            if not owns_listener(item):
                self.statusBar().showMessage("The original socket is no longer available. Refresh and select it again.", 7000)
                self.refresh()
                return
            if not QDesktopServices.openUrl(QUrl(item.url)):
                self.statusBar().showMessage(f"Could not open {item.url}", 7000)

    def _open_selected(self):
        item = self._selected_endpoint()
        if item:
            self.open_url(item)

    def _stop_selected(self):
        item = self._selected_endpoint()
        if item:
            self.stop_target(item)

    def _force_selected(self):
        item = self._selected_endpoint()
        if item and item.key == self.force_key:
            self.stop_target(item, force=True)

    def stop_target(self, item: Listener, force: bool = False):
        if self.busy:
            return
        verb = "Force stop (SIGKILL)" if force else "Stop gracefully (SIGTERM)"
        detail = (f"{verb} {item.name} (PID {item.pid})?\n\n"
                  f"Selected URL: {item.url}\nProject: {item.cwd or 'unknown'}\n\n"
                  "This signals the entire socket-owning process, which may be a terminal, editor, or desktop helper. Its other ports may close too.")
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Confirm process stop")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(detail)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        if dialog.exec() != QMessageBox.StandardButton.Yes:
            return
        self.busy = True
        self._update_actions()
        job = Job(lambda: stop_listener(item, force=force))
        job.signals.finished.connect(lambda result: self._stop_done(item, result))
        job.signals.failed.connect(self._job_failed)
        self.pool.start(job)

    def _stop_done(self, item: Listener, result: StopResult):
        self.busy = False
        self.force_key = item.key if result.can_force else None
        self.statusBar().showMessage(result.message, 12000)
        if not result.closed:
            QMessageBox.information(self, "Stop result", result.message)
        self.refresh()

    def _job_failed(self, message: str):
        self.busy = False
        self.refresh_button.setEnabled(True)
        self.statusBar().showMessage(message, 12000)
        QMessageBox.warning(self, "Monitor error", message)
        self._update_actions()

    def closeEvent(self, event):
        if self.tray is not None and self.tray.isVisible():
            event.ignore()
            self.hide()
        else:
            event.accept()
            QApplication.instance().quit()


def _runtime_directory() -> Path:
    uid = os.getuid()
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or
                   (Path(tempfile.gettempdir()) / f"loopglass-{uid}"))
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = runtime.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or info.st_mode & 0o077:
        raise RuntimeError(f"Unsafe runtime directory: {runtime}")
    return runtime


def _single_instance(app: QApplication):
    runtime = _runtime_directory()
    lock_path = runtime / "loopglass.lock"
    flags = os.O_WRONLY | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW
    fd = os.open(lock_path, flags, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        os.close(fd)
        raise RuntimeError(f"Unsafe lock file: {lock_path}")
    lock_file = os.fdopen(fd, "w")
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sock = QLocalSocket()
        sock.connectToServer(str(runtime / "loopglass.sock"))
        if not sock.waitForConnected(1000):
            lock_file.close()
            raise RuntimeError("Another instance holds the lock but could not be reached")
        return None, lock_file
    server = QLocalServer(app)
    path = str(runtime / "loopglass.sock")
    QLocalServer.removeServer(path)
    if not server.listen(path):
        lock_file.close()
        raise RuntimeError(f"Could not start local control socket: {server.errorString()}")
    return server, lock_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor and safely stop local web apps")
    parser.add_argument("--autostart", action="store_true", help="hide at login if a tray host exists")
    args = parser.parse_args()
    if sys.platform != "linux" or os.getuid() == 0 or os.getresuid() != (os.getuid(),) * 3:
        print("Loopglass must run on Linux as a normal, non-root user.", file=sys.stderr)
        return 2
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName("Loopglass")
    app.setQuitOnLastWindowClosed(False)
    try:
        server, lock_file = _single_instance(app)
    except (OSError, RuntimeError) as exc:
        print(f"Loopglass startup failed: {exc}", file=sys.stderr)
        return 1
    if server is None:
        return 0
    window = MonitorWindow(autostart=args.autostart)
    def show_existing():
        connection = server.nextPendingConnection()
        if connection is not None:
            connection.close()
        window.show_normal()
    server.newConnection.connect(show_existing)
    if not args.autostart or window.tray is None:
        window.show()
    try:
        return app.exec()
    finally:
        lock_file.close()


if __name__ == "__main__":
    raise SystemExit(main())
