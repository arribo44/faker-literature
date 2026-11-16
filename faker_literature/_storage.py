"""Crash- and concurrency-safe persistence for the TinyDB catalogue.

* :class:`AtomicJSONStorage` writes a temporary file then renames it over the
  database, so that a reader (another process, or a crash in the middle of a
  write) never sees a half-written file.
* :class:`FileLock` serializes the read-modify-write sequences of several
  processes sharing the same database, so that none of their updates is lost.
"""

import json
import os
import stat
import tempfile
import threading
import time
from pathlib import Path

from tinydb.storages import Storage

if os.name == "nt":  # pragma: no cover - exercised on Windows only
    import msvcrt

    def _lock(file):
        file.seek(0)
        while True:
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)

    def _unlock(file):
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(file):
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)

    def _unlock(file):
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


class AtomicJSONStorage(Storage):
    """TinyDB storage reading and atomically replacing a JSON file."""

    def __init__(self, path, create_dirs=False, **dump_options):
        self.path = Path(path)
        self.dump_options = dump_options
        if create_dirs:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self):
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        if not text.strip():
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{self.path}: corrupted database ({error}); delete the file and import your datasets again"
            ) from None
        if not isinstance(data, dict):
            raise ValueError(f"{self.path}: corrupted database (expected a JSON object)")
        return data

    def write(self, data):
        content = json.dumps(data, **self.dump_options)
        # mkstemp creates the file for its owner only: keep the permissions of an existing database
        mode = stat.S_IMODE(self.path.stat().st_mode) if self.path.exists() else None
        fd, temp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            if mode is not None:
                os.chmod(temp, mode)
            os.replace(temp, self.path)
        except BaseException:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass
            raise

    def close(self):
        pass


class FileLock:
    """Reentrant lock held through ``path`` by one thread of one process at a time."""

    def __init__(self, path):
        self.path = Path(path)
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._file = None

    def __enter__(self):
        self._thread_lock.acquire()
        try:
            if self._depth == 0:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self._file = open(self.path, "a+b")
                try:
                    _lock(self._file)
                except BaseException:
                    self._file.close()
                    raise
            self._depth += 1
        except BaseException:
            self._thread_lock.release()
            raise
        return self

    def __exit__(self, *exc_info):
        self._depth -= 1
        if self._depth == 0:
            try:
                _unlock(self._file)
            finally:
                self._file.close()
                self._file = None
        self._thread_lock.release()
