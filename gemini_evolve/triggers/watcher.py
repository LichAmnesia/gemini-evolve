"""File watcher trigger — runs evolution when Gemini CLI sessions complete."""

from __future__ import annotations

import time
import threading
from collections.abc import Callable
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
from watchdog.observers import Observer


class SessionCompleteHandler(FileSystemEventHandler):
    """Triggers evolution after Gemini CLI session files are written.

    Uses a debounce timer to avoid running evolution on every incremental
    write — waits until the session directory is quiet for `debounce_seconds`.
    """

    def __init__(
        self,
        callback: Callable[[str, str], None],
        debounce_seconds: float = 30.0,
        target_type: str = "instructions",
    ):
        super().__init__()
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.target_type = target_type
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._last_event_path: str = ""

    def on_created(self, event: FileCreatedEvent) -> None:
        if not event.is_directory:
            self._debounce(event.src_path)

    def on_modified(self, event: FileModifiedEvent) -> None:
        if not event.is_directory:
            self._debounce(event.src_path)

    def _debounce(self, path: str) -> None:
        with self._lock:
            self._last_event_path = path
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
            path = self._last_event_path
        self.callback(path, self.target_type)


def start_watcher(
    watch_dir: Path | None = None,
    callback: Callable[[str, str], None] | None = None,
    debounce_seconds: float = 30.0,
    target_type: str = "instructions",
    apply: bool = False,
) -> Observer:
    """Start watching for Gemini CLI session changes.

    Args:
        watch_dir: Directory to watch (default: ~/.gemini/tmp).
        callback: Function(path, target_type) called when evolution should run.
        debounce_seconds: Wait this long after last file change before triggering.
        target_type: What to evolve when triggered.
        apply: Write evolved content back to original files.

    Returns:
        The Observer instance (call .stop() to shut down).
    """
    if watch_dir is None:
        watch_dir = Path.home() / ".gemini" / "tmp"

    if callback is None:
        from ..evolve import evolve, discover_targets
        from ..config import EvolutionConfig

        def default_callback(path: str, ttype: str) -> None:
            config = EvolutionConfig.from_env()
            targets = discover_targets(config, ttype)
            for target in targets:
                try:
                    evolve(target, config, apply=apply)
                except Exception as e:
                    print(f"Evolution failed for {target}: {e}")

        callback = default_callback

    handler = SessionCompleteHandler(
        callback=callback,
        debounce_seconds=debounce_seconds,
        target_type=target_type,
    )
    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=True)
    observer.start()
    return observer


def run_watcher_blocking(
    watch_dir: Path | None = None,
    debounce_seconds: float = 30.0,
    target_type: str = "instructions",
    apply: bool = False,
) -> None:
    """Run the file watcher in blocking mode (for CLI use)."""
    observer = start_watcher(
        watch_dir=watch_dir,
        debounce_seconds=debounce_seconds,
        target_type=target_type,
        apply=apply,
    )
    print(f"Watching {watch_dir or '~/.gemini/tmp'} for session changes...")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
