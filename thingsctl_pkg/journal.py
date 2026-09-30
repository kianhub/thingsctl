"""Private operation receipts; never a second Things task database."""

import json
import os
from pathlib import Path
import sqlite3
import stat

from .errors import ThingsError


class OperationJournal:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("THINGSCTL_JOURNAL") or
                         Path.home() / "Library/Application Support/ThingsCTL/operations.sqlite3")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Never chmod an arbitrary existing parent supplied by a developer.
        if self.path.parent.name == "ThingsCTL":
            os.chmod(self.path.parent, 0o700)
        if self.path.is_symlink():
            raise ThingsError("UNSAFE_JOURNAL", "The operation journal must be a regular file owned by you.")
        fd = os.open(str(self.path), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            info = os.fstat(fd)
            if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode):
                raise ThingsError("UNSAFE_JOURNAL", "The operation journal must belong to you.")
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS operations (id TEXT PRIMARY KEY, input_hash TEXT NOT NULL, status TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")

    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=15)
        db.execute("PRAGMA journal_mode=DELETE")
        return db

    def begin(self, operation_id, input_hash):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT input_hash,status,result FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row:
                if row[0] != input_hash:
                    raise ThingsError("OPERATION_ID_REUSED", "This operation ID was already used with different arguments. Use a new operation ID.")
                if row[1] in {"pending", "uncertain"}:
                    result = json.loads(row[2]) if row[2] else None
                    if result:
                        return result
                    raise ThingsError("MUTATION_UNCERTAIN", "This operation was interrupted or is still running. Check Things before issuing a new operation.", uncertain=True)
                return json.loads(row[2]) if row[2] else None
            db.execute("INSERT INTO operations(id,input_hash,status) VALUES(?,?,'pending')", (operation_id, input_hash))
        return None

    def finish(self, operation_id, status, result):
        with self._connect() as db:
            db.execute("UPDATE operations SET status=?,result=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",
                       (status, json.dumps(result, ensure_ascii=False, separators=(",", ":")), operation_id))
