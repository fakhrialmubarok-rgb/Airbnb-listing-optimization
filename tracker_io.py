"""Atomic, locked tracker CSV I/O — shared by all pipeline steps."""
import csv, os, tempfile, fcntl
from pathlib import Path

def write_rows(path, rows, fieldnames=None):
    """Atomic replace + advisory lock; never leaves a truncated tracker."""
    path = str(path)
    fieldnames = fieldnames or list(rows[0].keys())
    lock = open(path + ".lock", "w")
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path))
        with os.fdopen(fd, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k, "") for k in fieldnames})
        os.replace(tmp, path)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()
