"""Release guards for socket identity, scan bounds, startup, and UI state."""

import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from loopglass.app import MonitorWindow, _runtime_directory, _single_instance, main
from loopglass.monitor import (
    Listener,
    Scanner,
    discover_listeners,
    owns_listener,
    stop_listener,
)

REBIND_SERVER = r'''
import socket, sys
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1',0)); port=s.getsockname()[1]; s.listen()
print(port, flush=True)
sys.stdin.readline(); s.close()
s=socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(('127.0.0.1',port)); s.listen()
print('rebound', flush=True)
sys.stdin.readline(); s.close()
'''


class TestReleaseGuards(unittest.TestCase):
    def test_same_process_rebind_is_rejected(self):
        child = subprocess.Popen([sys.executable, "-u", "-c", REBIND_SERVER],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        try:
            port = int(child.stdout.readline().strip())
            original = next(item for item in discover_listeners()
                            if item.pid == child.pid and item.port == port)
            self.assertIsNotNone(original.inode)
            child.stdin.write("rebind\n")
            child.stdin.flush()
            self.assertEqual(child.stdout.readline().strip(), "rebound")
            rebound = next(item for item in discover_listeners()
                           if item.pid == child.pid and item.port == port)
            self.assertNotEqual(original.inode, rebound.inode)
            self.assertFalse(owns_listener(original))
            self.assertFalse(stop_listener(original).closed)
            self.assertIsNone(child.poll())
        finally:
            child.kill()
            child.wait(timeout=3)
            child.stdin.close()
            child.stdout.close()
            child.stderr.close()

    def test_probe_batch_is_bounded_and_fair(self):
        items = [Listener(1000 + i, 1.0, "test", "/tmp", socket.AF_INET,
                          "127.0.0.1", 20000 + i, inode=100 + i)
                 for i in range(30)]
        scanner = Scanner()
        with patch("loopglass.monitor.discover_listeners", return_value=items), \
             patch("loopglass.monitor.probe_protocol", return_value="http") as probe, \
             patch("loopglass.monitor.owns_listener", return_value=True):
            self.assertEqual(sum(item.protocol == "http" for item in scanner.scan()), 24)
            self.assertEqual(probe.call_count, 24)
            self.assertEqual(sum(item.protocol == "http" for item in scanner.scan()), 30)
            self.assertEqual(probe.call_count, 30)

    def test_root_launch_refused(self):
        with patch("loopglass.app.os.getuid", return_value=0), \
             patch.object(sys, "argv", ["loopglass"]):
            self.assertEqual(main(), 2)

    def test_setuid_socket_owner_is_not_signaled(self):
        uid = os.getuid()
        item = Listener(424242, 1.0, "test", "/tmp", socket.AF_INET,
                        "127.0.0.1", 24569, protocol="http", inode=55)
        fake = SimpleNamespace(uids=lambda: SimpleNamespace(real=uid, effective=0, saved=uid))
        with patch("loopglass.monitor.psutil.Process", return_value=fake):
            result = stop_listener(item)
        self.assertFalse(result.closed)
        self.assertIn("normal user identity", result.message)

    def test_unsafe_runtime_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "target"
            target.mkdir()
            link = Path(tmp) / "runtime"
            link.symlink_to(target, target_is_directory=True)
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(link)}), self.assertRaises(RuntimeError):
                _runtime_directory()

    def test_lock_symlink_refused_without_touching_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            runtime.mkdir(mode=0o700)
            target = Path(tmp) / "target"
            target.write_text("sentinel")
            (runtime / "loopglass.lock").symlink_to(target)
            app = QApplication.instance() or QApplication([])
            with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}), self.assertRaises(OSError):
                _single_instance(app)
            self.assertEqual(target.read_text(), "sentinel")

    def test_tree_state_survives_refresh(self):
        _app = QApplication.instance() or QApplication([])
        window = MonitorWindow()
        window.timer.stop()
        try:
            item = Listener(os.getpid(), 1.0, "test", "/tmp/project", socket.AF_INET,
                            "127.0.0.1", 24567, protocol="http", inode=42)
            other_item = Listener(os.getpid(), 1.0, "test", "/tmp/project", socket.AF_INET,
                                  "127.0.0.1", 24568, inode=43)
            window.listeners = [item, other_item]
            window._render()
            project = window.web_tree.topLevelItem(0)
            project.setExpanded(False)
            other = window.other_tree.topLevelItem(0)
            endpoint = other.child(0)
            window.other_tree.setCurrentItem(endpoint)
            window._render()
            self.assertFalse(window.web_tree.topLevelItem(0).isExpanded())
            self.assertEqual(len(window.other_tree.selectedItems()), 1)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
