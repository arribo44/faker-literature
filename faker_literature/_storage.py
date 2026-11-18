"""Crash- and concurrency-safe persistence for the TinyDB catalogue.

* :class:`AtomicJSONStorage` writes a temporary file then renames it over the
  database, so that a reader (another process, or a crash in the middle of a
  write) never sees a half-written file.
* :class:`FileLock` serializes the read-modify-write sequences of several
  processes sharing the same database, so that none of their updates is lost.
* :class:`SharedTinyDB` gives every new document an id read from the file,
  so that a process never reuses an id another process has given meanwhile.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import tempfile
import threading
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import TracebackType
from typing import IO, Any

from tinydb import TinyDB
from tinydb.storages import Storage
from tinydb.table import Table

if sys.platform == "win32":  # pragma: no cover - exercised on Windows only
    import msvcrt

    def _lock(file: IO[bytes]) -> None:
        file.seek(0)
        while True:
            try:
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(0.05)

    def _unlock(file: IO[bytes]) -> None:
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(file: IO[bytes]) -> None:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)

    def _unlock(file: IO[bytes]) -> None:
        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _replace(source: str, target: Path) -> None:
    """``os.replace``, retried while Windows refuses it because another process reads ``target``."""
    for _ in range(100):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if sys.platform != "win32":
                raise
            time.sleep(0.02)
    os.replace(source, target)


class AtomicJSONStorage(Storage):
    """TinyDB storage reading and atomically replacing a JSON file."""

    def __init__(self, path: str | os.PathLike[str], create_dirs: bool = False, **dump_options: Any) -> None:
        self.path = Path(path)
        self.dump_options = dump_options
        if create_dirs:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self) -> dict[str, dict[str, Any]] | None:
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

    def write(self, data: dict[str, dict[str, Any]]) -> None:
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
            _replace(temp, self.path)
        except BaseException:
            try:
                os.unlink(temp)
            except FileNotFoundError:
                pass
            raise

    def close(self) -> None:
        pass


class FileLock:
    """Reentrant lock held through ``path`` by one thread of one process at a time."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._thread_lock = threading.RLock()
        self._depth = 0
        self._file: IO[bytes] | None = None

    def __enter__(self) -> FileLock:
        self._thread_lock.acquire()
        try:
            if self._depth == 0:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                file = open(self.path, "a+b")  # kept open while the lock is held
                try:
                    _lock(file)
                except BaseException:
                    file.close()
                    raise
                self._file = file
            self._depth += 1
        except BaseException:
            self._thread_lock.release()
            raise
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self._depth -= 1
        if self._depth == 0 and self._file is not None:
            try:
                _unlock(self._file)
            finally:
                self._file.close()
                self._file = None
        self._thread_lock.release()


class SharedTable(Table):
    """TinyDB table that does not trust its cached next document id.

    :class:`~tinydb.table.Table` computes the id of a new document once, then
    counts on from it in memory.  When another process (or another store on
    the same file) has inserted meanwhile, that id is already taken:
    ``insert_multiple`` then silently overwrites the other document, and
    ``insert`` fails.  This table reads the highest id from the file again at
    each insertion; callers hold the :class:`FileLock` around it.
    """

    def insert(self, document: Mapping[Any, Any]) -> int:
        self._next_id = None
        return super().insert(document)

    def insert_multiple(self, documents: Iterable[Mapping[Any, Any]]) -> list[int]:
        self._next_id = None
        return super().insert_multiple(documents)


class SharedTinyDB(TinyDB):
    """TinyDB database whose tables can be shared by several processes (see :class:`SharedTable`)."""

    table_class = SharedTable
