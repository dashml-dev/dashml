"""
DashML File Watcher - Hot reload for .dashml files
"""
import time
import os
from pathlib import Path
from typing import Callable, Optional
from datetime import datetime


class DashMLWatcher:
    """
    Watches a .dashml file and triggers rebuild on changes.
    Uses simple polling to avoid external dependencies.
    """

    def __init__(
        self,
        dashml_path: str,
        on_change: Callable[[], None],
        poll_interval: float = 1.0
    ):
        """
        Initialize watcher.

        Args:
            dashml_path: Path to .dashml file to watch
            on_change: Callback function to call when file changes
            poll_interval: How often to check for changes (seconds)
        """
        self.dashml_path = Path(dashml_path)
        self.on_change = on_change
        self.poll_interval = poll_interval
        self.last_modified: Optional[float] = None
        self.running = False

        if not self.dashml_path.exists():
            raise FileNotFoundError(f"File not found: {dashml_path}")

    def _get_mtime(self) -> float:
        """Get file modification time"""
        return os.path.getmtime(self.dashml_path)

    def _check_and_trigger(self) -> bool:
        """
        Check if file changed and trigger callback if so.

        Returns:
            True if change detected and callback triggered
        """
        try:
            current_mtime = self._get_mtime()

            # First run - initialize
            if self.last_modified is None:
                self.last_modified = current_mtime
                return False

            # Check if modified
            if current_mtime > self.last_modified:
                self.last_modified = current_mtime
                timestamp = datetime.now().strftime("%H:%M:%S")
                print(f"\n[{timestamp}] 🔄 Change detected in {self.dashml_path.name}")
                self.on_change()
                return True

            return False

        except FileNotFoundError:
            print(f"\n⚠️  File was deleted: {self.dashml_path}")
            return False
        except Exception as e:
            print(f"\n⚠️  Error checking file: {e}")
            return False

    def watch(self) -> None:
        """
        Start watching the file.
        Blocks until interrupted (Ctrl+C).
        """
        self.running = True
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] 👀 Watching {self.dashml_path} for changes...")
        print("Press Ctrl+C to stop\n")

        try:
            while self.running:
                self._check_and_trigger()
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            timestamp = datetime.now().strftime("%H:%M:%S")
            print(f"\n\n[{timestamp}] 🛑 Stopped watching")
            self.running = False

    def stop(self) -> None:
        """Stop watching"""
        self.running = False
