"""Atomic file writes that survive Windows/OneDrive file locks.

On Windows, `os.replace` fails with PermissionError (WinError 5/32) while another process
has the target open: OneDrive syncing it, an editor, or a reader. The output folder lives
in OneDrive, which re-uploads the audit trail after every write, so this happens mid-run.
We retry the replace with backoff. If the lock never clears, we overwrite the file in
place, which Windows allows when the other process opened it for shared reading.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

RETRIES = 24          # ~5 s in total with the backoff below
FIRST_DELAY = 0.02
MAX_DELAY = 0.25


def _retry(action, retries: int = RETRIES) -> bool:
    delay = FIRST_DELAY
    for _ in range(retries):
        try:
            action()
            return True
        except PermissionError:
            time.sleep(delay)
            delay = min(delay * 2, MAX_DELAY)
    return False


def atomic_write_text(path: Path, text: str) -> None:
    """Write `text` to `path` via a temp file and replace, retrying while the file is locked."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    if not _retry(lambda: tmp.write_text(text, encoding="utf-8")):
        tmp = None
    if tmp is not None and _retry(lambda: os.replace(tmp, path)):
        return
    # The lock didn't clear: write in place instead of failing the run.
    try:
        if not _retry(lambda: path.write_text(text, encoding="utf-8"), retries=RETRIES * 2):
            path.write_text(text, encoding="utf-8")  # last try; raises the real error
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
